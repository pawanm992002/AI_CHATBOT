"""Safe metadata-driven School ERP query and report engine."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from bson.decimal128 import Decimal128

from core.auth import db
from services.school_data_registry import (
    SAFE_OPERATORS,
    EntitySpec,
    explain_entity,
    get_entity_spec,
    normalize_entity_name,
)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_REGEX_LENGTH = 200
ALLOWED_SORT_DIRECTIONS = {1, -1, "asc", "desc", "ASC", "DESC"}
FEE_DUE_STATUSES = {"Pending", "Partial"}
FEE_STATUSES = {"Paid", "Pending", "Partial"}


def serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    if isinstance(value, Decimal):
        return str(value)
    return value


def serialize_document(document: dict[str, Any]) -> dict[str, Any]:
    return {key: serialize_value(value) for key, value in document.items()}


def serialize_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [serialize_document(document) for document in documents]


def to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def normalize_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(int(limit), MAX_LIMIT))


def normalize_sort_direction(direction: Any) -> int:
    if direction not in ALLOWED_SORT_DIRECTIONS:
        raise ValueError(f"Invalid sort direction: {direction}")
    if direction in (-1, "desc", "DESC"):
        return -1
    return 1


def validate_projection(spec: EntitySpec, projection: list[str] | None) -> dict[str, int]:
    fields = projection or list(spec.default_projection)
    invalid = [field for field in fields if field not in spec.fields]
    if invalid:
        raise ValueError(f"Projection contains invalid field(s) for {spec.entity}: {invalid}")

    mongo_projection = {field: 1 for field in fields}
    mongo_projection["_id"] = 0
    return mongo_projection


def validate_filter_condition(spec: EntitySpec, condition: dict[str, Any]) -> dict[str, Any]:
    field = condition.get("field")
    op = condition.get("op", "$eq")
    value = condition.get("value")

    if field not in spec.fields:
        raise ValueError(f"Invalid field for {spec.entity}: {field}")
    if op not in SAFE_OPERATORS or op not in spec.fields[field].operators:
        raise ValueError(f"Invalid operator for {spec.entity}.{field}: {op}")

    if op == "$regex":
        val_str = str(value)
        if len(val_str) > MAX_REGEX_LENGTH:
            raise ValueError(f"Regex too long for {spec.entity}.{field}")
        return {field: {"$regex": val_str, "$options": "i"}}

    if op == "$in":
        if not isinstance(value, list):
            raise ValueError(f"$in value must be a list for {spec.entity}.{field}")
        return {field: {"$in": value}}

    return {field: {op: value}}


def build_entity_filter(
    spec: EntitySpec,
    filters: list[dict[str, Any]] | None,
    tenant_id: str,
) -> dict[str, Any]:
    safe_conditions = [{"tenant_id": tenant_id}]
    for condition in filters or []:
        safe_conditions.append(validate_filter_condition(spec, condition))

    if len(safe_conditions) == 1:
        return {"tenant_id": tenant_id}
    return {"$and": safe_conditions}


def build_sort(spec: EntitySpec, sort: list[dict[str, Any]] | None) -> list[tuple[str, int]]:
    sort_spec: list[tuple[str, int]] = []
    for item in sort or []:
        field = item.get("field")
        if field not in spec.sortable_fields:
            raise ValueError(f"Invalid sort field for {spec.entity}: {field}")
        sort_spec.append((field, normalize_sort_direction(item.get("direction", 1))))

    if sort_spec:
        return sort_spec
    return [(spec.primary_key, 1)] if spec.primary_key in spec.fields else []


class SchoolDataEngine:
    """Executes safe generic school queries and deterministic reports."""

    async def search_entity(
        self,
        *,
        tenant_id: str,
        entity: str,
        filters: list[dict[str, Any]] | None = None,
        projection: list[str] | None = None,
        sort: list[dict[str, Any]] | None = None,
        limit: int | None = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        spec = get_entity_spec(entity)
        safe_filter = build_entity_filter(spec, filters, tenant_id)
        safe_projection = validate_projection(spec, projection)
        safe_sort = build_sort(spec, sort)
        safe_limit = normalize_limit(limit)

        total_count = await db[spec.collection].count_documents(safe_filter)
        cursor = db[spec.collection].find(safe_filter, safe_projection)
        if safe_sort:
            cursor = cursor.sort(safe_sort)
        rows = await cursor.limit(safe_limit).to_list(length=safe_limit)

        return {
            "entity": spec.entity,
            "collection": spec.collection,
            "filter": safe_filter,
            "total_count": total_count,
            "returned_count": len(rows),
            "has_more": total_count > len(rows),
            "limit": safe_limit,
            "rows": serialize_documents(rows),
        }

    async def get_entity_detail(
        self,
        *,
        tenant_id: str,
        entity: str,
        entity_id: Any,
        projection: list[str] | None = None,
    ) -> dict[str, Any]:
        spec = get_entity_spec(entity)
        return await self.search_entity(
            tenant_id=tenant_id,
            entity=spec.entity,
            filters=[{"field": spec.primary_key, "op": "$eq", "value": entity_id}],
            projection=projection,
            limit=1,
        )

    async def count_entities(
        self,
        *,
        tenant_id: str,
        entity: str,
        filters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        spec = get_entity_spec(entity)
        safe_filter = build_entity_filter(spec, filters, tenant_id)
        total_count = await db[spec.collection].count_documents(safe_filter)
        return {
            "entity": spec.entity,
            "collection": spec.collection,
            "filter": safe_filter,
            "total_count": total_count,
        }

    async def get_related_entities(
        self,
        *,
        tenant_id: str,
        entity: str,
        entity_id: Any,
        relationship: str,
        projection: list[str] | None = None,
        limit: int | None = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        source = get_entity_spec(entity)
        if relationship not in source.relationships:
            raise ValueError(f"Unknown relationship for {source.entity}: {relationship}")

        rel = source.relationships[relationship]
        source_detail = await self.get_entity_detail(
            tenant_id=tenant_id,
            entity=source.entity,
            entity_id=entity_id,
            projection=[source.primary_key, rel.local_key],
        )
        if not source_detail["rows"]:
            return {
                "entity": source.entity,
                "relationship": relationship,
                "related_entity": normalize_entity_name(rel.entity),
                "total_count": 0,
                "returned_count": 0,
                "has_more": False,
                "limit": normalize_limit(limit),
                "rows": [],
            }

        local_value = source_detail["rows"][0].get(rel.local_key)
        return await self.search_entity(
            tenant_id=tenant_id,
            entity=rel.entity,
            filters=[{"field": rel.foreign_key, "op": "$eq", "value": local_value}],
            projection=projection,
            limit=limit,
        )

    async def get_report(
        self,
        *,
        tenant_id: str,
        report_id: str,
        filters: dict[str, Any] | None = None,
        limit: int | None = MAX_LIMIT,
    ) -> dict[str, Any]:
        normalized = report_id.strip().lower()
        if normalized in {"due_fees_by_student", "due_fee_report", "fee_due_report"}:
            return await self.due_fees_by_student(tenant_id=tenant_id, filters=filters, limit=limit)
        raise ValueError(f"Unknown school report: {report_id}")

    async def due_fees_by_student(
        self,
        *,
        tenant_id: str,
        filters: dict[str, Any] | None = None,
        limit: int | None = MAX_LIMIT,
    ) -> dict[str, Any]:
        filters = filters or {}
        safe_limit = normalize_limit(limit)
        statuses = filters.get("statuses") or filters.get("status") or ["Pending", "Partial"]
        if isinstance(statuses, str):
            statuses = [statuses]
        invalid_statuses = [status for status in statuses if status not in FEE_STATUSES]
        if invalid_statuses:
            raise ValueError(f"Invalid fee status value(s): {invalid_statuses}")

        fee_conditions: list[dict[str, Any]] = [
            {"field": "status", "op": "$in", "value": statuses},
        ]
        for field in ("student_id", "school_id", "fee_head", "due_date"):
            if field in filters and filters[field] is not None:
                fee_conditions.append({"field": field, "op": "$eq", "value": filters[field]})

        fee_spec = get_entity_spec("applied_fee")
        fee_filter = build_entity_filter(fee_spec, fee_conditions, tenant_id)
        fee_projection = {
            "_id": 0,
            "applied_fee_id": 1,
            "student_id": 1,
            "school_id": 1,
            "fee_head": 1,
            "amount": 1,
            "concession": 1,
            "status": 1,
            "due_date": 1,
        }
        fees = await db.school_applied_fees.find(fee_filter, fee_projection).sort(
            [("student_id", 1), ("applied_fee_id", 1)]
        ).to_list(length=None)

        applied_fee_ids = [fee["applied_fee_id"] for fee in fees if fee.get("applied_fee_id") is not None]
        paid_by_fee: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        if applied_fee_ids:
            payments = await db.school_payments.find(
                {"tenant_id": tenant_id, "applied_fee_id": {"$in": applied_fee_ids}},
                {"_id": 0, "applied_fee_id": 1, "paid_amount": 1},
            ).to_list(length=None)
            for payment in payments:
                applied_fee_id = payment.get("applied_fee_id")
                if applied_fee_id is not None:
                    paid_by_fee[applied_fee_id] += to_decimal(payment.get("paid_amount"))

        by_student: dict[int, dict[str, Any]] = defaultdict(
            lambda: {
                "student_id": None,
                "due_amount": Decimal("0"),
                "fee_record_count": 0,
                "breakdown": [],
            }
        )
        total_due = Decimal("0")
        for fee in fees:
            student_id = fee.get("student_id")
            amount = to_decimal(fee.get("amount"))
            concession = to_decimal(fee.get("concession"))
            net_amount = amount - concession
            paid_amount = paid_by_fee[fee.get("applied_fee_id")]
            due_amount = max(net_amount - paid_amount, Decimal("0"))
            total_due += due_amount

            row = by_student[student_id]
            row["student_id"] = student_id
            row["due_amount"] += due_amount
            row["fee_record_count"] += 1
            row["breakdown"].append({
                "applied_fee_id": fee.get("applied_fee_id"),
                "fee_head": fee.get("fee_head"),
                "amount": serialize_value(amount),
                "concession": serialize_value(concession),
                "paid_amount": serialize_value(paid_amount),
                "due_amount": serialize_value(due_amount),
                "status": fee.get("status"),
                "due_date": fee.get("due_date"),
            })

        student_filters: list[dict[str, Any]] = []
        for field in ("class_id", "section_id"):
            if field in filters and filters[field] is not None:
                student_filters.append({"field": field, "op": "$eq", "value": filters[field]})

        student_ids = list(by_student)
        students_by_id: dict[int, dict[str, Any]] = {}
        if student_ids:
            student_spec = get_entity_spec("student")
            student_filters.append({"field": "student_id", "op": "$in", "value": student_ids})
            student_filter = build_entity_filter(student_spec, student_filters, tenant_id)
            students = await db.school_students.find(
                student_filter,
                {
                    "_id": 0,
                    "student_id": 1,
                    "student_name": 1,
                    "admission_no": 1,
                    "class_id": 1,
                    "section_id": 1,
                },
            ).to_list(length=None)
            students_by_id = {student["student_id"]: student for student in students}

        rows = []
        filtered_total_due = Decimal("0")
        filtered_fee_record_count = 0
        for student_id, due_data in sorted(by_student.items()):
            student = students_by_id.get(student_id)
            if not student:
                continue
            filtered_total_due += due_data["due_amount"]
            filtered_fee_record_count += due_data["fee_record_count"]
            rows.append({
                "student_id": student_id,
                "student_name": student.get("student_name"),
                "admission_no": student.get("admission_no"),
                "class_id": student.get("class_id"),
                "section_id": student.get("section_id"),
                "due_amount": serialize_value(due_data["due_amount"]),
                "fee_record_count": due_data["fee_record_count"],
                "breakdown": due_data["breakdown"],
            })

        total_count = len(rows)
        returned_rows = rows[:safe_limit]
        return {
            "report_id": "due_fees_by_student",
            "calculation_basis": "Due amount = sum(max(amount - concession - payments recorded against each applied fee, 0)) for selected statuses.",
            "statuses": list(statuses),
            "filters": filters,
            "total_due": serialize_value(filtered_total_due),
            "student_count": total_count,
            "fee_record_count": filtered_fee_record_count,
            "total_count": total_count,
            "returned_count": len(returned_rows),
            "has_more": total_count > len(returned_rows),
            "limit": safe_limit,
            "rows": returned_rows,
        }

    def explain_schema(self, entity: str | None = None) -> dict[str, Any]:
        if entity:
            return explain_entity(entity)
        from services.school_data_registry import SCHOOL_ENTITY_REGISTRY

        return {
            "entities": sorted(SCHOOL_ENTITY_REGISTRY.keys()),
            "reports": ["due_fees_by_student"],
        }


school_data_engine = SchoolDataEngine()
