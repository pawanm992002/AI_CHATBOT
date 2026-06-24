from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class FAQRepository:
    def __init__(self):
        self.collection = db.faqs

    async def create(self, faq_data: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.collection.insert_one(faq_data)
        faq_data["_id"] = result.inserted_id
        return faq_data

    async def get_by_faq_id(self, tenant_id: str, source_id: str, faq_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"tenant_id": tenant_id, "source_id": source_id, "faq_id": faq_id})

    async def get_by_source(self, tenant_id: str, source_id: str) -> List[Dict[str, Any]]:
        cursor = self.collection.find({"tenant_id": tenant_id, "source_id": source_id})
        return await cursor.to_list(length=1000)

    async def update(self, tenant_id: str, source_id: str, faq_id: str, update_data: Dict[str, Any]) -> bool:
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "source_id": source_id, "faq_id": faq_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def delete(self, tenant_id: str, source_id: str, faq_id: str) -> bool:
        result = await self.collection.delete_one({"tenant_id": tenant_id, "source_id": source_id, "faq_id": faq_id})
        return result.deleted_count > 0

    async def bulk_create(self, faqs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not faqs:
            return []
        result = await self.collection.insert_many(faqs)
        for i, faq in enumerate(faqs):
            faq["_id"] = result.inserted_ids[i]
        return faqs