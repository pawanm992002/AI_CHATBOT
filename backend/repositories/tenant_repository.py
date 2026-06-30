from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class TenantRepository:
    def __init__(self):
        self.collection = db.tenants

    async def create(self, tenant_data: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.collection.insert_one(tenant_data)
        tenant_data["_id"] = result.inserted_id
        return tenant_data

    async def get_by_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"domain": domain})

    async def get_by_api_key_hash(self, api_key_hash: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"api_key_hash": api_key_hash})

    async def get_by_tenant_id(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"tenant_id": tenant_id})

    async def update(self, tenant_id: str, update_data: Dict[str, Any]) -> bool:
        result = await self.collection.update_one(
            {"tenant_id": tenant_id},
            {"$set": update_data}
        )
        return result.matched_count > 0

    async def update_api_key_hash(self, tenant_id: str, api_key_hash: str) -> bool:
        result = await self.collection.update_one(
            {"tenant_id": tenant_id},
            {"$set": {"api_key_hash": api_key_hash}}
        )
        return result.modified_count > 0

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = self.collection.find().skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def count(self) -> int:
        return await self.collection.count_documents({})

    async def delete(self, tenant_id: str) -> bool:
        result = await self.collection.delete_one({"tenant_id": tenant_id})
        return result.deleted_count > 0