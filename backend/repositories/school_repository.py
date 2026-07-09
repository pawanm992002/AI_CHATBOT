"""CRUD repository for School ERP reference data (schools, classes, sections)."""

from core.auth import db


MAX_LIMIT = 20


class SchoolRepository:

    async def get_school(self, tenant_id: str) -> dict | None:
        return await db.schools.find_one({"tenant_id": tenant_id})

    async def get_classes(self, tenant_id: str, school_id: int | None = None, limit: int = MAX_LIMIT) -> list[dict]:
        query: dict = {"tenant_id": tenant_id}
        if school_id is not None:
            query["school_id"] = school_id
        cursor = db.school_classes.find(query).sort("class_id", 1).limit(min(limit, MAX_LIMIT))
        return await cursor.to_list(length=MAX_LIMIT)

    async def get_class_by_id(self, tenant_id: str, class_id: int) -> dict | None:
        return await db.school_classes.find_one({"tenant_id": tenant_id, "class_id": class_id})

    async def get_sections(self, tenant_id: str, class_id: int | None = None, limit: int = MAX_LIMIT) -> list[dict]:
        query: dict = {"tenant_id": tenant_id}
        if class_id is not None:
            query["class_id"] = class_id
        cursor = db.school_sections.find(query).sort("section_id", 1).limit(min(limit, MAX_LIMIT))
        return await cursor.to_list(length=MAX_LIMIT)
