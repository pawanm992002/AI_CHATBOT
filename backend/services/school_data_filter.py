"""
Query safety filter for School ERP data service.

All filter construction logic lives here so it can be unit-tested without
importing the heavy auth/db dependencies.
"""

from typing import Any

# ---------------------------------------------------------------------------
# Query safety — per-collection allowlists
# ---------------------------------------------------------------------------

FIELD_ALLOWLIST: dict[str, dict[str, list[str]]] = {
    "schools": {
        "allowed_fields": ["school_name", "school_id"],
        "allowed_ops": ["$eq", "$regex"],
    },
    "school_classes": {
        "allowed_fields": ["class_id", "school_id", "class_name"],
        "allowed_ops": ["$eq", "$regex", "$in"],
    },
    "school_sections": {
        "allowed_fields": ["section_id", "class_id", "school_id", "section_name"],
        "allowed_ops": ["$eq", "$regex", "$in"],
    },
    "school_students": {
        "allowed_fields": [
            "student_id", "admission_no", "student_name",
            "father_name", "mother_name", "gender", "blood_group",
            "category", "class_id", "section_id",
        ],
        "allowed_ops": ["$eq", "$regex", "$in"],
    },
    "school_routes": {
        "allowed_fields": ["route_id", "school_id", "route_name", "route_code"],
        "allowed_ops": ["$eq", "$regex"],
    },
    "school_stops": {
        "allowed_fields": ["stop_id", "route_id", "school_id", "stop_name"],
        "allowed_ops": ["$eq", "$regex"],
    },
    "school_transport_assign": {
        "allowed_fields": ["transport_id", "student_id", "route_id", "stop_id", "vehicle_no", "transport_status"],
        "allowed_ops": ["$eq", "$regex", "$in"],
    },
    "school_hostel_assign": {
        "allowed_fields": ["hostel_id", "student_id", "hostel_name", "room_no", "bed_no", "hostel_status", "transport_status", "block"],
        "allowed_ops": ["$eq", "$regex", "$in"],
    },
    "school_applied_fees": {
        "allowed_fields": ["applied_fee_id", "student_id", "fee_head", "amount", "concession", "status", "due_date"],
        "allowed_ops": ["$eq", "$in"],
    },
    "school_payments": {
        "allowed_fields": ["payment_id", "student_id", "applied_fee_id", "payment_mode", "receipt_no"],
        "allowed_ops": ["$eq", "$in"],
    },
    "school_teachers": {
        "allowed_fields": ["teacher_id", "teacher_name", "school_id", "email", "status"],
        "allowed_ops": ["$eq", "$regex", "$in"],
    },
}


def validate_condition(collection: str, cond: dict[str, Any]) -> dict | None:
    """Validate a single LLM-generated condition against the allowlist.

    Returns a safe Mongo filter fragment, or None if invalid.
    """
    allow = FIELD_ALLOWLIST.get(collection)
    if not allow:
        return None

    field = cond.get("field")
    op = cond.get("op", "$eq")
    value = cond.get("value")

    if field not in allow["allowed_fields"]:
        return None
    if op not in allow["allowed_ops"]:
        return None

    # Reject regex longer than 200 chars
    if op == "$regex":
        val_str = str(value)
        if len(val_str) > 200:
            return None
        return {field: {"$regex": val_str, "$options": "i"}}

    return {field: {op: value}}


def build_safe_filter(
    collection: str,
    conditions: list[dict[str, Any]],
    tenant_id: str,
) -> dict:
    """Build a Mongo filter from validated LLM conditions.

    tenant_id is injected server-side with no path for override.
    """
    safe_conditions = []
    for cond in conditions:
        validated = validate_condition(collection, cond)
        if validated:
            safe_conditions.append(validated)

    if not safe_conditions:
        return {"tenant_id": tenant_id}

    return {"$and": [{"tenant_id": tenant_id}, *safe_conditions]}
