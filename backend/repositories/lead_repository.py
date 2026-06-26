from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class LeadRepository:
    def __init__(self):
        self.collection = db.leads

    async def create(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.collection.insert_one(lead_data)
        lead_data["_id"] = result.inserted_id
        return lead_data

    async def get_by_tenant(self, tenant_id: str, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.collection.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("created_at", -1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def count_by_tenant(self, tenant_id: str) -> int:
        return await self.collection.count_documents({"tenant_id": tenant_id})


class LeadFormConfigRepository:
    def __init__(self):
        self.collection = db.lead_form_configs

    async def create(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.collection.insert_one(config_data)
        config_data["_id"] = result.inserted_id
        return config_data

    async def get_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        cursor = self.collection.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("created_at", -1)
        return await cursor.to_list(length=100)

    async def get_by_form_id(self, tenant_id: str, form_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one(
            {"tenant_id": tenant_id, "form_id": form_id}, {"_id": 0}
        )

    async def get_enabled_for_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one(
            {"tenant_id": tenant_id, "enabled": True}, {"_id": 0}
        )

    async def update(self, tenant_id: str, form_id: str, update_data: Dict[str, Any]) -> bool:
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "form_id": form_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def delete(self, tenant_id: str, form_id: str) -> bool:
        result = await self.collection.delete_one(
            {"tenant_id": tenant_id, "form_id": form_id}
        )
        return result.deleted_count > 0

    async def delete_by_tenant(self, tenant_id: str) -> int:
        result = await self.collection.delete_many({"tenant_id": tenant_id})
        return result.deleted_count