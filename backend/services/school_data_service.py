"""
School Data Query Service.

Translates natural language questions into structured MongoDB queries with
strict output validation. The LLM proposes filter *conditions* as structured
JSON, never raw Mongo syntax. The service validates against a per-collection
allowlist, injects tenant_id server-side, and executes.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from core.auth import db
from core.redis import redis_client, get_redis_key
from services.llm.factory import get_llm
from services.school_data_filter import build_safe_filter

COLLECTION_DESCRIPTIONS = {
    "schools": "School information (name, id)",
    "school_classes": "Classes/standards offered (e.g. Nursery, 1, 2, ... 8)",
    "school_sections": "Sections within each class (A, B, C)",
    "school_students": "Student records (name, admission_no, class, section, parents, gender, blood_group, category, address)",
    "school_routes": "Transport routes",
    "school_stops": "Bus stops on each route",
    "school_transport_assign": "Which students are assigned to which transport routes",
    "school_hostel_assign": "Hostel assignments for students",
    "school_applied_fees": "Fee structure applied to each student (fee_head, amount, concession, status)",
    "school_payments": "Payment records against applied fees",
}

MAX_RESULT_LIMIT = 20
MAX_CHAIN_DEPTH = 3
SCHOOL_MODE_TTL = 1800  # 30 min inactivity TTL for school mode


_LLM_SYSTEM_PROMPT = """You translate natural language questions into structured MongoDB filter conditions for a school ERP system.

Available collections:
{collection_descriptions}

Return a JSON object with these fields:
- "collection": one of the collection names listed above
- "conditions": an array of filter conditions, each with:
    - "field": the field name to filter on
    - "op": the operator ("$eq", "$regex", "$in")
    - "value": the value to match
- "fields": array of field names to return (empty array = return all fields)
- "limit": max results to return (max 20)

Rules:
- Use "$regex" for partial name/string matching
- Use "$eq" for exact IDs, status values, or known exact values
- Use "$in" when the question lists multiple values
- Keep limit small (1-5) for specific lookups, 20 for list queries
- Return ONLY valid JSON, no explanation, no markdown formatting

Example 1: "Show me Ansh Sharma's fee balance"
{{"collection": "school_students", "conditions": [{{"field": "student_name", "op": "$regex", "value": "Ansh Sharma"}}], "fields": ["student_id", "student_name", "admission_no", "class_id"], "limit": 5}}

Example 2: "List all students in class 5"
{{"collection": "school_students", "conditions": [{{"field": "class_id", "op": "$eq", "value": 26}}], "fields": [], "limit": 20}}"""


_COLLECTION_RELATIONSHIPS = {
    "school_students": [
        {
            "collection": "school_applied_fees",
            "link_field": "student_id",
            "label": "fee records",
        },
        {
            "collection": "school_payments",
            "link_field": "student_id",
            "label": "payment records",
        },
        {
            "collection": "school_transport_assign",
            "link_field": "student_id",
            "label": "transport assignment",
        },
        {
            "collection": "school_hostel_assign",
            "link_field": "student_id",
            "label": "hostel assignment",
        },
    ],
}


class SchoolDataService:

    def __init__(self):
        self._repo_cache = {}

    @staticmethod
    def _serialize_value(v: Any) -> Any:
        """Convert BSON types to JSON-safe Python types.

        Handles Decimal128 → str, and passes through everything else.
        """
        from bson.decimal128 import Decimal128
        if isinstance(v, Decimal128):
            return str(v.to_decimal())
        return v

    @staticmethod
    def _serialize_results(results: list[dict]) -> list[dict]:
        """Deep-convert all values in a result list to JSON-safe types."""
        serialized = []
        for row in results:
            serialized.append({k: SchoolDataService._serialize_value(v) for k, v in row.items()})
        return serialized

    async def _compute_fee_summary(
        self,
        tenant_id: str,
        student_id: int,
    ) -> str | None:
        """Server-side fee reconciliation.

        Computes true outstanding balance as:
          SUM(amount - concession) FROM school_applied_fees
          - SUM(paid_amount) FROM school_payments

        Ignores the stored school_payments.balance field entirely.
        Returns a formatted string or None if no fee records exist.
        """
        fees_cursor = db.school_applied_fees.find(
            {"tenant_id": tenant_id, "student_id": student_id},
            {"_id": 0, "applied_fee_id": 1, "fee_head": 1, "amount": 1, "concession": 1, "status": 1, "due_date": 1},
        )
        fees = await fees_cursor.to_list(length=MAX_RESULT_LIMIT)
        if not fees:
            return None

        from bson.decimal128 import Decimal128
        from decimal import Decimal

        total_amount = Decimal("0")
        total_concession = Decimal("0")

        fee_lines = []
        for f in fees:
            amount = self._to_decimal_val(f.get("amount"))
            concession = self._to_decimal_val(f.get("concession"))
            total_amount += amount
            total_concession += concession
            net = amount - concession
            fee_lines.append(
                f"  {f.get('fee_head', 'Unknown')}: ₹{net} "
                f"(due: {f.get('due_date', 'N/A')}, status: {f.get('status', 'N/A')})"
            )

        payments_cursor = db.school_payments.find(
            {"tenant_id": tenant_id, "student_id": student_id},
            {"_id": 0, "paid_amount": 1, "payment_date": 1, "payment_mode": 1, "receipt_no": 1},
        )
        payments = await payments_cursor.to_list(length=MAX_RESULT_LIMIT)

        total_paid = Decimal("0")
        pay_lines = []
        for p in payments:
            amt = self._to_decimal_val(p.get("paid_amount"))
            total_paid += amt
            pay_lines.append(
                f"  Receipt {p.get('receipt_no', 'N/A')}: ₹{amt} "
                f"on {p.get('payment_date', 'N/A')} ({p.get('payment_mode', 'N/A')})"
            )

        net_payable = total_amount - total_concession
        outstanding = net_payable - total_paid

        parts = [f"Fee Summary (Student ID {student_id}):"]
        parts.append(f"  Total fees applied: ₹{total_amount}")
        parts.append(f"  Total concession: ₹{total_concession}")
        parts.append(f"  Net payable: ₹{net_payable}")
        parts.extend(fee_lines)
        if pay_lines:
            parts.append(f"  Total paid: ₹{total_paid}")
            parts.extend(pay_lines)
        else:
            parts.append("  No payments recorded yet.")
        parts.append(f"  Outstanding balance: ₹{outstanding}")
        if outstanding > 0:
            parts.append("  ⚠ This balance is computed from fees minus payments and may differ from cached values.")

        return "\n".join(parts)

    @staticmethod
    def _to_decimal_val(val: Any) -> Decimal:
        """Extract a Python Decimal from a Decimal128, int, float, or None."""
        from bson.decimal128 import Decimal128
        from decimal import Decimal
        if val is None:
            return Decimal("0")
        if isinstance(val, Decimal128):
            return val.to_decimal()
        if isinstance(val, (int, float)):
            return Decimal(str(val))
        if isinstance(val, Decimal):
            return val
        return Decimal("0")

    async def query(
        self,
        tenant_id: str,
        session_id: str,
        question: str,
        llm_provider: str = "openai",
        llm_model: str = "gpt-4o-mini",
    ) -> str:
        """Translate a natural language question into school data results.

        Returns a formatted string suitable for injection into chat context.
        Logs every query call to school_data_query_log for audit.
        """
        coll_desc_lines = "\n".join(
            f'- "{k}": {v}' for k, v in COLLECTION_DESCRIPTIONS.items()
        )
        system_prompt = _LLM_SYSTEM_PROMPT.format(
            collection_descriptions=coll_desc_lines,
        )

        llm = get_llm(llm_provider, llm_model)
        resp = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ])

        raw = (resp.content or "").strip()
        parsed = self._parse_llm_response(raw)
        if not parsed:
            return "I couldn't understand how to look up that information. Could you rephrase your question?"

        collection = parsed["collection"]
        conditions = parsed.get("conditions", [])
        fields = parsed.get("fields", [])
        limit = min(parsed.get("limit", MAX_RESULT_LIMIT), MAX_RESULT_LIMIT)

        safe_filter = build_safe_filter(collection, conditions, tenant_id)

        # Log the query for audit
        await self._log_query(tenant_id, session_id, question, safe_filter)

        projection = {f: 1 for f in fields} if fields else {"_id": 0}
        projection["_id"] = 0

        cursor = db[collection].find(safe_filter, projection).limit(limit)
        results = await cursor.to_list(length=limit)

        if not results:
            return f"I couldn't find any data matching your query in the {collection.replace('school_', '')} records."

        # Serialize Decimal128 to string for JSON-safe output
        results = self._serialize_results(results)

        # Check for ambiguous entity resolution
        if collection == "school_students" and len(results) > 1:
            return self._format_ambiguous_students(results)

        # Format results
        answer_parts = []
        answer_parts.append(self._format_results(collection, results))

        # Chain follow-up queries (up to MAX_CHAIN_DEPTH)
        chain_depth = 0
        seen_collections = {collection}
        for rel in _COLLECTION_RELATIONSHIPS.get(collection, []):
            if chain_depth >= MAX_CHAIN_DEPTH:
                break
            child_collection = rel["collection"]
            if child_collection in seen_collections:
                continue
            link_field = rel["link_field"]
            child_results = await self._fetch_related(
                tenant_id, child_collection, link_field, results, rel["label"],
            )
            if child_results:
                answer_parts.append(child_results)
                seen_collections.add(child_collection)
                chain_depth += 1

        # Compute fee summary (server-side reconciliation) when student data was queried
        if collection == "school_students" and len(results) == 1:
            student_id = results[0].get("student_id")
            if student_id is not None:
                fee_summary = await self._compute_fee_summary(tenant_id, student_id)
                if fee_summary:
                    answer_parts.append(fee_summary)

        return "\n\n".join(answer_parts)

    def _parse_llm_response(self, raw: str) -> dict | None:
        """Extract JSON from LLM response, trying multiple parsing strategies."""
        # Try direct parse first
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "collection" in data:
                return data
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict) and "collection" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # Try finding first { and last }
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
                if isinstance(data, dict) and "collection" in data:
                    return data
            except json.JSONDecodeError:
                pass

        return None

    def _format_results(self, collection: str, results: list[dict]) -> str:
        display_name = collection.replace("school_", "").replace("_", " ").title()
        if len(results) == 1:
            return self._format_single_record(collection, results[0])
        rows = []
        for r in results:
            row = ", ".join(f"{k}: {v}" for k, v in r.items() if v is not None and k != "_id")
            rows.append(f"- {row}")
        return f"I found {len(results)} {display_name} record(s):\n" + "\n".join(rows)

    def _format_single_record(self, collection: str, record: dict) -> str:
        display_name = collection.replace("school_", "").replace("_", " ").title()
        details = "\n".join(f"  {k}: {v}" for k, v in record.items() if v is not None and k != "_id")
        return f"{display_name}:\n{details}"

    def _format_ambiguous_students(self, results: list[dict]) -> str:
        rows = []
        for r in results:
            class_info = f"Class ID {r.get('class_id', '?')}, Section {r.get('section_id', '?')}"
            rows.append(
                f"- {r.get('student_name', 'Unknown')} (Admission: {r.get('admission_no', 'N/A')}, "
                f"{class_info})"
            )
        return (
            f"I found {len(results)} students matching that name. Could you specify which one?\n"
            + "\n".join(rows)
        )

    async def _fetch_related(
        self,
        tenant_id: str,
        collection: str,
        link_field: str,
        parent_results: list[dict],
        label: str,
    ) -> str | None:
        """Fetch related records (e.g. fees for a student)."""
        ids = [r.get(link_field) for r in parent_results if r.get(link_field) is not None]
        if not ids:
            return None

        safe_filter = {
            "tenant_id": tenant_id,
            link_field: {"$in": ids},
        }
        cursor = db[collection].find(safe_filter, {"_id": 0}).limit(MAX_RESULT_LIMIT)
        child_results = await cursor.to_list(length=MAX_RESULT_LIMIT)
        if not child_results:
            return None

        child_results = self._serialize_results(child_results)
        return self._format_results(collection, child_results)

    async def _log_query(
        self,
        tenant_id: str,
        session_id: str,
        question: str,
        generated_filter: dict,
    ) -> None:
        """Log every SchoolDataService.query() call for audit."""
        try:
            await db.school_data_query_log.insert_one({
                "log_id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "session_id": session_id,
                "question": question[:500],
                "generated_filter": generated_filter,
                "timestamp": datetime.now(timezone.utc),
            })
        except Exception as e:
            print(f"[SCHOOL_DATA] Audit log failed: {e}")

    # -----------------------------------------------------------------------
    # School mode session management
    # -----------------------------------------------------------------------

    @staticmethod
    async def set_school_mode(session_id: str, tenant_id: str) -> None:
        key = get_redis_key(f"school_mode:{session_id}")
        await redis_client.setex(key, SCHOOL_MODE_TTL, tenant_id)

    @staticmethod
    async def get_school_mode(session_id: str) -> str | None:
        key = get_redis_key(f"school_mode:{session_id}")
        return await redis_client.get(key)

    @staticmethod
    async def clear_school_mode(session_id: str) -> None:
        key = get_redis_key(f"school_mode:{session_id}")
        await redis_client.delete(key)
