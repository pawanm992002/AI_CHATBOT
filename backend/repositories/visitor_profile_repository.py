from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
from core.auth import db


class VisitorProfileRepository:
    def __init__(self):
        self.collection = db.visitor_profiles

    async def create(self, tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        doc = {
            "profile_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            **data,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def get_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        cursor = self.collection.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("created_at", -1)
        return await cursor.to_list(length=100)

    async def get_by_profile_id(self, tenant_id: str, profile_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one(
            {"tenant_id": tenant_id, "profile_id": profile_id}, {"_id": 0}
        )

    async def get_enabled_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        cursor = self.collection.find(
            {"tenant_id": tenant_id, "enabled": True}, {"_id": 0}
        ).sort("created_at", -1)
        return await cursor.to_list(length=100)

    async def update(self, tenant_id: str, profile_id: str, data: Dict[str, Any]) -> bool:
        data["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "profile_id": profile_id},
            {"$set": data}
        )
        return result.modified_count > 0

    async def delete(self, tenant_id: str, profile_id: str) -> bool:
        result = await self.collection.delete_one(
            {"tenant_id": tenant_id, "profile_id": profile_id}
        )
        return result.deleted_count > 0

    async def delete_by_tenant(self, tenant_id: str) -> int:
        result = await self.collection.delete_many({"tenant_id": tenant_id})
        return result.deleted_count