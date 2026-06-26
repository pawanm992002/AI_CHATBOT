import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from core.auth import db, get_current_tenant
from models.requests import TextDocCreateRequest, TextDocUpdateRequest
from views.responses import TextDocResponse
from services.ingestion import ingest_document
from services.suggested import generate_suggested_questions
from repositories.source_repository import SourceRepository
from repositories.text_doc_repository import TextDocRepository

router = APIRouter(prefix="/dashboard/sources/{source_id}/docs", tags=["text_docs"])
source_repo = SourceRepository()
doc_repo = TextDocRepository()


async def _verify_source(tenant_id: str, source_id: str) -> dict:
    source = await source_repo.get_by_source_id(tenant_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source["source_type"] != "text":
        raise HTTPException(status_code=400, detail="Source is not a text document source")
    return source


@router.get("")
async def list_docs(
    source_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    await _verify_source(tenant_id, source_id)

    docs = await doc_repo.get_by_source(tenant_id, source_id)
    for doc in docs:
        doc.pop("_id", None)
    return docs


@router.post("", status_code=201)
async def create_doc(
    source_id: str,
    body: TextDocCreateRequest,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    await _verify_source(tenant_id, source_id)

    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": tenant_id,
        "source_id": source_id,
        "doc_id": doc_id,
        "title": body.title,
        "body": body.body,
        "created_at": now,
        "updated_at": now,
    }
    await doc_repo.create(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{doc_id}")
async def update_doc(
    source_id: str,
    doc_id: str,
    body: TextDocUpdateRequest,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    await _verify_source(tenant_id, source_id)

    update = {}
    if body.title is not None:
        update["title"] = body.title
    if body.body is not None:
        update["body"] = body.body

    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    update["updated_at"] = datetime.now(timezone.utc)

    success = await doc_repo.update(tenant_id, source_id, doc_id, update)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = await doc_repo.get_by_doc_id(tenant_id, source_id, doc_id)
    if doc:
        doc.pop("_id", None)
    return doc


@router.delete("/{doc_id}")
async def delete_doc(
    source_id: str,
    doc_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    await _verify_source(tenant_id, source_id)

    success = await doc_repo.delete(tenant_id, source_id, doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.chunks.delete_many({
        "tenant_id": tenant_id,
        "source_id": source_id,
        "page_id": f"doc_{doc_id}",
    })
    await db.parents.delete_many({
        "tenant_id": tenant_id,
        "source_id": source_id,
        "page_id": f"doc_{doc_id}",
    })
    await db.pages.delete_many({
        "tenant_id": tenant_id,
        "source_id": source_id,
        "page_id": f"doc_{doc_id}",
    })

    return {"status": "deleted", "doc_id": doc_id}


async def _create_source_job(tenant_id: str, source_id: str, job_type: str, config: dict = None) -> str:
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


async def _index_all_docs(tenant_id: str, source_id: str):
    job_id = await _create_source_job(tenant_id, source_id, "text_index")
    await _update_source_job(job_id, {"status": "running", "started_at": datetime.now(timezone.utc)})

    try:
        await db.chunks.delete_many({"tenant_id": tenant_id, "source_id": source_id})
        await db.parents.delete_many({"tenant_id": tenant_id, "source_id": source_id})
        await db.pages.delete_many({"tenant_id": tenant_id, "source_id": source_id})

        docs = await doc_repo.get_by_source(tenant_id, source_id)

        total_chunks = 0
        for doc in docs:
            doc_id = f"doc_{doc['doc_id']}"
            result = await ingest_document(
                tenant_id=tenant_id,
                source_id=source_id,
                doc_id=doc_id,
                content=doc["body"],
                title=doc["title"],
                url=f"doc://{doc['doc_id']}",
                min_content_length=0,
            )
            total_chunks += result["chunks_created"]

        await source_repo.update(tenant_id, source_id, {
            "status": "ready",
            "last_indexed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        await _update_source_job(job_id, {
            "status": "done",
            "chunks_created": total_chunks,
            "finished_at": datetime.now(timezone.utc),
        })

        import asyncio
        asyncio.create_task(generate_suggested_questions(tenant_id))
    except Exception as e:
        print(f"Text doc indexing failed for {source_id}: {e}")
        await source_repo.update(tenant_id, source_id, {
            "status": "failed",
            "updated_at": datetime.now(timezone.utc),
        })
        await _update_source_job(job_id, {
            "status": "failed",
            "error": str(e),
            "finished_at": datetime.now(timezone.utc),
        })


@router.post("/index")
async def index_docs(
    source_id: str,
    background_tasks: BackgroundTasks,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    await _verify_source(tenant_id, source_id)

    await source_repo.update(tenant_id, source_id, {
        "status": "indexing",
        "updated_at": datetime.now(timezone.utc)
    })

    background_tasks.add_task(_index_all_docs, tenant_id, source_id)
    return {"status": "indexing", "source_id": source_id}