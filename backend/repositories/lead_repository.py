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
        cursor = self.collection.find({"tenant_id": tenant_id}).sort("created_at", -1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def count_by_tenant(self, tenant_id: str) -> int:
        return await self.collection.count_documents({"tenant_id": tenant_id})