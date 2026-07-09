"""CRUD repository for School ERP hostel assignments."""

from core.auth import db


class SchoolHostelRepository:

    async def get_hostel_by_student(self, tenant_id: str, student_id: int) -> dict | None:
        return await db.school_hostel_assign.find_one(
            {"tenant_id": tenant_id, "student_id": student_id}
        )
