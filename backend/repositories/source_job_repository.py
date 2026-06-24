from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.auth import db


class SourceJobRepository:
    def __init__(self):
        self.collection = db.source_jobs

    async def create(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.collection.insert_one(job_data)
        job_data["_id"] = result.inserted_id
        return job_data

    async def get_by_tenant(self, tenant_id: str, job_type: Optional[str] = None, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        query = {"tenant_id": tenant_id}
        if job_type:
            query["job_type"] = job_type
        cursor = self.collection.find(query).sort("started_at", -1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def update_status(self, tenant_id: str, source_id: str, job_type: str, status: str, **kwargs) -> bool:
        update_data = {"status": status, **kwargs}
        if status in ("completed", "failed"):
            update_data["finished_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"tenant_id": tenant_id, "source_id": source_id, "job_type": job_type},
            {"$set": update_data}
        )
        return result.modified_count > 0