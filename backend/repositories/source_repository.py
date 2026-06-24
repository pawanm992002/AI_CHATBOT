from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class SourceRepository:
    def __init__(self):
        self.collection = db.sources

    async def create(self, source_data: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.collection.insert_one(source_data)
        source_data["_id"] = result.inserted_id
        return source_data

    async def get_by_source_id(self, tenant_id: str, source_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"tenant_id": tenant_id, "source_id": source_id})

    async def get_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        cursor = self.collection.find({"tenant_id": tenant_id})
        return await cursor.to_list(length=1000)

    async def update(self, tenant_id: str, source_id: str, update_data: Dict[str, Any]) -> bool:
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "source_id": source_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def delete(self, tenant_id: str, source_id: str) -> bool:
        result = await self.collection.delete_one({"tenant_id": tenant_id, "source_id": source_id})
        return result.deleted_count > 0

    async def increment_chunk_count(self, tenant_id: str, source_id: str, count: int) -> bool:
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "source_id": source_id},
            {"$inc": {"chunk_count": count}, "$set": {"last_indexed_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0