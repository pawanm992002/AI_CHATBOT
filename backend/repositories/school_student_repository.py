"""CRUD repository for School ERP students."""

import re
from core.auth import db


MAX_LIMIT = 20


class SchoolStudentRepository:

    async def search_students(
        self, tenant_id: str, query: str = "", class_id: int | None = None, limit: int = MAX_LIMIT
    ) -> list[dict]:
        conditions: list[dict] = [{"tenant_id": tenant_id}]
        if query:
            escaped = re.escape(query)
            conditions.append({
                "$or": [
                    {"student_name": {"$regex": escaped, "$options": "i"}},
                    {"admission_no": {"$regex": f"^{escaped}", "$options": "i"}},
                    {"father_name": {"$regex": escaped, "$options": "i"}},
                    {"mother_name": {"$regex": escaped, "$options": "i"}},
                ]
            })
        if class_id is not None:
            conditions.append({"class_id": class_id})
        filter_query = {"$and": conditions} if len(conditions) > 1 else conditions[0]
        cursor = db.school_students.find(filter_query).sort("student_name", 1).limit(min(limit, MAX_LIMIT))
        return await cursor.to_list(length=MAX_LIMIT)

    async def get_student(self, tenant_id: str, student_id: int) -> dict | None:
        return await db.school_students.find_one({"tenant_id": tenant_id, "student_id": student_id})

    async def get_student_by_admission(self, tenant_id: str, admission_no: str) -> dict | None:
        return await db.school_students.find_one({"tenant_id": tenant_id, "admission_no": admission_no})

    async def get_students_by_class(self, tenant_id: str, class_id: int, section_id: int | None = None, limit: int = MAX_LIMIT) -> list[dict]:
        query: dict = {"tenant_id": tenant_id, "class_id": class_id}
        if section_id is not None:
            query["section_id"] = section_id
        cursor = db.school_students.find(query).sort("student_name", 1).limit(min(limit, MAX_LIMIT))
        return await cursor.to_list(length=MAX_LIMIT)
