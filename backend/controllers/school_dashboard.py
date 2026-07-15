"""Read-only School ERP records used to verify School Agent answers."""

from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth import db, get_current_tenant
from models.requests import DashboardSchoolChatRequest
from services.archival_service import archival_service
from services.chat_service import ChatService, ChatTurnInput
from services.school_data_engine import school_data_engine, serialize_documents, to_decimal
from services.school_data_service import SchoolDataService


router = APIRouter(prefix="/dashboard/school", tags=["school-dashboard"])
_chat_service = ChatService()
_school_data_service = SchoolDataService()
MAX_QUERY_LENGTH = 500
DASHBOARD_SESSION_PREFIX = "dashboard-school-"


def _money(value: object) -> str:
    return str(to_decimal(value))


@router.post("/chat")
async def dashboard_school_chat(
    req: DashboardSchoolChatRequest,
    current_tenant: dict = Depends(get_current_tenant),
):
    """Run a School Agent turn for the signed-in tenant without widget credentials."""
    tenant_id = current_tenant["tenant_id"]
    session_id = req.session_id or f"{DASHBOARD_SESSION_PREFIX}{uuid.uuid4()}"
    if not session_id.startswith(DASHBOARD_SESSION_PREFIX):
        raise HTTPException(status_code=400, detail="Invalid dashboard school chat session.")
    query = req.query.strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        raise HTTPException(status_code=400, detail="Question must be between 1 and 500 characters.")

    from core.rate_limiter import check_rate_limit

    if await check_rate_limit(f"rate_limit:chat:tenant:{tenant_id}", limit=100, window=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    if await check_rate_limit(f"rate_limit:chat:session:{session_id}", limit=20, window=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")

    # Dashboard JWT authentication already proves this user belongs to the school.
    await _school_data_service.set_school_mode(session_id, tenant_id)
    result = await _chat_service.handle_message(
        ChatTurnInput(
            tenant=current_tenant,
            session_id=session_id,
            visitor_id=f"dashboard-admin:{tenant_id}",
            query=query,
            current_url="/dashboard/school-chat",
            current_page_title="School Chat",
            message_id=str(uuid.uuid4()),
        )
    )
    return {
        "session_id": session_id,
        "message_id": result.message_id,
        "answer": result.answer,
    }


@router.get("/chat/{session_id}")
async def get_dashboard_school_chat(
    session_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    """Load a saved dashboard School Agent conversation within the same tenant."""
    tenant_id = current_tenant["tenant_id"]
    if not session_id.startswith(DASHBOARD_SESSION_PREFIX):
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation = await archival_service.get_full_conversation(session_id, tenant_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = conversation.get("full_messages", conversation.get("messages", []))
    return {
        "session_id": session_id,
        "messages": [
            {"role": message.get("role"), "content": message.get("content", "")}
            for message in messages
            if message.get("role") in {"user", "assistant"}
        ],
    }


@router.get("/students")
async def search_students(
    query: str = Query("", max_length=100),
    limit: int = Query(25, ge=1, le=50),
    current_tenant: dict = Depends(get_current_tenant),
):
    """Search only the authenticated tenant's students by name or admission no."""
    tenant_id = current_tenant["tenant_id"]
    filters: dict = {"tenant_id": tenant_id}
    cleaned_query = query.strip()
    if cleaned_query:
        safe_query = re.escape(cleaned_query)
        filters["$or"] = [
            {"student_name": {"$regex": safe_query, "$options": "i"}},
            {"admission_no": {"$regex": safe_query, "$options": "i"}},
        ]

    projection = {
        "_id": 0,
        "student_id": 1,
        "school_id": 1,
        "admission_no": 1,
        "student_name": 1,
        "class_id": 1,
        "section_id": 1,
    }
    total_count = await db.school_students.count_documents(filters)
    rows = await db.school_students.find(filters, projection).sort(
        [("student_name", 1), ("student_id", 1)]
    ).limit(limit).to_list(length=limit)

    return {
        "items": serialize_documents(rows),
        "total_count": total_count,
        "returned_count": len(rows),
        "has_more": total_count > len(rows),
    }


@router.get("/students/{student_id}")
async def get_student_record(
    student_id: int,
    current_tenant: dict = Depends(get_current_tenant),
):
    """Return the facts behind a student-level School Agent answer."""
    tenant_id = current_tenant["tenant_id"]
    student = await db.school_students.find_one(
        {"tenant_id": tenant_id, "student_id": student_id}, {"_id": 0}
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    school_id = student.get("school_id")
    class_id = student.get("class_id")
    section_id = student.get("section_id")

    school, school_class, section, fees, payments, transport, hostel, due_report = await asyncio.gather(
        db.schools.find_one({"tenant_id": tenant_id, "school_id": school_id}, {"_id": 0, "school_name": 1}),
        db.school_classes.find_one({"tenant_id": tenant_id, "class_id": class_id}, {"_id": 0, "class_name": 1}),
        db.school_sections.find_one({"tenant_id": tenant_id, "section_id": section_id}, {"_id": 0, "section_name": 1}),
        db.school_applied_fees.find(
            {"tenant_id": tenant_id, "student_id": student_id}, {"_id": 0}
        ).sort("applied_fee_id", 1).to_list(length=200),
        db.school_payments.find(
            {"tenant_id": tenant_id, "student_id": student_id}, {"_id": 0}
        ).sort([("payment_date", -1), ("payment_id", -1)]).to_list(length=200),
        db.school_transport_assign.find_one({"tenant_id": tenant_id, "student_id": student_id}, {"_id": 0}),
        db.school_hostel_assign.find_one({"tenant_id": tenant_id, "student_id": student_id}, {"_id": 0}),
        school_data_engine.get_report(
            tenant_id=tenant_id,
            report_id="due_fees_by_student",
            filters={"student_id": student_id},
            limit=1,
        ),
    )

    route = stop = None
    if transport:
        route, stop = await asyncio.gather(
            db.school_routes.find_one(
                {"tenant_id": tenant_id, "route_id": transport.get("route_id")},
                {"_id": 0, "route_name": 1, "route_code": 1},
            ),
            db.school_stops.find_one(
                {"tenant_id": tenant_id, "stop_id": transport.get("stop_id")},
                {"_id": 0, "stop_name": 1},
            ),
        )

    fees = serialize_documents(fees)
    payments = serialize_documents(payments)
    net_assigned = sum((to_decimal(fee.get("amount")) - to_decimal(fee.get("concession")) for fee in fees), Decimal("0"))
    total_paid = sum((to_decimal(payment.get("paid_amount")) for payment in payments), Decimal("0"))
    due_row = due_report["rows"][0] if due_report["rows"] else None

    return {
        "student": serialize_documents([student])[0],
        "school": school or {},
        "class": school_class or {},
        "section": section or {},
        "fees": fees,
        "payments": payments,
        "transport": {**(transport or {}), "route": route or {}, "stop": stop or {}},
        "hostel": hostel or {},
        "summary": {
            "net_assigned": _money(net_assigned),
            "total_paid": _money(total_paid),
            "agent_due": due_row.get("due_amount", "0") if due_row else "0",
            "due_fee_records": due_row.get("fee_record_count", 0) if due_row else 0,
            "calculation_basis": due_report["calculation_basis"],
            "statuses": due_report["statuses"],
        },
    }
