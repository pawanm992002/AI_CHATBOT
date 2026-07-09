"""CRUD repository for School ERP transport data (routes, stops, assignments)."""

from core.auth import db


MAX_LIMIT = 20


class SchoolTransportRepository:

    async def get_routes(self, tenant_id: str, limit: int = MAX_LIMIT) -> list[dict]:
        cursor = db.school_routes.find({"tenant_id": tenant_id}).sort("route_name", 1).limit(min(limit, MAX_LIMIT))
        return await cursor.to_list(length=MAX_LIMIT)

    async def get_stops(self, tenant_id: str, route_id: int | None = None, limit: int = MAX_LIMIT) -> list[dict]:
        query: dict = {"tenant_id": tenant_id}
        if route_id is not None:
            query["route_id"] = route_id
        cursor = db.school_stops.find(query).sort("stop_name", 1).limit(min(limit, MAX_LIMIT))
        return await cursor.to_list(length=MAX_LIMIT)

    async def get_transport_by_student(self, tenant_id: str, student_id: int) -> dict | None:
        return await db.school_transport_assign.find_one(
            {"tenant_id": tenant_id, "student_id": student_id}
        )
