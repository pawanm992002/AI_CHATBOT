from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class ConversationRepository:
    def __init__(self):
        self.collection = db.conversations

    async def get_by_session_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"session_id": session_id})

    async def upsert(self, session_id: str, tenant_id: str, current_url: str, summary: str, messages: List[Dict[str, Any]]) -> bool:
        result = await self.collection.update_one(
            {"session_id": session_id},
            {"$set": {
                "tenant_id": tenant_id,
                "current_url": current_url,
                "summary": summary,
                "messages": messages,
                "updated_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        return result.upserted_id is not None or result.modified_count > 0

    async def add_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        result = await self.collection.update_one(
            {"session_id": session_id},
            {"$push": {"messages": message}, "$set": {"updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0