from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class VisitorRepository:
    def __init__(self):
        self.collection = db.visitors

    async def upsert_visit(self, session_id: str, tenant_id: str, ip: str, url: str, title: str) -> bool:
        now = datetime.now(timezone.utc)
        visitor = await self.collection.find_one({"session_id": session_id}, {"ip_history": {"$slice": -1}, "page_views": {"$slice": -1}})
        
        needs_ip = not visitor or not visitor.get("ip_history") or visitor["ip_history"][-1]["ip"] != ip
        needs_page = not visitor or not visitor.get("page_views") or visitor["page_views"][-1]["url"] != url or visitor["page_views"][-1]["title"] != title
        
        update = {"$set": {"last_seen_at": now, "tenant_id": tenant_id}}
        if not visitor:
            update["$setOnInsert"] = {
                "session_id": session_id,
                "first_seen_at": now,
                "conversation_ids": [],
                "total_messages": 0,
            }
        if needs_ip:
            update.setdefault("$push", {})["ip_history"] = {
                "$each": [{"ip": ip, "seen_at": now}],
                "$slice": -20,
            }
        if needs_page:
            update.setdefault("$push", {})["page_views"] = {
                "$each": [{"url": url, "title": title, "timestamp": now}],
                "$slice": -50,
            }

        if update:
            await self.collection.update_one({"session_id": session_id}, update, upsert=True)
        return True

    async def add_conversation(self, session_id: str) -> bool:
        result = await self.collection.update_one(
            {"session_id": session_id},
            {"$addToSet": {"conversation_ids": session_id}, "$inc": {"total_messages": 1}}
        )
        return result.modified_count > 0