from typing import Optional, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class FeedbackRepository:
    def __init__(self):
        self.collection = db.message_feedback

    async def upsert(self, tenant_id: str, session_id: str, message_id: str, rating: str) -> bool:
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "session_id": session_id, "message_id": message_id},
            {"$set": {
                "tenant_id": tenant_id,
                "session_id": session_id,
                "message_id": message_id,
                "rating": rating,
                "created_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        return result.upserted_id is not None or result.modified_count > 0