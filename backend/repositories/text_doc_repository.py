from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class TextDocRepository:
    def __init__(self):
        self.collection = db.documents

    async def create(self, doc_data: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.collection.insert_one(doc_data)
        doc_data["_id"] = result.inserted_id
        return doc_data

    async def get_by_doc_id(self, tenant_id: str, source_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"tenant_id": tenant_id, "source_id": source_id, "doc_id": doc_id})

    async def get_by_source(self, tenant_id: str, source_id: str) -> List[Dict[str, Any]]:
        cursor = self.collection.find({"tenant_id": tenant_id, "source_id": source_id})
        return await cursor.to_list(length=1000)

    async def update(self, tenant_id: str, source_id: str, doc_id: str, update_data: Dict[str, Any]) -> bool:
        update_data["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "source_id": source_id, "doc_id": doc_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def delete(self, tenant_id: str, source_id: str, doc_id: str) -> bool:
        result = await self.collection.delete_one({"tenant_id": tenant_id, "source_id": source_id, "doc_id": doc_id})
        return result.deleted_count > 0