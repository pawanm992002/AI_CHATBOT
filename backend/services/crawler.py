import asyncio
import uuid
from datetime import datetime, timezone

import httpx
from core.auth import db
from services.ingestion import ingest_document
from services.suggested import generate_suggested_questions
from core.config import settings

MAX_PAGES = 200

def normalize_url(url: str) -> str:
    url = url.strip().lower()
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]
    return url.rstrip("/")


async def crawl_task(tenant_id: str, seed_url: str, job_id: str, source_id: str = ""):
    """Phase 1: start a Firecrawl job and persist its ID, then return immediately.
       The crawl monitor handles polling, page retrieval and indexing."""
    print(f"[CRAWL {job_id}] Starting crawl for seed_url={seed_url}")

    if not settings.FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY is not configured")

    await db.crawl_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "running",
            "started_at": datetime.now(timezone.utc),
            "embedding_errors": 0,
            "error": None,
        }}
    )
    await db.source_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "running",
            "started_at": datetime.now(timezone.utc),
        }}
    )

    # Purge all old data for this site before re-crawling
    old_jobs = await db.crawl_jobs.find(
        {"tenant_id": tenant_id, "job_id": {"$ne": job_id}},
        {"job_id": 1, "seed_url": 1}
    ).to_list(length=100)
    old_crawl_ids = [j["job_id"] for j in old_jobs if normalize_url(j.get("seed_url", "")) == seed_url]
    if old_crawl_ids:
        print(f"[CRAWL {job_id}] Purging {len(old_crawl_ids)} old crawl jobs")
        await db.chunks.delete_many({"tenant_id": tenant_id, "crawl_id": {"$in": old_crawl_ids}})
        await db.parents.delete_many({"tenant_id": tenant_id, "crawl_id": {"$in": old_crawl_ids}})
        await db.pages.delete_many({"tenant_id": tenant_id, "crawl_id": {"$in": old_crawl_ids}})

    firecrawl_job_id = await _start_firecrawl_job(seed_url)
    print(f"[CRAWL {job_id}] Firecrawl job started: {firecrawl_job_id}")

    await db.crawl_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"firecrawl_job_id": firecrawl_job_id}}
    )


async def _start_firecrawl_job(seed_url: str) -> str:
    headers = {"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        crawl_response = await client.post(
            "https://api.firecrawl.dev/v2/crawl",
            headers=headers,
            json={
                "url": seed_url,
                "limit": MAX_PAGES,
                "scrapeOptions": {
                    "formats": ["markdown"],
                    "actions": [
                        {"type": "wait", "milliseconds": 10000},
                    ],
                }
            }
        )
        print(f"[FIRECRAWL] POST /v2/crawl status={crawl_response.status_code}")
        print(f"[FIRECRAWL] Response: {crawl_response.text[:500]}")
        crawl_response.raise_for_status()
        return crawl_response.json()["id"]


# ── Crawl monitor ──────────────────────────────────────────────────────────

async def start_crawl_monitor():
    """Periodic background loop that polls Firecrawl for running jobs."""
    print("[CRAWL_MONITOR] Starting crawl monitor")
    while True:
        try:
            await _monitor_cycle()
        except Exception as e:
            print(f"[CRAWL_MONITOR] Cycle error: {e}")
            import traceback
            traceback.print_exc()
        await asyncio.sleep(15)


async def _monitor_cycle():
    running_jobs = await db.crawl_jobs.find(
        {"status": "running", "firecrawl_job_id": {"$exists": True, "$ne": None}},
        {"_id": 0}
    ).to_list(length=50)

    for job in running_jobs:
        await _poll_and_process(job)


async def _poll_and_process(job: dict):
    tenant_id = job["tenant_id"]
    job_id = job["job_id"]
    firecrawl_job_id = job["firecrawl_job_id"]

    headers = {"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        try:
            resp = await client.get(
                f"https://api.firecrawl.dev/v2/crawl/{firecrawl_job_id}",
                headers=headers
            )
        except Exception as e:
            print(f"[CRAWL_MONITOR] Job {job_id}: Poll error: {e}")
            return

        if resp.status_code == 429:
            print(f"[CRAWL_MONITOR] Job {job_id}: Rate limited, will retry next cycle")
            return
        if not resp.text.strip():
            return

        data = resp.json()
        status = data.get("status")
        total = data.get("total", 0)
        completed = data.get("completed", 0)

        print(f"[CRAWL_MONITOR] Job {job_id}: status={status}, total={total}, completed={completed}")

        if status == "scraping":
            await db.crawl_jobs.update_one(
                {"job_id": job_id},
                {"$set": {"pages_found": completed or 0, "total_pages": total or 0}}
            )
            return

        if status == "completed":
            pages = data.get("data", [])
            print(f"[CRAWL_MONITOR] Job {job_id}: Firecrawl completed with {len(pages)} pages")
            await db.crawl_jobs.update_one(
                {"job_id": job_id},
                {"$set": {"status": "processing", "pages_found": len(pages)}}
            )
            asyncio.create_task(
                _process_crawled_pages(
                    tenant_id, job_id, pages,
                    job.get("source_id", ""),
                    job.get("seed_url", "")
                )
            )
            return

        if status == "failed":
            error_msg = data.get("error", "Firecrawl job failed")
            print(f"[CRAWL_MONITOR] Job {job_id}: Firecrawl failed: {error_msg}")
            await _fail_job(job_id, error_msg)
            return


async def _process_crawled_pages(
    tenant_id: str,
    job_id: str,
    pages: list[dict],
    source_id: str = "",
    seed_url: str = "",
):
    """Phase 2: index all pages returned by Firecrawl."""
    print(f"[CRAWL {job_id}] Indexing {len(pages)} pages")

    pages_found = 0
    chunks_created = 0
    embedding_errors = 0

    for i, page in enumerate(pages):
        url = page.get("metadata", {}).get("sourceURL", "")
        print(f"[CRAWL {job_id}] Processing page {i+1}/{len(pages)}: {url}")
        result = await _index_page(tenant_id, job_id, page, source_id)
        if not result:
            print(f"[CRAWL {job_id}] Page {i+1} skipped (no content or too short)")
            continue

        chunks_created += result["chunks_created"]
        embedding_errors += result["embedding_errors"]
        if result["indexed"]:
            pages_found += 1

        await db.crawl_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "pages_found": pages_found,
                "chunks_created": chunks_created,
                "embedding_errors": embedding_errors,
            }}
        )
        await db.source_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "chunks_created": chunks_created,
                "embedding_errors": embedding_errors,
            }}
        )

    print(f"[CRAWL {job_id}] Done. pages_found={pages_found}, chunks_created={chunks_created}, embedding_errors={embedding_errors}")
    await db.crawl_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "done",
            "pages_found": pages_found,
            "chunks_created": chunks_created,
            "finished_at": datetime.now(timezone.utc)
        }}
    )
    await db.source_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "done",
            "pages_found": pages_found,
            "chunks_created": chunks_created,
            "finished_at": datetime.now(timezone.utc)
        }}
    )

    if pages_found > 0:
        asyncio.create_task(generate_suggested_questions(tenant_id))
        asyncio.create_task(_generate_business_description(tenant_id, job_id))


async def _fail_job(job_id: str, error: str):
    await db.crawl_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "failed",
            "error": error,
            "finished_at": datetime.now(timezone.utc)
        }}
    )
    await db.source_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "failed",
            "error": error,
            "finished_at": datetime.now(timezone.utc)
        }}
    )


async def _index_page(
    tenant_id: str,
    crawl_id: str,
    page: dict,
    source_id: str = "",
) -> dict | None:
    content = page.get("markdown", "").strip()
    url = page.get("metadata", {}).get("sourceURL", "")
    title = page.get("metadata", {}).get("title", "")

    if not content or len(content) < 50 or not url:
        print(f"[INDEX] Skipping page url={url} content_len={len(content)} reason={'empty' if not content else 'too short' if len(content) < 50 else 'no url'}")
        return None

    doc_id = str(uuid.uuid4())
    result = await ingest_document(
        tenant_id=tenant_id,
        source_id=source_id,
        doc_id=doc_id,
        content=content,
        title=title,
        url=url,
        crawl_id=crawl_id,
    )

    if result["indexed"]:
        return {
            "url": url,
            "indexed": True,
            "chunks_created": result["chunks_created"],
            "embedding_errors": result["embedding_errors"],
        }

    return {
        "url": url,
        "indexed": False,
        "chunks_created": 0,
        "embedding_errors": result["embedding_errors"] or 1,
    }


async def _generate_business_description(tenant_id: str, crawl_id: str):
    """Auto-generate a short business description from crawled content."""
    try:
        from services.embedder import openai_client

        pages = await db.pages.find(
            {"tenant_id": tenant_id, "crawl_id": crawl_id},
            {"content": 1, "url": 1}
        ).limit(5).to_list(5)

        if not pages:
            return

        combined = ""
        for page in pages:
            content = page.get("content", "")[:500]
            combined += f"\n{content}"
            if len(combined) > 2000:
                break

        resp = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "Generate a 1-2 sentence description of what this business/website does. "
                    "Be concise and factual. Only use information from the provided content."
                )},
                {"role": "user", "content": combined},
            ],
            max_tokens=100,
            temperature=0.0,
        )
        description = resp.choices[0].message.content.strip()

        await db.tenants.update_one(
            {"tenant_id": tenant_id},
            {"$set": {"description": description}}
        )
        print(f"[CRAWL] Auto-generated description for {tenant_id}: {description[:80]}...")

    except Exception as e:
        print(f"[CRAWL] Failed to generate description: {e}")
