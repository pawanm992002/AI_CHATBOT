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


async def _map_with_firecrawl(seed_url: str) -> list[str]:
    """Discover all URLs from the sitemap using Firecrawl /map endpoint."""
    headers = {"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=60.0, read=120.0, write=60.0, pool=60.0)) as client:
        print(f"[FIRECRAWL] Discovering URLs from sitemap for {seed_url}")
        map_response = await client.post(
            "https://api.firecrawl.dev/v2/map",
            headers=headers,
            json={
                "url": seed_url,
                "sitemap": "only",
                "limit": settings.MAX_CRAWL_PAGES,
                "includeSubdomains": True,
                "ignoreQueryParameters": True,
            }
        )
        print(f"[FIRECRAWL] POST /v2/map status={map_response.status_code}")
        if map_response.status_code == 402:
            raise ValueError("Map service limit reached (out of credits). Please upgrade your plan or contact support.")
        map_response.raise_for_status()
        map_data = map_response.json()
        links = map_data.get("links", [])
        print(f"[FIRECRAWL] Discovered {len(links)} URLs from sitemap")

        # Extract URLs - /map returns objects with "url" key or plain strings
        raw_urls = []
        for link in links:
            if isinstance(link, dict):
                raw_urls.append(link.get("url", ""))
            else:
                raw_urls.append(str(link))

        # Convert relative URLs to absolute
        from urllib.parse import urljoin
        absolute_urls = []
        base_url = seed_url if seed_url.startswith("http") else f"https://{seed_url}"
        for url in raw_urls:
            if not url:
                continue
            if url.startswith("http"):
                absolute_urls.append(url)
            else:
                absolute_urls.append(urljoin(base_url + "/", url.lstrip("/")))
        print(f"[FIRECRAWL] Converted to {len(absolute_urls)} absolute URLs")
        return absolute_urls


async def _batch_scrape_with_firecrawl(urls: list[str]) -> list[dict]:
    """Scrape multiple URLs using Firecrawl /batch/scrape endpoint."""
    headers = {"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=60.0, read=120.0, write=60.0, pool=60.0)) as client:
        print(f"[FIRECRAWL] Starting batch scrape for {len(urls)} URLs")
        batch_response = await client.post(
            "https://api.firecrawl.dev/v2/batch/scrape",
            headers=headers,
            json={
                "urls": urls,
                "formats": ["markdown"],
            }
        )
        print(f"[FIRECRAWL] POST /v2/batch/scrape status={batch_response.status_code}")
        if batch_response.status_code != 200:
            print(f"[FIRECRAWL] Batch scrape error: {batch_response.text[:500]}")
        if batch_response.status_code == 402:
            raise ValueError("Batch scrape limit reached (out of credits). Please upgrade your plan or contact support.")
        if batch_response.status_code != 200:
            print(f"[FIRECRAWL] Batch scrape error body: {batch_response.text[:1000]}")
        batch_response.raise_for_status()
        batch_job_id = batch_response.json()["id"]
        print(f"[FIRECRAWL] Batch job ID: {batch_job_id}")

        # Timeout after 10 minutes
        max_wait = 600
        elapsed = 0

        while elapsed < max_wait:
            await asyncio.sleep(5)
            elapsed += 5
            try:
                status_response = await client.get(
                    f"https://api.firecrawl.dev/v2/batch/scrape/{batch_job_id}",
                    headers=headers
                )
            except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
                print(f"[FIRECRAWL] Batch poll ({elapsed}s): Connection error ({e}), retrying...")
                await asyncio.sleep(10)
                elapsed += 10
                continue

            if status_response.status_code == 429:
                print(f"[FIRECRAWL] Batch poll ({elapsed}s): Rate limited, retrying in 10s...")
                await asyncio.sleep(10)
                elapsed += 10
                continue

            status_data = status_response.json()
            print(f"[FIRECRAWL] Batch poll ({elapsed}s): status={status_data.get('status')}, completed={status_data.get('completed')}/{status_data.get('total')}")

            if status_data["status"] == "completed":
                all_data = status_data.get("data", [])
                next_url = status_data.get("next")
                print(f"[FIRECRAWL] Batch completed with {len(all_data)} pages (initial batch)")

                # Follow pagination
                while next_url:
                    print(f"[FIRECRAWL] Fetching next batch from: {next_url[:100]}...")
                    try:
                        next_response = await client.get(next_url, headers=headers)
                        if next_response.status_code == 429:
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
                print(f"[FIRECRAWL] Batch job failed: {status_data}")
                raise RuntimeError(f"Firecrawl batch job failed: {status_data}")

        raise RuntimeError(f"Firecrawl batch scrape timed out after {max_wait}s")


async def _crawl_with_firecrawl(seed_url: str) -> list[dict]:
    """Main crawl function: uses /map to discover URLs, then /batch/scrape to fetch content."""
    # Step 1: Discover all URLs from sitemap
    urls = await _map_with_firecrawl(seed_url)

    if not urls:
        print(f"[FIRECRAWL] No URLs found in sitemap for {seed_url}")
        return []

    # Step 2: Batch scrape all discovered URLs
    pages = await _batch_scrape_with_firecrawl(urls)
    return pages


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
