"""Metadata registry for scalable School ERP querying.

The agent should not need one tool per MongoDB collection. This registry
describes entities, fields, and relationships so a small set of generic tools
can validate and run safe queries across many school data tables.
"""

from dataclasses import dataclass, field
from typing import Any


SAFE_OPERATORS = {"$eq", "$regex", "$in", "$ne", "$gt", "$gte", "$lt", "$lte"}


@dataclass(frozen=True)
class FieldSpec:
    type: str
    operators: tuple[str, ...] = ("$eq",)
    searchable: bool = False
    sortable: bool = False


@dataclass(frozen=True)
class RelationshipSpec:
    entity: str
    local_key: str
    foreign_key: str
    type: str = "one_to_many"


@dataclass(frozen=True)
class EntitySpec:
    entity: str
    collection: str
    primary_key: str
    display_name: str
    fields: dict[str, FieldSpec]
    default_projection: tuple[str, ...]
    relationships: dict[str, RelationshipSpec] = field(default_factory=dict)

    @property
    def allowed_fields(self) -> set[str]:
        return set(self.fields)

    @property
    def sortable_fields(self) -> set[str]:
        return {name for name, spec in self.fields.items() if spec.sortable}


def _field(
    field_type: str,
    operators: tuple[str, ...] = ("$eq",),
    *,
    searchable: bool = False,
    sortable: bool = False,
) -> FieldSpec:
    return FieldSpec(field_type, operators, searchable, sortable)


SCHOOL_ENTITY_REGISTRY: dict[str, EntitySpec] = {
    "school": EntitySpec(
        entity="school",
        collection="schools",
        primary_key="school_id",
        display_name="School",
        fields={
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_name": _field("string", ("$eq", "$regex"), searchable=True, sortable=True),
        },
        default_projection=("school_id", "school_name"),
    ),
    "class": EntitySpec(
        entity="class",
        collection="school_classes",
        primary_key="class_id",
        display_name="Class",
        fields={
            "class_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "class_name": _field("string", ("$eq", "$regex", "$in"), searchable=True, sortable=True),
        },
        default_projection=("class_id", "school_id", "class_name"),
        relationships={
            "sections": RelationshipSpec("section", "class_id", "class_id"),
            "students": RelationshipSpec("student", "class_id", "class_id"),
        },
    ),
    "section": EntitySpec(
        entity="section",
        collection="school_sections",
        primary_key="section_id",
        display_name="Section",
        fields={
            "section_id": _field("number", ("$eq", "$in"), sortable=True),
            "class_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "section_name": _field("string", ("$eq", "$regex", "$in"), searchable=True, sortable=True),
        },
        default_projection=("section_id", "class_id", "school_id", "section_name"),
        relationships={
            "students": RelationshipSpec("student", "section_id", "section_id"),
            "class": RelationshipSpec("class", "class_id", "class_id", "many_to_one"),
        },
    ),
    "student": EntitySpec(
        entity="student",
        collection="school_students",
        primary_key="student_id",
        display_name="Student",
        fields={
            "student_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "admission_no": _field("string", ("$eq", "$regex", "$in"), searchable=True, sortable=True),
            "student_name": _field("string", ("$eq", "$regex", "$in"), searchable=True, sortable=True),
            "father_name": _field("string", ("$eq", "$regex"), searchable=True),
            "mother_name": _field("string", ("$eq", "$regex"), searchable=True),
            "gender": _field("string", ("$eq", "$in")),
            "blood_group": _field("string", ("$eq", "$in")),
            "category": _field("string", ("$eq", "$in")),
            "address": _field("string", ("$eq", "$regex"), searchable=True),
            "class_id": _field("number", ("$eq", "$in"), sortable=True),
            "section_id": _field("number", ("$eq", "$in"), sortable=True),
        },
        default_projection=("student_id", "admission_no", "student_name", "class_id", "section_id"),
        relationships={
            "fees": RelationshipSpec("applied_fee", "student_id", "student_id"),
            "payments": RelationshipSpec("payment", "student_id", "student_id"),
            "transport": RelationshipSpec("transport_assignment", "student_id", "student_id"),
            "hostel": RelationshipSpec("hostel_assignment", "student_id", "student_id"),
            "class": RelationshipSpec("class", "class_id", "class_id", "many_to_one"),
            "section": RelationshipSpec("section", "section_id", "section_id", "many_to_one"),
        },
    ),
    "route": EntitySpec(
        entity="route",
        collection="school_routes",
        primary_key="route_id",
        display_name="Route",
        fields={
            "route_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "route_name": _field("string", ("$eq", "$regex"), searchable=True, sortable=True),
            "route_code": _field("string", ("$eq", "$regex"), searchable=True, sortable=True),
        },
        default_projection=("route_id", "school_id", "route_name", "route_code"),
        relationships={
            "stops": RelationshipSpec("stop", "route_id", "route_id"),
            "transport_assignments": RelationshipSpec("transport_assignment", "route_id", "route_id"),
        },
    ),
    "stop": EntitySpec(
        entity="stop",
        collection="school_stops",
        primary_key="stop_id",
        display_name="Stop",
        fields={
            "stop_id": _field("number", ("$eq", "$in"), sortable=True),
            "route_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "stop_name": _field("string", ("$eq", "$regex"), searchable=True, sortable=True),
        },
        default_projection=("stop_id", "route_id", "school_id", "stop_name"),
        relationships={
            "route": RelationshipSpec("route", "route_id", "route_id", "many_to_one"),
            "transport_assignments": RelationshipSpec("transport_assignment", "stop_id", "stop_id"),
        },
    ),
    "transport_assignment": EntitySpec(
        entity="transport_assignment",
        collection="school_transport_assign",
        primary_key="transport_id",
        display_name="Transport Assignment",
        fields={
            "transport_id": _field("number", ("$eq", "$in"), sortable=True),
            "student_id": _field("number", ("$eq", "$in"), sortable=True),
            "route_id": _field("number", ("$eq", "$in"), sortable=True),
            "stop_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "vehicle_no": _field("string", ("$eq", "$regex", "$in"), searchable=True),
            "transport_status": _field("string", ("$eq", "$regex", "$in")),
        },
        default_projection=("transport_id", "student_id", "route_id", "stop_id", "vehicle_no", "transport_status"),
        relationships={
            "student": RelationshipSpec("student", "student_id", "student_id", "many_to_one"),
            "route": RelationshipSpec("route", "route_id", "route_id", "many_to_one"),
            "stop": RelationshipSpec("stop", "stop_id", "stop_id", "many_to_one"),
        },
    ),
    "hostel_assignment": EntitySpec(
        entity="hostel_assignment",
        collection="school_hostel_assign",
        primary_key="hostel_id",
        display_name="Hostel Assignment",
        fields={
            "hostel_id": _field("number", ("$eq", "$in"), sortable=True),
            "student_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "hostel_name": _field("string", ("$eq", "$regex", "$in"), searchable=True),
            "room_no": _field("string", ("$eq", "$regex", "$in"), searchable=True, sortable=True),
            "bed_no": _field("number", ("$eq", "$in"), sortable=True),
            "hostel_status": _field("string", ("$eq", "$regex", "$in")),
            "block": _field("string", ("$eq", "$regex", "$in"), searchable=True),
        },
        default_projection=("hostel_id", "student_id", "hostel_name", "room_no", "bed_no", "hostel_status"),
        relationships={
            "student": RelationshipSpec("student", "student_id", "student_id", "many_to_one"),
        },
    ),
    "applied_fee": EntitySpec(
        entity="applied_fee",
        collection="school_applied_fees",
        primary_key="applied_fee_id",
        display_name="Applied Fee",
        fields={
            "applied_fee_id": _field("number", ("$eq", "$in"), sortable=True),
            "student_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "fee_head": _field("string", ("$eq", "$in")),
            "amount": _field("money", ("$eq", "$gt", "$gte", "$lt", "$lte"), sortable=True),
            "concession": _field("money", ("$eq", "$gt", "$gte", "$lt", "$lte"), sortable=True),
            "status": _field("string", ("$eq", "$in")),
            "due_date": _field("string", ("$eq", "$gt", "$gte", "$lt", "$lte"), sortable=True),
        },
        default_projection=("applied_fee_id", "student_id", "fee_head", "amount", "concession", "status", "due_date"),
        relationships={
            "student": RelationshipSpec("student", "student_id", "student_id", "many_to_one"),
            "payments": RelationshipSpec("payment", "applied_fee_id", "applied_fee_id"),
        },
    ),
    "payment": EntitySpec(
        entity="payment",
        collection="school_payments",
        primary_key="payment_id",
        display_name="Payment",
        fields={
            "payment_id": _field("number", ("$eq", "$in"), sortable=True),
            "student_id": _field("number", ("$eq", "$in"), sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "applied_fee_id": _field("number", ("$eq", "$in"), sortable=True),
            "paid_amount": _field("money", ("$eq", "$gt", "$gte", "$lt", "$lte"), sortable=True),
            "payment_date": _field("string", ("$eq", "$gt", "$gte", "$lt", "$lte"), sortable=True),
            "payment_mode": _field("string", ("$eq", "$in")),
            "receipt_no": _field("string", ("$eq", "$regex", "$in"), searchable=True),
            "balance": _field("money", ("$eq", "$gt", "$gte", "$lt", "$lte"), sortable=True),
        },
        default_projection=("payment_id", "student_id", "applied_fee_id", "paid_amount", "payment_date", "payment_mode", "receipt_no"),
        relationships={
            "student": RelationshipSpec("student", "student_id", "student_id", "many_to_one"),
            "applied_fee": RelationshipSpec("applied_fee", "applied_fee_id", "applied_fee_id", "many_to_one"),
        },
    ),
    "teacher": EntitySpec(
        entity="teacher",
        collection="school_teachers",
        primary_key="teacher_id",
        display_name="Teacher",
        fields={
            "teacher_id": _field("number", ("$eq", "$in"), sortable=True),
            "teacher_name": _field("string", ("$eq", "$regex", "$in"), searchable=True, sortable=True),
            "school_id": _field("number", ("$eq", "$in"), sortable=True),
            "email": _field("string", ("$eq", "$regex", "$in"), searchable=True),
            "status": _field("string", ("$eq", "$regex", "$in")),
        },
        default_projection=("teacher_id", "teacher_name", "school_id", "email", "status"),
    ),
}


ENTITY_ALIASES = {
    "schools": "school",
    "classes": "class",
    "school_classes": "class",
    "sections": "section",
    "school_sections": "section",
    "students": "student",
    "school_students": "student",
    "fees": "applied_fee",
    "fee": "applied_fee",
    "applied_fees": "applied_fee",
    "school_applied_fees": "applied_fee",
    "payments": "payment",
    "school_payments": "payment",
    "routes": "route",
    "school_routes": "route",
    "stops": "stop",
    "school_stops": "stop",
    "transport": "transport_assignment",
    "transport_assign": "transport_assignment",
    "school_transport_assign": "transport_assignment",
    "hostel": "hostel_assignment",
    "hostel_assign": "hostel_assignment",
    "school_hostel_assign": "hostel_assignment",
    "teachers": "teacher",
    "school_teachers": "teacher",
}


def normalize_entity_name(entity: str) -> str:
    normalized = entity.strip().lower()
    return ENTITY_ALIASES.get(normalized, normalized)


def get_entity_spec(entity: str) -> EntitySpec:
    normalized = normalize_entity_name(entity)
    try:
        return SCHOOL_ENTITY_REGISTRY[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown school entity: {entity}") from exc


def explain_entity(entity: str) -> dict[str, Any]:
    spec = get_entity_spec(entity)
    return {
        "entity": spec.entity,
        "collection": spec.collection,
        "primary_key": spec.primary_key,
        "display_name": spec.display_name,
        "fields": {
            name: {
                "type": field.type,
                "operators": list(field.operators),
                "searchable": field.searchable,
                "sortable": field.sortable,
            }
            for name, field in spec.fields.items()
        },
        "default_projection": list(spec.default_projection),
        "relationships": {
            name: {
                "entity": rel.entity,
                "local_key": rel.local_key,
                "foreign_key": rel.foreign_key,
                "type": rel.type,
            }
            for name, rel in spec.relationships.items()
        },
    }
