"""CRUD repository for visitor_profiles collection."""

import uuid
from datetime import datetime, timezone

from core.auth import db


class VisitorProfileRepository:
    async def create(self, tenant_id: str, data: dict) -> dict:
        now = datetime.now(timezone.utc)
        doc = {
            "profile_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            **data,
            "created_at": now,
            "updated_at": now,
        }
        await db.visitor_profiles.insert_one(doc)
        return doc

    async def get_by_tenant(self, tenant_id: str) -> list[dict]:
        cursor = db.visitor_profiles.find({"tenant_id": tenant_id}).sort("created_at", -1)
        return await cursor.to_list(length=100)

    async def get_enabled_by_tenant(self, tenant_id: str) -> list[dict]:
        cursor = db.visitor_profiles.find({"tenant_id": tenant_id, "enabled": True})
        return await cursor.to_list(length=100)

    async def get_by_profile_id(self, tenant_id: str, profile_id: str) -> dict | None:
        return await db.visitor_profiles.find_one(
            {"profile_id": profile_id, "tenant_id": tenant_id}
        )

    async def update(self, tenant_id: str, profile_id: str, data: dict) -> bool:
        data["updated_at"] = datetime.now(timezone.utc)
        result = await db.visitor_profiles.update_one(
            {"profile_id": profile_id, "tenant_id": tenant_id},
            {"$set": data},
        )
        return result.modified_count > 0

    async def delete(self, tenant_id: str, profile_id: str) -> bool:
        result = await db.visitor_profiles.delete_one(
            {"profile_id": profile_id, "tenant_id": tenant_id}
        )
        return result.deleted_count > 0

    async def delete_by_tenant(self, tenant_id: str) -> int:
        result = await db.visitor_profiles.delete_many({"tenant_id": tenant_id})
        return result.deleted_count
