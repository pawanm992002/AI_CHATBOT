import asyncio
import uuid
from datetime import datetime, timezone

import httpx
from core.auth import db
from services.ingestion import ingest_document
from services.suggested import generate_suggested_questions
from core.config import settings


def normalize_url(url: str) -> str:
    url = url.strip().lower()
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]
    return url.rstrip("/")


async def crawl_task(tenant_id: str, seed_url: str, job_id: str, source_id: str = ""):
    print(f"[CRAWL {job_id}] Starting crawl for seed_url={seed_url}")

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

    try:
        if not settings.FIRECRAWL_API_KEY:
            raise ValueError("FIRECRAWL_API_KEY is not configured")

        print(f"[CRAWL {job_id}] FIRECRAWL_API_KEY is set (len={len(settings.FIRECRAWL_API_KEY)})")

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

        pages = await _crawl_with_firecrawl(seed_url)
        print(f"[CRAWL {job_id}] Firecrawl returned {len(pages)} pages")

        pages_found = 0
        chunks_created = 0
        embedding_errors = 0

        for i, page in enumerate(pages):
            print(f"[CRAWL {job_id}] Processing page {i+1}/{len(pages)}: {page.get('metadata', {}).get('sourceURL', 'unknown')}")
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
                "error": None,
                "finished_at": datetime.now(timezone.utc)
            }}
        )
        await db.source_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "done",
                "pages_found": pages_found,
                "chunks_created": chunks_created,
                "error": None,
                "finished_at": datetime.now(timezone.utc)
            }}
        )

        # Auto-generate suggested questions after successful crawl
        if pages_found > 0:
            asyncio.create_task(generate_suggested_questions(tenant_id))
            asyncio.create_task(_generate_business_description(tenant_id, job_id))

    except Exception as e:
        print(f"[CRAWL {job_id}] FAILED: {e}")
        import traceback
        traceback.print_exc()
        await db.crawl_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "failed",
                "error": str(e),
                "finished_at": datetime.now(timezone.utc)
            }}
        )
        await db.source_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "failed",
                "error": str(e),
                "finished_at": datetime.now(timezone.utc)
            }}
        )


async def _crawl_with_firecrawl(seed_url: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=60.0, read=120.0, write=60.0, pool=60.0)) as client:
        print(f"[FIRECRAWL] Using MAX_CRAWL_PAGES={settings.MAX_CRAWL_PAGES} (APP_ENV={getattr(settings, 'APP_ENV', None)}) for seed_url={seed_url}")
        crawl_response = await client.post(
            "https://api.firecrawl.dev/v2/crawl",
            headers=headers,
            json={
                "url": seed_url,
                "limit": settings.MAX_CRAWL_PAGES,
                "scrapeOptions": {
                    "formats": ["markdown"],
                }
            }
        )
        print(f"[FIRECRAWL] POST /v2/crawl status={crawl_response.status_code}")
        print(f"[FIRECRAWL] Response: {crawl_response.text[:500]}")
        if crawl_response.status_code == 402:
            raise ValueError("Crawl service limit reached (out of credits). Please upgrade your plan or contact support.")
        crawl_response.raise_for_status()
        firecrawl_job_id = crawl_response.json()["id"]
        print(f"[FIRECRAWL] Job ID: {firecrawl_job_id}")

        # Timeout after 8 minutes
        max_wait = 480
        elapsed = 0

        max_retries = 3
        retry_delay = 10

        while elapsed < max_wait:
            await asyncio.sleep(5)
            elapsed += 5
            try:
                status_response = await client.get(
                    f"https://api.firecrawl.dev/v2/crawl/{firecrawl_job_id}",
                    headers=headers
                )
            except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
                if max_retries > 0:
                    max_retries -= 1
                    print(f"[FIRECRAWL] Poll ({elapsed}s): Connection error ({e}), retrying in {retry_delay}s... (retries left: {max_retries})")
                    await asyncio.sleep(retry_delay)
                    elapsed += retry_delay
                    continue
                raise

            if status_response.status_code == 429:
                print(f"[FIRECRAWL] Poll ({elapsed}s): Rate limited, retrying in 10s...")
                await asyncio.sleep(10)
                elapsed += 10
                continue
            if not status_response.text.strip():
                print(f"[FIRECRAWL] Poll ({elapsed}s): Empty response, retrying in 5s...")
                continue
            status_data = status_response.json()
            print(f"[FIRECRAWL] Poll ({elapsed}s): status={status_data.get('status')}, total={status_data.get('total')}, completed={status_data.get('completed')}, failed={status_data.get('failed')}")

            if status_data["status"] == "completed":
                all_data = status_data.get("data", [])
                next_url = status_data.get("next")
                print(f"[FIRECRAWL] Completed with {len(all_data)} pages (initial batch)")

                # Follow pagination to get all remaining pages
                while next_url:
                    print(f"[FIRECRAWL] Fetching next batch from: {next_url[:100]}...")
                    try:
                        next_response = await client.get(next_url, headers=headers)
                        if next_response.status_code == 429:
                            print(f"[FIRECRAWL] Rate limited on pagination, waiting 10s...")
                            await asyncio.sleep(10)
                            next_response = await client.get(next_url, headers=headers)
                        next_response.raise_for_status()
                        next_data = next_response.json()
                        batch = next_data.get("data", [])
                        next_url = next_data.get("next")
                        all_data.extend(batch)
                        print(f"[FIRECRAWL] Fetched {len(batch)} more pages (total: {len(all_data)})")
                    except Exception as e:
                        print(f"[FIRECRAWL] Error fetching next batch: {e}")
                        break

                print(f"[FIRECRAWL] Total pages collected: {len(all_data)}")
                return all_data
            if status_data["status"] == "failed":
                print(f"[FIRECRAWL] Job failed: {status_data}")
                raise RuntimeError(f"Firecrawl job failed: {status_data}")

        raise RuntimeError(f"Firecrawl crawl timed out after {max_wait}s")


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
