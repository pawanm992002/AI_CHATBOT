"""Pydantic v2 schemas for School ERP data entities."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class School(BaseModel):
    school_id: int
    tenant_id: str
    school_name: str


class SchoolClass(BaseModel):
    class_id: int
    tenant_id: str
    school_id: int
    class_name: str


class SchoolSection(BaseModel):
    section_id: int
    tenant_id: str
    school_id: int
    class_id: int
    section_name: str


class SchoolStudent(BaseModel):
    student_id: int
    tenant_id: str
    school_id: int
    admission_no: str
    student_name: str
    father_name: str
    mother_name: str
    gender: str
    blood_group: str
    category: str
    address: str
    class_id: int
    section_id: int


class SchoolRoute(BaseModel):
    route_id: int
    tenant_id: str
    school_id: int
    route_name: str
    route_code: str


class SchoolStop(BaseModel):
    stop_id: int
    tenant_id: str
    school_id: int
    route_id: int
    stop_name: str


class SchoolTransportAssign(BaseModel):
    transport_id: int
    tenant_id: str
    school_id: int
    student_id: int
    route_id: int
    stop_id: int
    vehicle_no: str
    transport_status: str


class SchoolHostelAssign(BaseModel):
    hostel_id: int
    tenant_id: str
    school_id: int
    student_id: int
    hostel_name: str
    room_no: str
    bed_no: int
    hostel_status: str


class SchoolAppliedFee(BaseModel):
    applied_fee_id: int
    tenant_id: str
    school_id: int
    student_id: int
    fee_head: str
    amount: Decimal
    due_date: str
    concession: Decimal
    status: str


class SchoolPayment(BaseModel):
    payment_id: int
    tenant_id: str
    school_id: int
    student_id: int
    applied_fee_id: int
    paid_amount: Decimal
    payment_date: str
    payment_mode: str
    receipt_no: str
    balance: Decimal


class SchoolDataQueryLog(BaseModel):
    log_id: str
    tenant_id: str
    session_id: str
    question: str
    generated_filter: dict
    timestamp: datetime
