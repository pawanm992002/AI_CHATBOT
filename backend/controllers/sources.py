import os
import uuid
import httpx
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form

from core.auth import db, get_current_tenant
from models.requests import SourceCreateRequest
from views.responses import SourceCreateResponse
from services.pdf_parser import extract_text_from_pdf, extract_text_from_pdf_from_bytes
from services.ingestion import ingest_document
from services.storage import upload_pdf as do_upload, get_presigned_url, delete_pdf as do_delete
from repositories.source_repository import SourceRepository

router = APIRouter(prefix="/dashboard/sources", tags=["sources"])
source_repo = SourceRepository()


def _to_iso(dt):
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


async def _delete_source_data(tenant_id: str, source_id: str) -> None:
    await db.chunks.delete_many({"tenant_id": tenant_id, "source_id": source_id})
    await db.parents.delete_many({"tenant_id": tenant_id, "source_id": source_id})
    await db.pages.delete_many({"tenant_id": tenant_id, "source_id": source_id})


async def _create_source_job(tenant_id: str, source_id: str, job_type: str, config: dict | None = None) -> str:
    job_id = str(uuid.uuid4())
    job_doc = {
        "tenant_id": tenant_id,
        "job_id": job_id,
        "source_id": source_id,
        "job_type": job_type,
        "status": "queued",
        "chunks_created": 0,
        "embedding_errors": 0,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "config": config or {},
        "created_at": datetime.now(timezone.utc),
    }
    await db.source_jobs.insert_one(job_doc)
    return job_id


async def _update_source_job(job_id: str, update: dict) -> None:
    await db.source_jobs.update_one({"job_id": job_id}, {"$set": update})


@router.get("")
async def list_sources(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]
    sources = await source_repo.get_by_tenant(tenant_id)

    for source in sources:
        source.pop("_id", None)
        source["chunk_count"] = await db.chunks.count_documents({
            "tenant_id": tenant_id,
            "source_id": source["source_id"],
        })

    crawl_jobs = await db.crawl_jobs.find(
        {"tenant_id": tenant_id, "status": "done"},
        {"_id": 0}
    ).sort("started_at", -1).to_list(length=100)

    for job in crawl_jobs:
        sources.append({
            "tenant_id": tenant_id,
            "source_id": f"crawl_{job.get('job_id', '')}",
            "source_type": "website",
            "name": job.get("seed_url", "Website"),
            "status": "ready",
            "chunk_count": job.get("chunks_created", 0),
            "config": {
                "seed_url": job.get("seed_url"),
                "pages_found": job.get("pages_found", 0),
            },
            "created_at": _to_iso(job.get("started_at")),
            "last_indexed_at": _to_iso(job.get("finished_at")),
        })

    return sources


@router.post("", status_code=201)
async def create_source(
    body: SourceCreateRequest,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    source_id = str(uuid.uuid4())

    source_doc = {
        "tenant_id": tenant_id,
        "source_id": source_id,
        "source_type": body.source_type,
        "name": body.name,
        "config": {},
        "status": "ready",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "last_indexed_at": None,
    }

    await source_repo.create(source_doc)
    source_doc.pop("_id", None)
    return source_doc


def _serialize_job(job):
    if not job:
        return job
    for field in ("started_at", "finished_at", "created_at"):
        val = job.get(field)
        if val is not None:
            job[field] = val.isoformat() if hasattr(val, "isoformat") else str(val)
    return job


@router.get("/history")
async def source_job_history(
    page: int = 1,
    page_size: int = 20,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    skip = (page - 1) * page_size
    jobs = await db.source_jobs.find(
        {"tenant_id": tenant_id},
        {"_id": 0}
    ).sort("started_at", -1).skip(skip).limit(page_size).to_list(length=page_size)
    total = await db.source_jobs.count_documents({"tenant_id": tenant_id})
    return {
        "items": [_serialize_job(j) for j in jobs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/history/{source_id}")
async def source_job_history_by_source(
    source_id: str,
    page: int = 1,
    page_size: int = 20,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    skip = (page - 1) * page_size
    jobs = await db.source_jobs.find(
        {"tenant_id": tenant_id, "source_id": source_id},
        {"_id": 0}
    ).sort("started_at", -1).skip(skip).limit(page_size).to_list(length=page_size)
    total = await db.source_jobs.count_documents({"tenant_id": tenant_id, "source_id": source_id})
    return {
        "items": [_serialize_job(j) for j in jobs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/{source_id}")
async def get_source(
    source_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    source = await source_repo.get_by_source_id(tenant_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source.pop("_id", None)
    source["chunk_count"] = await db.chunks.count_documents({
        "tenant_id": tenant_id,
        "source_id": source_id,
    })
    return source


@router.delete("/{source_id}")
async def delete_source(
    source_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    source = await source_repo.get_by_source_id(tenant_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    config = source.get("config", {})
    if source["source_type"] == "pdf":
        try:
            do_delete(tenant_id, source_id)
        except Exception as e:
            print(f"Failed to delete PDF from DO Spaces: {e}")

    await source_repo.delete(tenant_id, source_id)
    await _delete_source_data(tenant_id, source_id)

    if source["source_type"] == "faq":
        await db.faqs.delete_many({"tenant_id": tenant_id, "source_id": source_id})
    elif source["source_type"] == "text":
        await db.documents.delete_many({"tenant_id": tenant_id, "source_id": source_id})

    await db.source_jobs.update_many(
        {"tenant_id": tenant_id, "source_id": source_id},
        {"$set": {"status": "purged"}}
    )

    return {"status": "deleted", "source_id": source_id}


@router.delete("/crawl/{job_id}")
async def delete_crawl_source(
    job_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    job = await db.crawl_jobs.find_one(
        {"tenant_id": tenant_id, "job_id": job_id},
    )
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    await db.chunks.delete_many({"tenant_id": tenant_id, "crawl_id": job_id})
    await db.parents.delete_many({"tenant_id": tenant_id, "crawl_id": job_id})
    await db.pages.delete_many({"tenant_id": tenant_id, "crawl_id": job_id})

    await db.crawl_jobs.update_one(
        {"tenant_id": tenant_id, "job_id": job_id},
        {"$set": {"status": "purged", "pages_found": 0, "chunks_created": 0}}
    )

    return {"status": "deleted", "job_id": job_id}


async def _index_pdf_background(tenant_id: str, source_id: str, name: str):
    job_id = await _create_source_job(tenant_id, source_id, "pdf_index", {"name": name})
    await _update_source_job(job_id, {"status": "running", "started_at": datetime.now(timezone.utc)})

    try:
        url = get_presigned_url(tenant_id, source_id, expires=1800)
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=60)
            resp.raise_for_status()
            pdf_bytes = resp.content

        text = extract_text_from_pdf_from_bytes(pdf_bytes)
        if not text.strip():
            raise ValueError("No text could be extracted from the PDF")

        doc_id = str(uuid.uuid4())
        result = await ingest_document(
            tenant_id=tenant_id,
            source_id=source_id,
            doc_id=doc_id,
            content=text,
            title=name,
            url=f"pdf://{source_id}",
        )

        await source_repo.update(tenant_id, source_id, {
            "status": "ready",
            "last_indexed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        await _update_source_job(job_id, {
            "status": "done",
            "chunks_created": result.get("chunks_created", 0),
            "finished_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        print(f"PDF indexing failed for {source_id}: {e}")
        await source_repo.update(tenant_id, source_id, {
            "status": "failed",
            "updated_at": datetime.now(timezone.utc),
        })
        await _update_source_job(job_id, {
            "status": "failed",
            "error": str(e),
            "finished_at": datetime.now(timezone.utc),
        })


@router.post("/pdf/upload", status_code=201)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...),
    current_tenant: dict = Depends(get_current_tenant),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    tenant_id = current_tenant["tenant_id"]
    source_id = str(uuid.uuid4())

    file_bytes = await file.read()
    if len(file_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File size exceeds 100MB limit")
    try:
        do_upload(tenant_id, source_id, file_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload PDF: {e}")

    source_doc = {
        "tenant_id": tenant_id,
        "source_id": source_id,
        "source_type": "pdf",
        "name": name,
        "config": {
            "original_name": file.filename,
        },
        "status": "indexing",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "last_indexed_at": None,
    }
    await source_repo.create(source_doc)

    background_tasks.add_task(_index_pdf_background, tenant_id, source_id, name)

    source_doc.pop("_id", None)
    return source_doc


@router.get("/{source_id}/pdf_url")
async def get_pdf_url(
    source_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    source = await source_repo.get_by_source_id(tenant_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source["source_type"] != "pdf":
        raise HTTPException(status_code=400, detail="Source is not a PDF")

    try:
        url = get_presigned_url(tenant_id, source_id, expires=3600)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate URL: {e}")

    return {"url": url}