"""Registry-backed tools for the School ERP LangGraph agent."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from core.auth import db
from core.config import settings
from services.school_data_engine import school_data_engine


def school_write_actions_enabled() -> bool:
    import os

    env_val = os.environ.get("SCHOOL_WRITE_ACTIONS_ENABLED")
    if env_val is not None:
        return env_val.strip().lower() in {"1", "true", "yes", "on"}
    return settings.SCHOOL_WRITE_ACTIONS_ENABLED is True


def _config_value(config: RunnableConfig | None, key: str, default: str = "") -> str:
    return (config or {}).get("configurable", {}).get(key, default)


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


async def log_tool_invocation(
    config: RunnableConfig | None,
    tool_name: str,
    generated_filter: dict[str, Any],
) -> None:
    """Record each tool invocation in both School ERP audit collections."""
    try:
        log_doc = {
            "log_id": str(uuid.uuid4()),
            "tenant_id": _config_value(config, "tenant_id", "unknown"),
            "session_id": _config_value(config, "session_id", "unknown"),
            "question": _config_value(config, "question", "Tool invocation")[:500],
            "generated_filter": generated_filter,
            "tool_name": tool_name,
            "timestamp": datetime.now(timezone.utc),
        }
        await db.school_data_query_log.insert_one(log_doc)
        await db.school_audit_log.insert_one(log_doc)
    except Exception as exc:
        print(f"[SCHOOL_DATA_TOOL] Audit log failed: {exc}")


@tool
async def search_school_entity(
    entity: str,
    filters: list[dict[str, Any]] | None = None,
    projection: list[str] | None = None,
    sort: list[dict[str, Any]] | None = None,
    limit: int = 50,
    config: RunnableConfig = None,
) -> str:
    """Safely search a registered entity using field/op/value filters. Entities include student, class, section, applied_fee, payment, route, stop, transport_assignment, hostel_assignment, and teacher."""
    result = await school_data_engine.search_entity(
        tenant_id=_config_value(config, "tenant_id"),
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
    projection: list[str] | None = None,
    config: RunnableConfig = None,
) -> str:
    """Fetch one registered entity by primary key, always scoped to the current tenant."""
    result = await school_data_engine.get_entity_detail(
        tenant_id=_config_value(config, "tenant_id"),
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
    projection: list[str] | None = None,
    limit: int = 50,
    config: RunnableConfig = None,
) -> str:
    """Follow a registry relationship, for example student -> fees, payments, transport, hostel, class, or section."""
    tenant_id = _config_value(config, "tenant_id")
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
        {"entity": entity, "entity_id": entity_id, "relationship": relationship, "tenant_id": tenant_id},
    )
    return _json_dumps(result)


@tool
async def count_school_entities(
    entity: str,
    filters: list[dict[str, Any]] | None = None,
    config: RunnableConfig = None,
) -> str:
    """Count a registered entity with safe filters. Use this for count questions."""
    result = await school_data_engine.count_entities(
        tenant_id=_config_value(config, "tenant_id"), entity=entity, filters=filters
    )
    await log_tool_invocation(config, "count_school_entities", result.get("filter", {}))
    return _json_dumps(result)


@tool
async def get_school_report(
    report_id: str,
    filters: dict[str, Any] | None = None,
    limit: int = 200,
    config: RunnableConfig = None,
) -> str:
    """Run a deterministic report. Use due_fees_by_student for due totals, due student lists, and fee breakdowns."""
    tenant_id = _config_value(config, "tenant_id")
    result = await school_data_engine.get_report(
        tenant_id=tenant_id, report_id=report_id, filters=filters, limit=limit
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
    entity: str | None = None,
    config: RunnableConfig = None,
) -> str:
    """Explain registered entities, their allowed fields and relationships, and available reports."""
    result = school_data_engine.explain_schema(entity)
    await log_tool_invocation(config, "explain_school_schema", {"entity": entity or "*"})
    return _json_dumps(result)


@tool
async def resolve_student_id(name: str, config: RunnableConfig = None) -> str:
    """Find student candidates by partial name and return IDs, admission numbers, classes, and sections."""
    result = await school_data_engine.search_entity(
        tenant_id=_config_value(config, "tenant_id"),
        entity="student",
        filters=[{"field": "student_name", "op": "$regex", "value": name}],
        projection=["student_id", "student_name", "admission_no", "class_id", "section_id"],
        limit=10,
    )
    await log_tool_invocation(config, "resolve_student_id", result.get("filter", {}))
    return _json_dumps(result)


@tool
async def resolve_class_id(
    class_name: str,
    school_id: int | None = None,
    config: RunnableConfig = None,
) -> str:
    """Find class candidates by name and return class IDs."""
    filters: list[dict[str, Any]] = [
        {"field": "class_name", "op": "$regex", "value": class_name.lower().replace("class", "").strip()}
    ]
    if school_id is not None:
        filters.append({"field": "school_id", "op": "$eq", "value": school_id})
    result = await school_data_engine.search_entity(
        tenant_id=_config_value(config, "tenant_id"),
        entity="class",
        filters=filters,
        projection=["class_id", "class_name", "school_id"],
        limit=10,
    )
    await log_tool_invocation(config, "resolve_class_id", result.get("filter", {}))
    return _json_dumps(result)


@tool
async def update_transport_status(
    transport_id: int, status: str, config: RunnableConfig = None
) -> str:
    """Update a transport assignment status. Requires human approval and the write feature flag."""
    tenant_id = _config_value(config, "tenant_id")
    await log_tool_invocation(config, "update_transport_status", {"transport_id": transport_id, "status": status})
    if not school_write_actions_enabled():
        return "Write actions are disabled. Set SCHOOL_WRITE_ACTIONS_ENABLED=True to enable them."
    result = await db.school_transport_assign.update_one(
        {"tenant_id": tenant_id, "transport_id": transport_id}, {"$set": {"transport_status": status}}
    )
    return f"Updated transport_id {transport_id} to {status}." if result.modified_count else f"No transport record changed for transport_id {transport_id}."


@tool
async def update_hostel_status(
    hostel_id: int, status: str, config: RunnableConfig = None
) -> str:
    """Update a hostel assignment status. Requires human approval and the write feature flag."""
    tenant_id = _config_value(config, "tenant_id")
    await log_tool_invocation(config, "update_hostel_status", {"hostel_id": hostel_id, "status": status})
    if not school_write_actions_enabled():
        return "Write actions are disabled. Set SCHOOL_WRITE_ACTIONS_ENABLED=True to enable them."
    result = await db.school_hostel_assign.update_one(
        {"tenant_id": tenant_id, "hostel_id": hostel_id}, {"$set": {"hostel_status": status}}
    )
    return f"Updated hostel_id {hostel_id} to {status}." if result.modified_count else f"No hostel record changed for hostel_id {hostel_id}."


@tool
async def update_fee_status(
    applied_fee_id: int, status: str, config: RunnableConfig = None
) -> str:
    """Update an applied fee status. Requires human approval and the write feature flag."""
    tenant_id = _config_value(config, "tenant_id")
    await log_tool_invocation(config, "update_fee_status", {"applied_fee_id": applied_fee_id, "status": status})
    if not school_write_actions_enabled():
        return "Write actions are disabled. Set SCHOOL_WRITE_ACTIONS_ENABLED=True to enable them."
    result = await db.school_applied_fees.update_one(
        {"tenant_id": tenant_id, "applied_fee_id": applied_fee_id}, {"$set": {"status": status}}
    )
    return f"Updated applied_fee_id {applied_fee_id} to {status}." if result.modified_count else f"No applied fee record changed for applied_fee_id {applied_fee_id}."


READ_TOOLS = [
    search_school_entity,
    get_school_entity_detail,
    get_school_related_entities,
    count_school_entities,
    get_school_report,
    explain_school_schema,
    resolve_student_id,
    resolve_class_id,
]

WRITE_TOOLS = [update_transport_status, update_hostel_status, update_fee_status]
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS
WRITE_TOOL_NAMES = {tool_.name for tool_ in WRITE_TOOLS}
tools_by_name = {tool_.name: tool_ for tool_ in ALL_TOOLS}
