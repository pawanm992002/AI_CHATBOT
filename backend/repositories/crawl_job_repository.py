from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class CrawlJobRepository:
    def __init__(self):
        self.collection = db.crawl_jobs

    async def create(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.collection.insert_one(job_data)
        job_data["_id"] = result.inserted_id
        return job_data

    async def get_by_job_id(self, tenant_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"tenant_id": tenant_id, "job_id": job_id}, {"_id": 0})

    async def get_by_tenant(self, tenant_id: str, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.collection.find({"tenant_id": tenant_id}, {"_id": 0}).sort("started_at", -1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def update_status(self, tenant_id: str, job_id: str, status: str, **kwargs) -> bool:
        update_data = {"status": status, **kwargs}
        if status in ("completed", "failed"):
            update_data["finished_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "job_id": job_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def increment_pages(self, tenant_id: str, job_id: str, count: int = 1) -> bool:
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "job_id": job_id},
            {"$inc": {"pages_crawled": count}}
        )
        return result.modified_count > 0

    async def increment_chunks(self, tenant_id: str, job_id: str, count: int = 1) -> bool:
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "job_id": job_id},
            {"$inc": {"chunks_created": count}}
        )
        return result.modified_count > 0

    async def count_by_tenant(self, tenant_id: str) -> int:
        return await self.collection.count_documents({"tenant_id": tenant_id})

    async def mark_stale_running_as_failed(self) -> int:
        result = await self.collection.update_many(
            {"status": "running"},
            {"$set": {
                "status": "failed",
                "error": "Server restarted — crawl task was interrupted",
                "finished_at": datetime.now(timezone.utc),
            }}
        )
        return result.modified_count
