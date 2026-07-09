"""CRUD repository for School ERP fees and payments."""

from core.auth import db


MAX_LIMIT = 20


class SchoolFeeRepository:

    async def get_fees_by_student(self, tenant_id: str, student_id: int, limit: int = MAX_LIMIT) -> list[dict]:
        cursor = db.school_applied_fees.find(
            {"tenant_id": tenant_id, "student_id": student_id}
        ).sort("applied_fee_id", 1).limit(min(limit, MAX_LIMIT))
        return await cursor.to_list(length=MAX_LIMIT)

    async def get_fees_by_status(self, tenant_id: str, status: str, limit: int = MAX_LIMIT) -> list[dict]:
        cursor = db.school_applied_fees.find(
            {"tenant_id": tenant_id, "status": {"$regex": f"^{status}$", "$options": "i"}}
        ).sort("due_date", 1).limit(min(limit, MAX_LIMIT))
        return await cursor.to_list(length=MAX_LIMIT)

    async def get_payments_by_student(self, tenant_id: str, student_id: int, limit: int = MAX_LIMIT) -> list[dict]:
        cursor = db.school_payments.find(
            {"tenant_id": tenant_id, "student_id": student_id}
        ).sort("payment_date", -1).limit(min(limit, MAX_LIMIT))
        return await cursor.to_list(length=MAX_LIMIT)
