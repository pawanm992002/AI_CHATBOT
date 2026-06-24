from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class KnowledgeGapRepository:
    def __init__(self):
        self.collection = db.knowledge_gaps

    async def create(self, gap_data: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.collection.insert_one(gap_data)
        gap_data["_id"] = result.inserted_id
        return gap_data

    async def get_by_tenant(self, tenant_id: str, status: Optional[str] = None, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        query = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        cursor = self.collection.find(query).sort("last_seen", -1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def count_by_tenant(self, tenant_id: str, status: Optional[str] = None) -> int:
        query = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        return await self.collection.count_documents(query)

    async def update_status(self, tenant_id: str, gap_id: str, status: str, resolved_by_faq_id: Optional[str] = None) -> bool:
        update_data = {"status": status}
        if resolved_by_faq_id:
            update_data["resolved_by_faq_id"] = resolved_by_faq_id
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "_id": gap_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def find_similar(self, tenant_id: str, embedding: List[float], threshold: float = 0.85) -> Optional[Dict[str, Any]]:
        open_gaps = await self.collection.find({
            "tenant_id": tenant_id,
            "status": "open",
            "embedding": {"$exists": True}
        }).to_list(1000)
        
        if not open_gaps:
            return None
        
        import numpy as np
        new_embedding = np.array(embedding)
        best_match = None
        best_similarity = 0.0
        
        for gap in open_gaps:
            if gap.get("embedding"):
                gap_embedding = np.array(gap["embedding"])
                cos_sim = np.dot(gap_embedding, new_embedding) / (np.linalg.norm(gap_embedding) * np.linalg.norm(new_embedding))
                if cos_sim > best_similarity and cos_sim > threshold:
                    best_similarity = cos_sim
                    best_match = gap
        
        return best_match

    async def increment_count(self, gap_id: str) -> bool:
        result = await self.collection.update_one(
            {"_id": gap_id},
            {"$inc": {"count": 1}, "$set": {"last_seen": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0