from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db

GAPS_VECTOR_INDEX = "knowledge_gaps_vector_index"
FAQS_VECTOR_INDEX = "faqs_vector_index"


async def _vector_search_gaps(
    tenant_id: str,
    query_vector: list[float],
    threshold: float = 0.85,
    limit: int = 5,
) -> list[Dict[str, Any]]:
    """Find similar open knowledge gaps using MongoDB Atlas vector search."""
    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": GAPS_VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(limit * 10, 100),
                    "limit": limit,
                    "filter": {
                        "tenant_id": tenant_id,
                        "status": "open",
                    },
                }
            },
            {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
            {"$match": {"score": {"$gte": threshold}}},
            {"$project": {"embedding": 0}},
        ]
        return await db.knowledge_gaps.aggregate(pipeline).to_list(length=limit)
    except Exception as e:
        print(f"[VECTOR] gaps vector search failed (index may not exist): {e}")
        return []


async def _vector_search_faqs(
    tenant_id: str,
    query_vector: list[float],
    threshold: float = 0.80,
    limit: int = 3,
) -> list[Dict[str, Any]]:
    """Find similar FAQs using MongoDB Atlas vector search."""
    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": FAQS_VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(limit * 10, 100),
                    "limit": limit,
                    "filter": {"tenant_id": tenant_id},
                }
            },
            {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
            {"$match": {"score": {"$gte": threshold}}},
            {"$project": {"embedding": 0}},
        ]
        return await db.faqs.aggregate(pipeline).to_list(length=limit)
    except Exception as e:
        print(f"[VECTOR] faqs vector search failed (index may not exist): {e}")
        return []


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
        results = await _vector_search_gaps(tenant_id, embedding, threshold, limit=1)
        return results[0] if results else None

    async def increment_count(self, gap_id: str) -> bool:
        result = await self.collection.update_one(
            {"_id": gap_id},
            {"$inc": {"count": 1}, "$set": {"last_seen": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0
