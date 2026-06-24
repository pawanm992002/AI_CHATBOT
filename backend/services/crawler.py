import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

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

    try:
        firecrawl_job_id = await _start_firecrawl_job(seed_url)
    except Exception as e:
        print(f"[CRAWL {job_id}] Failed to start Firecrawl job: {e}")
        await _fail_job(job_id, str(e))
        return
    print(f"[CRAWL {job_id}] Firecrawl job started: {firecrawl_job_id}")

    await db.crawl_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"firecrawl_job_id": firecrawl_job_id}}
    )


async def _start_firecrawl_job(seed_url: str) -> Optional[str]:
    headers = {"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        crawl_response = await client.post(
            "https://api.firecrawl.dev/v2/crawl",
            headers=headers,
            json={
                "url": seed_url,
                "limit": settings.MAX_CRAWL_PAGES,
                "maxConcurrency": 10,
                "scrapeOptions": {
                    "formats": ["markdown"],
                }
            }
        )
        print(f"[FIRECRAWL] POST /v2/crawl status={crawl_response.status_code}")
        print(f"[FIRECRAWL] Response: {crawl_response.text[:500]}")
        if crawl_response.status_code == 402:
            raise ValueError("Crawl service limit reached. Please try again later or contact support.")
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
            all_pages = list(data.get("data", []))
            next_url = data.get("next")
            while next_url:
                try:
                    resp = await client.get(next_url, headers=headers)
                    if resp.status_code != 200:
                        break
                    chunk = resp.json()
                    all_pages.extend(chunk.get("data", []))
                    next_url = chunk.get("next")
                except Exception as e:
                    print(f"[CRAWL_MONITOR] Job {job_id}: Pagination error: {e}")
                    break
            print(f"[CRAWL_MONITOR] Job {job_id}: Firecrawl completed with {len(all_pages)} pages")
            await db.crawl_jobs.update_one(
                {"job_id": job_id},
                {"$set": {"status": "processing", "pages_found": len(all_pages)}}
            )
            asyncio.create_task(
                _process_crawled_pages(
                    tenant_id, job_id, all_pages,
                    job.get("source_id", ""),
                    job.get("seed_url", "")
                )
            )
            return

        if status is None or status == "unknown":
            print(f"[CRAWL_MONITOR] Job {job_id}: Firecrawl returned no status (transient), will retry")
            return

        if status == "failed":
            error_msg = data.get("error", "Crawl job failed")
            print(f"[CRAWL_MONITOR] Job {job_id}: Firecrawl failed: {error_msg}")
            await _fail_job(job_id, "Crawl job failed. Please try again later.")
            return


async def _process_crawled_pages(
    tenant_id: str,
    job_id: str,
    pages: list[dict],
    source_id: str = "",
    seed_url: str = "",
):
    """Process crawled pages. Simple approach: process all, no staging."""

    job = await db.crawl_jobs.find_one({"job_id": job_id})
    if job and job.get("status") == "done":
        print(f"[CRAWL {job_id}] Already done, skipping")
        return

    # Check if bulk insert already completed (crash after insert, before finalize)
    existing_count = await db.pages.count_documents({"tenant_id": tenant_id, "crawl_id": job_id})
    if existing_count > 0:
        print(f"[CRAWL {job_id}] Found {existing_count} existing pages, skipping to finalize")
        await db.crawl_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "done", "pages_found": existing_count, "finished_at": datetime.now(timezone.utc)}}
        )
        await db.source_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "done", "pages_found": existing_count, "finished_at": datetime.now(timezone.utc)}}
        )
        return

    from services.ingestion import (
        _build_parent_sections, _split_child_chunks, embed_texts,
        EMBEDDING_BATCH_SIZE, count_tokens, MARKDOWN_HEADERS,
        CHILD_CHUNK_TOKENS, CHILD_CHUNK_OVERLAP_TOKENS,
    )
    from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
    from services.tokens import TOKEN_ENCODING_NAME

    parent_splitter_inst = MarkdownHeaderTextSplitter(
        headers_to_split_on=MARKDOWN_HEADERS, strip_headers=False,
    )
    child_splitter_inst = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=TOKEN_ENCODING_NAME,
        chunk_size=CHILD_CHUNK_TOKENS, chunk_overlap=CHILD_CHUNK_OVERLAP_TOKENS,
    )

    all_page_docs = []
    all_parent_docs = []
    all_chunk_docs = []
    embedding_errors = 0

    for i, page in enumerate(pages):
        url = page.get("metadata", {}).get("sourceURL", "")
        content = page.get("markdown", "").strip()
        title = page.get("metadata", {}).get("title", "")

        if not content or len(content) < 50 or not url:
            print(f"[CRAWL {job_id}] Skipping page {i+1}: empty or too short")
            continue

        print(f"[CRAWL {job_id}] Processing page {i+1}/{len(pages)}: {url}")
        doc_id = str(uuid.uuid4())

        parent_sections = _build_parent_sections(parent_splitter_inst, content, title)
        if not parent_sections:
            continue

        page_doc = {
            "tenant_id": tenant_id, "source_id": source_id, "page_id": doc_id,
            "url": url, "title": title, "content": content,
            "crawl_id": job_id, "indexed_at": datetime.now(timezone.utc),
        }
        all_page_docs.append(page_doc)

        for parent_index, section in enumerate(parent_sections):
            parent_id = f"{doc_id}:{parent_index}"
            parent_text = section["text"]
            all_parent_docs.append({
                "tenant_id": tenant_id, "source_id": source_id, "page_id": doc_id,
                "parent_id": parent_id, "url": url, "title": title,
                "section_title": section["section_title"], "section_path": section["section_path"],
                "headings": section["headings"], "text": parent_text,
                "token_count": count_tokens(parent_text), "parent_index": parent_index,
                "crawl_id": job_id, "indexed_at": datetime.now(timezone.utc),
            })

            child_chunks = _split_child_chunks(child_splitter_inst, parent_text)
            for child_index, child in enumerate(child_chunks):
                all_chunk_docs.append({
                    "tenant_id": tenant_id, "source_id": source_id, "page_id": doc_id,
                    "parent_id": parent_id, "url": url, "title": title,
                    "section_title": section["section_title"], "section_path": section["section_path"],
                    "headings": section["headings"], "text": child,
                    "search_text": f"{section['section_title'] or section['section_path']}:\n{child}",
                    "token_count": count_tokens(f"{section['section_title'] or section['section_path']}:\n{child}"),
                    "parent_index": parent_index, "child_index": child_index,
                    "chunk_index": len(all_chunk_docs),
                    "crawl_id": job_id, "indexed_at": datetime.now(timezone.utc),
                })

    if not all_chunk_docs:
        print(f"[CRAWL {job_id}] No chunks produced, marking failed")
        await _fail_job(job_id, "No content to index")
        return

    # Embed ALL chunks in batches
    print(f"[CRAWL {job_id}] Embedding {len(all_chunk_docs)} chunks")
    for start in range(0, len(all_chunk_docs), EMBEDDING_BATCH_SIZE):
        batch = all_chunk_docs[start:start + EMBEDDING_BATCH_SIZE]
        try:
            embeddings = await embed_texts([item["search_text"] for item in batch])
        except Exception as exc:
            print(f"[CRAWL {job_id}] Embedding batch failed: {exc}")
            embedding_errors += len(batch)
            continue

        if len(embeddings) != len(batch):
            embedding_errors += len(batch)
            continue

        for offset, (chunk, embedding) in enumerate(zip(batch, embeddings)):
            if not embedding:
                embedding_errors += 1
                continue
            chunk["embedding"] = embedding

    all_chunk_docs = [c for c in all_chunk_docs if "embedding" in c]

    if not all_chunk_docs:
        print(f"[CRAWL {job_id}] All embeddings failed, marking failed")
        await _fail_job(job_id, "All embedding attempts failed")
        return

    # Bulk insert everything at once
    print(f"[CRAWL {job_id}] Bulk inserting {len(all_page_docs)} pages, {len(all_parent_docs)} parents, {len(all_chunk_docs)} chunks")
    try:
        await db.pages.insert_many(all_page_docs, ordered=False)
        await db.parents.insert_many(all_parent_docs, ordered=False)
        for start in range(0, len(all_chunk_docs), EMBEDDING_BATCH_SIZE):
            await db.chunks.insert_many(all_chunk_docs[start:start + EMBEDDING_BATCH_SIZE], ordered=False)
    except Exception as e:
        print(f"[CRAWL {job_id}] Bulk insert failed: {e}")
        await db.pages.delete_many({"tenant_id": tenant_id, "crawl_id": job_id})
        await db.parents.delete_many({"tenant_id": tenant_id, "crawl_id": job_id})
        await db.chunks.delete_many({"tenant_id": tenant_id, "crawl_id": job_id})
        await _fail_job(job_id, f"Bulk insert failed: {e}")
        return

    # Finalize
    pages_found = len(all_page_docs)
    chunks_created = len(all_chunk_docs)
    print(f"[CRAWL {job_id}] Done. pages={pages_found}, chunks={chunks_created}, errors={embedding_errors}")

    await db.crawl_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "done", "pages_found": pages_found,
            "chunks_created": chunks_created, "embedding_errors": embedding_errors,
            "finished_at": datetime.now(timezone.utc),
        }}
    )
    await db.source_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "done", "pages_found": pages_found,
            "chunks_created": chunks_created, "finished_at": datetime.now(timezone.utc),
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
        description = (resp.choices[0].message.content or "").strip()

        await db.tenants.update_one(
            {"tenant_id": tenant_id},
            {"$set": {"description": description}}
        )
        print(f"[CRAWL] Auto-generated description for {tenant_id}: {description[:80]}...")

    except Exception as e:
        print(f"[CRAWL] Failed to generate description: {e}")
