import httpx
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from models.requests import CrawlRequest
from views.responses import CrawlJobResponse
from core.auth import verify_api_key, get_current_tenant, db
from services.crawler import crawl_task, normalize_url
from repositories.crawl_job_repository import CrawlJobRepository
from datetime import datetime, timezone
from core.config import settings
import uuid

router = APIRouter(tags=["crawl"])
crawl_job_repo = CrawlJobRepository()


async def _create_crawl_source_job(tenant_id: str, job_id: str, seed_url: str) -> None:
    job_doc = {
        "tenant_id": tenant_id,
        "job_id": job_id,
        "source_id": f"crawl_{job_id}",
        "job_type": "crawl",
        "status": "queued",
        "chunks_created": 0,
        "embedding_errors": 0,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "config": {"seed_url": seed_url},
        "created_at": datetime.now(timezone.utc),
    }
    await db.source_jobs.insert_one(job_doc)


async def _update_crawl_source_job(job_id: str, update: dict) -> None:
    await db.source_jobs.update_one({"job_id": job_id}, {"$set": update})


@router.post("/crawl", response_model=CrawlJobResponse)
async def start_crawl(req: CrawlRequest, background_tasks: BackgroundTasks, current_tenant: dict = Depends(verify_api_key)):
    job_id = str(uuid.uuid4())
    seed_url = normalize_url(req.seed_url)
    await crawl_job_repo.create({
        "tenant_id": current_tenant["tenant_id"],
        "job_id": job_id,
        "seed_url": seed_url,
        "status": "queued",
        "pages_found": 0,
        "chunks_created": 0,
        "embedding_errors": 0,
        "started_at": None,
        "finished_at": None,
        "error": None,
    })

    await _create_crawl_source_job(current_tenant["tenant_id"], job_id, seed_url)
    background_tasks.add_task(crawl_task, current_tenant["tenant_id"], seed_url, job_id)
    return {"job_id": job_id}


@router.get("/crawl/{job_id}")
async def get_crawl_status(job_id: str, current_tenant: dict = Depends(verify_api_key)):
    job = await crawl_job_repo.get_by_job_id(current_tenant["tenant_id"], job_id)
    return job


@router.delete("/crawl/{job_id}")
async def cancel_crawl_job_api(job_id: str, current_tenant: dict = Depends(verify_api_key)):
    return await _cancel_job(job_id, current_tenant["tenant_id"])


@router.delete("/index")
async def delete_index(current_tenant: dict = Depends(verify_api_key)):
    tenant_id = current_tenant["tenant_id"]
    await db.chunks.delete_many({"tenant_id": tenant_id})
    await db.parents.delete_many({"tenant_id": tenant_id})
    await db.pages.delete_many({"tenant_id": tenant_id})
    return {"status": "deleted"}


@router.post("/dashboard/crawl", response_model=CrawlJobResponse)
async def dashboard_start_crawl(req: CrawlRequest, background_tasks: BackgroundTasks, current_tenant: dict = Depends(get_current_tenant)):
    job_id = str(uuid.uuid4())
    seed_url = normalize_url(req.seed_url)
    await crawl_job_repo.create({
        "tenant_id": current_tenant["tenant_id"],
        "job_id": job_id,
        "seed_url": seed_url,
        "status": "queued",
        "pages_found": 0,
        "chunks_created": 0,
        "embedding_errors": 0,
        "started_at": None,
        "finished_at": None,
        "error": None,
    })
    await _create_crawl_source_job(current_tenant["tenant_id"], job_id, seed_url)
    background_tasks.add_task(crawl_task, current_tenant["tenant_id"], seed_url, job_id)
    return {"job_id": job_id}


async def _cancel_job(job_id: str, tenant_id: str) -> dict:
    job = await db.crawl_jobs.find_one({"tenant_id": tenant_id, "job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    if job.get("status") not in ("queued", "running", "processing"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status '{job['status']}'")

    firecrawl_job_id = job.get("firecrawl_job_id")
    if firecrawl_job_id:
        headers = {"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            try:
                await client.delete(
                    f"https://api.firecrawl.dev/v2/crawl/{firecrawl_job_id}",
                    headers=headers
                )
            except Exception as e:
                print(f"[CRAWL] Job {job_id}: Failed to cancel Firecrawl job: {e}")

    now = datetime.now(timezone.utc)
    await db.crawl_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "failed",
            "error": "Cancelled by user",
            "finished_at": now
        }}
    )
    await db.source_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "failed",
            "error": "Cancelled by user",
            "finished_at": now
        }}
    )
    return {"status": "cancelled", "job_id": job_id}


@router.delete("/dashboard/crawl/{job_id}")
async def cancel_crawl_job(job_id: str, current_tenant: dict = Depends(get_current_tenant)):
    return await _cancel_job(job_id, current_tenant["tenant_id"])


def _serialize_job(job):
    if not job:
        return job
    for field in ("started_at", "finished_at"):
        val = job.get(field)
        if val is not None:
            job[field] = val.isoformat() if hasattr(val, "isoformat") else str(val)
    return job


@router.get("/dashboard/crawl/history")
async def dashboard_crawl_history(
    page: int = 1,
    page_size: int = 20,
    current_tenant: dict = Depends(get_current_tenant),
):
    skip = (page - 1) * page_size
    jobs = await crawl_job_repo.get_by_tenant(current_tenant["tenant_id"], skip=skip, limit=page_size)
    total = await crawl_job_repo.count_by_tenant(current_tenant["tenant_id"])
    return {
        "items": [_serialize_job(j) for j in jobs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/dashboard/crawl/{job_id}")
async def dashboard_get_crawl_status(job_id: str, current_tenant: dict = Depends(get_current_tenant)):
    job = await crawl_job_repo.get_by_job_id(current_tenant["tenant_id"], job_id)
    return _serialize_job(job)


@router.delete("/dashboard/index")
async def dashboard_delete_index(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]
    await db.chunks.delete_many({"tenant_id": tenant_id})
    await db.parents.delete_many({"tenant_id": tenant_id})
    await db.pages.delete_many({"tenant_id": tenant_id})
    return {"status": "deleted"}