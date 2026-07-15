import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, List
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from core.auth import db
from core.config import settings
from services.school_data_filter import build_safe_filter
from services.school_data_engine import school_data_engine


def school_write_actions_enabled() -> bool:
    import os

    env_val = os.environ.get("SCHOOL_WRITE_ACTIONS_ENABLED")
    if env_val is not None:
        return env_val.strip().lower() in {"1", "true", "yes", "on"}
    return settings.SCHOOL_WRITE_ACTIONS_ENABLED is True

def serialize_value(v: Any) -> Any:
    from bson.decimal128 import Decimal128
    if isinstance(v, Decimal128):
        return str(v.to_decimal())
    return v

def serialize_results(results: List[dict]) -> List[dict]:
    serialized = []
    for row in results:
        serialized.append({k: serialize_value(v) for k, v in row.items()})
    return serialized

async def log_tool_invocation(
    config: RunnableConfig,
    tool_name: str,
    generated_filter: dict,
) -> None:
    """Log every tool invocation for audit purposes."""
    try:
        configurable = config.get("configurable", {})
        tenant_id = configurable.get("tenant_id", "unknown")
        session_id = configurable.get("session_id", "unknown")
        question = configurable.get("question", "Tool invocation")
        
        log_doc = {
            "log_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "session_id": session_id,
            "question": question[:500],
            "generated_filter": generated_filter,
            "tool_name": tool_name,
            "timestamp": datetime.now(timezone.utc),
        }
        await db.school_data_query_log.insert_one(log_doc)
        try:
            await db.school_audit_log.insert_one(log_doc)
        except Exception:
            pass
    except Exception as e:
        print(f"[SCHOOL_DATA_TOOL] Audit log failed: {e}")


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@tool
async def search_school_entity(
    entity: str,
    filters: Optional[List[dict]] = None,
    projection: Optional[List[str]] = None,
    sort: Optional[List[dict]] = None,
    limit: int = 50,
    config: RunnableConfig = None,
) -> str:
    """Safely search any registered school entity. Use entity names like student, class, section, applied_fee, payment, route, stop, transport_assignment, hostel_assignment, teacher. Filters are structured dicts: field/op/value."""
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    result = await school_data_engine.search_entity(
        tenant_id=tenant_id,
        entity=entity,
        filters=filters,
        projection=projection,
        sort=sort,
        limit=limit,
    )
    await log_tool_invocation(config, "search_school_entity", result.get("filter", {}))
    return _json_dumps(result)


@tool
async def get_school_entity_detail(
    entity: str,
    entity_id: Any,
    projection: Optional[List[str]] = None,
    config: RunnableConfig = None,
) -> str:
    """Fetch one registered school entity by its primary key, always scoped to the current tenant."""
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    result = await school_data_engine.get_entity_detail(
        tenant_id=tenant_id,
        entity=entity,
        entity_id=entity_id,
        projection=projection,
    )
    await log_tool_invocation(config, "get_school_entity_detail", result.get("filter", {}))
    return _json_dumps(result)


@tool
async def get_school_related_entities(
    entity: str,
    entity_id: Any,
    relationship: str,
    projection: Optional[List[str]] = None,
    limit: int = 50,
    config: RunnableConfig = None,
) -> str:
    """Fetch related records using registry relationships, e.g. entity='student', relationship='fees' or 'payments'."""
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    result = await school_data_engine.get_related_entities(
        tenant_id=tenant_id,
        entity=entity,
        entity_id=entity_id,
        relationship=relationship,
        projection=projection,
        limit=limit,
    )
    await log_tool_invocation(
        config,
        "get_school_related_entities",
        {
            "entity": entity,
            "entity_id": entity_id,
            "relationship": relationship,
            "tenant_id": tenant_id,
        },
    )
    return _json_dumps(result)


@tool
async def count_school_entities(
    entity: str,
    filters: Optional[List[dict]] = None,
    config: RunnableConfig = None,
) -> str:
    """Count records for a registered school entity with safe filters. Use this for count questions."""
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    result = await school_data_engine.count_entities(
        tenant_id=tenant_id,
        entity=entity,
        filters=filters,
    )
    await log_tool_invocation(config, "count_school_entities", result.get("filter", {}))
    return _json_dumps(result)


@tool
async def get_school_report(
    report_id: str,
    filters: Optional[dict] = None,
    limit: int = 200,
    config: RunnableConfig = None,
) -> str:
    """Run a deterministic school report. For due fee totals, due students, or fee due breakdowns, use report_id='due_fees_by_student'."""
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    result = await school_data_engine.get_report(
        tenant_id=tenant_id,
        report_id=report_id,
        filters=filters,
        limit=limit,
    )
    await log_tool_invocation(
        config,
        "get_school_report",
        {
            "report_id": report_id,
            "filters": filters or {},
            "tenant_id": tenant_id,
            "calculation_basis": result.get("calculation_basis"),
        },
    )
    return _json_dumps(result)


@tool
async def explain_school_schema(
    entity: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """Explain registered school entities, fields, relationships, and available reports."""
    result = school_data_engine.explain_schema(entity)
    await log_tool_invocation(
        config,
        "explain_school_schema",
        {"entity": entity or "*"},
    )
    return _json_dumps(result)

@tool
async def query_students(
    class_id: Optional[int] = None,
    section_id: Optional[int] = None,
    admission_no: Optional[str] = None,
    first_name: Optional[str] = None,
    student_name: Optional[str] = None,
    status: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """Query student records. You can filter by class_id, section_id, admission_no, first_name/student_name."""
    conditions = []
    if class_id is not None:
        conditions.append({"field": "class_id", "op": "$eq", "value": class_id})
    if section_id is not None:
        conditions.append({"field": "section_id", "op": "$eq", "value": section_id})
    if admission_no is not None:
        conditions.append({"field": "admission_no", "op": "$eq", "value": admission_no})
    if first_name is not None:
        conditions.append({"field": "student_name", "op": "$regex", "value": first_name})
    if student_name is not None:
        conditions.append({"field": "student_name", "op": "$regex", "value": student_name})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_students", conditions, tenant_id)
    await log_tool_invocation(config, "query_students", safe_filter)
    
    cursor = db.school_students.find(safe_filter, {"_id": 0}).limit(20)
    results = await cursor.to_list(length=20)
    return str(serialize_results(results))

@tool
async def query_classes(
    class_name: Optional[str] = None,
    school_id: Optional[int] = None,
    config: RunnableConfig = None,
) -> str:
    """Query class records by class_name or school_id."""
    conditions = []
    if class_name is not None:
        conditions.append({"field": "class_name", "op": "$regex", "value": class_name})
    if school_id is not None:
        conditions.append({"field": "school_id", "op": "$eq", "value": school_id})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_classes", conditions, tenant_id)
    await log_tool_invocation(config, "query_classes", safe_filter)
    
    cursor = db.school_classes.find(safe_filter, {"_id": 0}).limit(20)
    results = await cursor.to_list(length=20)
    return str(serialize_results(results))

@tool
async def query_sections(
    section_name: Optional[str] = None,
    class_id: Optional[int] = None,
    school_id: Optional[int] = None,
    config: RunnableConfig = None,
) -> str:
    """Query section records by section_name, class_id, or school_id."""
    conditions = []
    if section_name is not None:
        conditions.append({"field": "section_name", "op": "$regex", "value": section_name})
    if class_id is not None:
        conditions.append({"field": "class_id", "op": "$eq", "value": class_id})
    if school_id is not None:
        conditions.append({"field": "school_id", "op": "$eq", "value": school_id})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_sections", conditions, tenant_id)
    await log_tool_invocation(config, "query_sections", safe_filter)
    
    cursor = db.school_sections.find(safe_filter, {"_id": 0}).limit(20)
    results = await cursor.to_list(length=20)
    return str(serialize_results(results))

@tool
async def query_teachers(
    teacher_name: Optional[str] = None,
    school_id: Optional[int] = None,
    config: RunnableConfig = None,
) -> str:
    """Query teacher records (currently placeholder)."""
    conditions = []
    if teacher_name is not None:
        conditions.append({"field": "teacher_name", "op": "$regex", "value": teacher_name})
    if school_id is not None:
        conditions.append({"field": "school_id", "op": "$eq", "value": school_id})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_teachers", conditions, tenant_id)
    await log_tool_invocation(config, "query_teachers", safe_filter)
    
    try:
        cursor = db.school_teachers.find(safe_filter, {"_id": 0}).limit(20)
        results = await cursor.to_list(length=20)
    except Exception:
        results = []
    return str(serialize_results(results))

@tool
async def query_applied_fees(
    student_id: Optional[int] = None,
    status: Optional[str] = None,
    due_date: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """Query applied fees. status can be 'Paid', 'Pending', or 'Partial'."""
    conditions = []
    if student_id is not None:
        conditions.append({"field": "student_id", "op": "$eq", "value": student_id})
    if status is not None:
        conditions.append({"field": "status", "op": "$eq", "value": status})
    if due_date is not None:
        conditions.append({"field": "due_date", "op": "$eq", "value": due_date})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_applied_fees", conditions, tenant_id)
    await log_tool_invocation(config, "query_applied_fees", safe_filter)
    
    cursor = db.school_applied_fees.find(safe_filter, {"_id": 0}).limit(20)
    results = await cursor.to_list(length=20)
    return str(serialize_results(results))

@tool
async def query_payments(
    student_id: Optional[int] = None,
    mode: Optional[str] = None,
    reference_no: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """Query payments records."""
    conditions = []
    if student_id is not None:
        conditions.append({"field": "student_id", "op": "$eq", "value": student_id})
    if mode is not None:
        conditions.append({"field": "payment_mode", "op": "$eq", "value": mode})
    if reference_no is not None:
        conditions.append({"field": "receipt_no", "op": "$eq", "value": reference_no})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_payments", conditions, tenant_id)
    await log_tool_invocation(config, "query_payments", safe_filter)
    
    cursor = db.school_payments.find(safe_filter, {"_id": 0}).limit(20)
    results = await cursor.to_list(length=20)
    return str(serialize_results(results))

@tool
async def query_routes(
    route_name: Optional[str] = None,
    route_code: Optional[str] = None,
    school_id: Optional[int] = None,
    config: RunnableConfig = None,
) -> str:
    """Query transport routes."""
    conditions = []
    if route_name is not None:
        conditions.append({"field": "route_name", "op": "$regex", "value": route_name})
    if route_code is not None:
        conditions.append({"field": "route_code", "op": "$regex", "value": route_code})
    if school_id is not None:
        conditions.append({"field": "school_id", "op": "$eq", "value": school_id})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_routes", conditions, tenant_id)
    await log_tool_invocation(config, "query_routes", safe_filter)
    
    cursor = db.school_routes.find(safe_filter, {"_id": 0}).limit(20)
    results = await cursor.to_list(length=20)
    return str(serialize_results(results))

@tool
async def query_stops(
    route_id: Optional[int] = None,
    stop_name: Optional[str] = None,
    school_id: Optional[int] = None,
    config: RunnableConfig = None,
) -> str:
    """Query bus stops."""
    conditions = []
    if route_id is not None:
        conditions.append({"field": "route_id", "op": "$eq", "value": route_id})
    if stop_name is not None:
        conditions.append({"field": "stop_name", "op": "$regex", "value": stop_name})
    if school_id is not None:
        conditions.append({"field": "school_id", "op": "$eq", "value": school_id})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_stops", conditions, tenant_id)
    await log_tool_invocation(config, "query_stops", safe_filter)
    
    cursor = db.school_stops.find(safe_filter, {"_id": 0}).limit(20)
    results = await cursor.to_list(length=20)
    return str(serialize_results(results))

@tool
async def query_transport_assign(
    student_id: Optional[int] = None,
    stop_id: Optional[int] = None,
    route_id: Optional[int] = None,
    status: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """Query transport assignment details for students."""
    conditions = []
    if student_id is not None:
        conditions.append({"field": "student_id", "op": "$eq", "value": student_id})
    if stop_id is not None:
        conditions.append({"field": "stop_id", "op": "$eq", "value": stop_id})
    if route_id is not None:
        conditions.append({"field": "route_id", "op": "$eq", "value": route_id})
    if status is not None:
        conditions.append({"field": "transport_status", "op": "$eq", "value": status})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_transport_assign", conditions, tenant_id)
    await log_tool_invocation(config, "query_transport_assign", safe_filter)
    
    cursor = db.school_transport_assign.find(safe_filter, {"_id": 0}).limit(20)
    results = await cursor.to_list(length=20)
    return str(serialize_results(results))

@tool
async def query_hostel_assign(
    student_id: Optional[int] = None,
    room_no: Optional[str] = None,
    block: Optional[str] = None,
    status: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """Query hostel assignments."""
    conditions = []
    if student_id is not None:
        conditions.append({"field": "student_id", "op": "$eq", "value": student_id})
    if room_no is not None:
        conditions.append({"field": "room_no", "op": "$eq", "value": room_no})
    if block is not None:
        conditions.append({"field": "block", "op": "$eq", "value": block})
    if status is not None:
        conditions.append({"field": "hostel_status", "op": "$eq", "value": status})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_hostel_assign", conditions, tenant_id)
    await log_tool_invocation(config, "query_hostel_assign", safe_filter)
    
    cursor = db.school_hostel_assign.find(safe_filter, {"_id": 0}).limit(20)
    results = await cursor.to_list(length=20)
    return str(serialize_results(results))

@tool
async def resolve_student_id(
    name: str,
    config: RunnableConfig = None,
) -> str:
    """Looks up school_students by fuzzy/partial name match, returns candidate(s) with student_id, student_name, admission_no, class_id, and section_id."""
    conditions = [{"field": "student_name", "op": "$regex", "value": name}]
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_students", conditions, tenant_id)
    await log_tool_invocation(config, "resolve_student_id", safe_filter)
    
    cursor = db.school_students.find(safe_filter, {"_id": 0}).limit(10)
    results = await cursor.to_list(length=10)
    return str(serialize_results(results))

@tool
async def resolve_class_id(
    class_name: str,
    school_id: Optional[int] = None,
    config: RunnableConfig = None,
) -> str:
    """Looks up school_classes by class_name (e.g. 'Class 3' or '3') and returns class_id."""
    cleaned_name = class_name.lower().replace("class", "").strip()
    conditions = [{"field": "class_name", "op": "$regex", "value": cleaned_name}]
    if school_id is not None:
        conditions.append({"field": "school_id", "op": "$eq", "value": school_id})
        
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    safe_filter = build_safe_filter("school_classes", conditions, tenant_id)
    await log_tool_invocation(config, "resolve_class_id", safe_filter)
    
    cursor = db.school_classes.find(safe_filter, {"_id": 0}).limit(10)
    results = await cursor.to_list(length=10)
    return str(serialize_results(results))

@tool
async def update_transport_status(
    transport_id: int,
    status: str,
    config: RunnableConfig = None,
) -> str:
    """Updates the transport assignment status. Requires approval."""
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    await log_tool_invocation(config, "update_transport_status", {"transport_id": transport_id, "status": status})
    
    if not school_write_actions_enabled():
        return "Write actions are disabled by default. Set SCHOOL_WRITE_ACTIONS_ENABLED=True to enable."
        
    result = await db.school_transport_assign.update_one(
        {"tenant_id": tenant_id, "transport_id": transport_id},
        {"$set": {"transport_status": status}}
    )
    if result.modified_count > 0:
        return f"Successfully updated transport_id {transport_id} status to {status}."
    return f"Failed to update transport_id {transport_id}. Record not found or no change."

@tool
async def update_hostel_status(
    hostel_id: int,
    status: str,
    config: RunnableConfig = None,
) -> str:
    """Updates the hostel assignment status. Requires approval."""
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    await log_tool_invocation(config, "update_hostel_status", {"hostel_id": hostel_id, "status": status})
    
    if not school_write_actions_enabled():
        return "Write actions are disabled by default. Set SCHOOL_WRITE_ACTIONS_ENABLED=True to enable."
        
    result = await db.school_hostel_assign.update_one(
        {"tenant_id": tenant_id, "hostel_id": hostel_id},
        {"$set": {"hostel_status": status}}
    )
    if result.modified_count > 0:
        return f"Successfully updated hostel_id {hostel_id} status to {status}."
    return f"Failed to update hostel_id {hostel_id}. Record not found or no change."

@tool
async def update_fee_status(
    applied_fee_id: int,
    status: str,
    config: RunnableConfig = None,
) -> str:
    """Updates the applied fee status. Requires approval."""
    tenant_id = config.get("configurable", {}).get("tenant_id", "")
    await log_tool_invocation(config, "update_fee_status", {"applied_fee_id": applied_fee_id, "status": status})
    
    if not school_write_actions_enabled():
        return "Write actions are disabled by default. Set SCHOOL_WRITE_ACTIONS_ENABLED=True to enable."
        
    result = await db.school_applied_fees.update_one(
        {"tenant_id": tenant_id, "applied_fee_id": applied_fee_id},
        {"$set": {"status": status}}
    )
    if result.modified_count > 0:
        return f"Successfully updated applied_fee_id {applied_fee_id} status to {status}."
    return f"Failed to update applied_fee_id {applied_fee_id}. Record not found or no change."

READ_TOOLS = [
    search_school_entity,
    get_school_entity_detail,
    get_school_related_entities,
    count_school_entities,
    get_school_report,
    explain_school_schema,
    query_students,
    query_classes,
    query_sections,
    query_teachers,
    query_applied_fees,
    query_payments,
    query_routes,
    query_stops,
    query_transport_assign,
    query_hostel_assign,
    resolve_student_id,
    resolve_class_id,
]

WRITE_TOOLS = [
    update_transport_status,
    update_hostel_status,
    update_fee_status,
]

ALL_TOOLS = READ_TOOLS + WRITE_TOOLS
WRITE_TOOL_NAMES = {t.name for t in WRITE_TOOLS}
tools_by_name = {t.name: t for t in ALL_TOOLS}
