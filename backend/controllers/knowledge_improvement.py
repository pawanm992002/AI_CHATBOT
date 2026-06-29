from fastapi import APIRouter, Depends, HTTPException, Query
from core.auth import get_current_tenant, db
from services.embedder import embed_text
from services.ingestion import ingest_faq_pair
from repositories.knowledge_gap_repository import KnowledgeGapRepository, _vector_search_faqs
from repositories.source_repository import SourceRepository
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
import numpy as np
from pydantic import BaseModel

router = APIRouter(prefix="/dashboard/knowledge", tags=["knowledge-improvement"])
gap_repo = KnowledgeGapRepository()


class GapResponse(BaseModel):
    gap_id: str
    query: str
    url: str
    gap_type: str
    count: int
    status: str
    first_seen: datetime
    last_seen: datetime
    resolved_by_faq_id: Optional[str] = None
    similar_faqs: list = []


class ResolveGapRequest(BaseModel):
    action: str
    faq_question: Optional[str] = None
    faq_answer: Optional[str] = None
    source_id: Optional[str] = None
    merge_into_id: Optional[str] = None


@router.get("/gaps")
async def list_knowledge_gaps(
    current_tenant: dict = Depends(get_current_tenant),
    status: str = Query("open"),
    gap_type: Optional[str] = Query(None),
    limit: int = Query(50),
    skip: int = Query(0),
):
    tenant_id = current_tenant["tenant_id"]

    query_filter = {"tenant_id": tenant_id}
    if status != "all":
        query_filter["status"] = status
    if gap_type:
        query_filter["gap_type"] = gap_type

    total = await db.knowledge_gaps.count_documents(query_filter)

    cursor = db.knowledge_gaps.find(query_filter).sort("count", -1).skip(skip).limit(limit)
    gaps = await cursor.to_list(limit)

    result = []
    for gap in gaps:
        try:
            gap["gap_id"] = str(gap["_id"])
            gap.pop("_id", None)
            gap_embedding = gap.pop("embedding", None)

            similar_faqs = []
            if gap_embedding:
                faq_results = await _vector_search_faqs(tenant_id, gap_embedding, threshold=0.80, limit=3)
                for faq in faq_results:
                    similar_faqs.append({
                        "faq_id": str(faq["_id"]),
                        "question": faq["question"],
                        "similarity": round(faq.get("score", 0), 3),
                    })

            gap["similar_faqs"] = similar_faqs
            result.append(gap)
        except Exception as e:
            print(f"[KNOWLEDGE] error processing gap: {e}")

    return {"items": result, "total": total, "page": (skip // limit) + 1, "page_size": limit, "total_pages": max(1, -(-total // limit))}


@router.post("/gaps/{gap_id}/resolve")
async def resolve_knowledge_gap(
    gap_id: str,
    req: ResolveGapRequest,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]

    gap = await db.knowledge_gaps.find_one({"_id": ObjectId(gap_id), "tenant_id": tenant_id})
    if not gap:
        raise HTTPException(status_code=404, detail="Gap not found")

    if req.action == "create_faq":
        if not req.faq_question or not req.faq_answer or not req.source_id:
            raise HTTPException(status_code=400, detail="faq_question, faq_answer, and source_id required")

        faq_id = await ingest_faq_pair(
            tenant_id=tenant_id,
            source_id=req.source_id,
            question=req.faq_question,
            answer=req.faq_answer,
        )

        faq_embedding = await embed_text(f"Q: {req.faq_question}\nA: {req.faq_answer}")

        await db.faqs.update_one(
            {"_id": ObjectId(faq_id)},
            {"$set": {"embedding": faq_embedding}}
        )

        await db.knowledge_gaps.update_one(
            {"_id": ObjectId(gap_id)},
            {"$set": {"status": "resolved", "resolved_by_faq_id": faq_id}}
        )

        return {"status": "ok", "faq_id": faq_id}

    elif req.action == "dismiss":
        await db.knowledge_gaps.update_one(
            {"_id": ObjectId(gap_id)},
            {"$set": {"status": "dismissed"}}
        )
        return {"status": "ok"}

    elif req.action == "merge":
        if not req.merge_into_id:
            raise HTTPException(status_code=400, detail="merge_into_id required for merge action")

        target_gap = await db.knowledge_gaps.find_one({"_id": ObjectId(req.merge_into_id), "tenant_id": tenant_id})
        if not target_gap:
            raise HTTPException(status_code=404, detail="Target gap not found")

        await db.knowledge_gaps.update_one(
            {"_id": ObjectId(req.merge_into_id)},
            {
                "$inc": {"count": gap.get("count", 1)},
                "$set": {"last_seen": max(gap.get("last_seen", datetime.now(timezone.utc)), target_gap.get("last_seen", datetime.now(timezone.utc)))}
            }
        )

        await db.knowledge_gaps.delete_one({"_id": ObjectId(gap_id)})

        return {"status": "ok", "merged_into": req.merge_into_id}

    else:
        raise HTTPException(status_code=400, detail="Invalid action")


@router.get("/gaps/stats")
async def get_gap_stats(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]

    total = await db.knowledge_gaps.count_documents({"tenant_id": tenant_id})
    open_count = await gap_repo.count_by_tenant(tenant_id, status="open")
    resolved = await gap_repo.count_by_tenant(tenant_id, status="resolved")
    dismissed = await gap_repo.count_by_tenant(tenant_id, status="dismissed")

    no_context_open = await db.knowledge_gaps.count_documents({"tenant_id": tenant_id, "status": "open", "gap_type": "no_context"})
    out_of_scope_open = await db.knowledge_gaps.count_documents({"tenant_id": tenant_id, "status": "open", "gap_type": "out_of_scope"})

    top_gaps = await db.knowledge_gaps.find(
        {"tenant_id": tenant_id, "status": "open"}
    ).sort("count", -1).limit(10).to_list(10)

    return {
        "total": total,
        "open": open_count,
        "resolved": resolved,
        "dismissed": dismissed,
        "no_context": no_context_open,
        "out_of_scope": out_of_scope_open,
        "top_gaps": [
            {"gap_id": str(g["_id"]), "query": g["query"], "count": g["count"]}
            for g in top_gaps
        ]
    }


@router.post("/gaps/cluster")
async def cluster_gaps(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]

    gaps = await db.knowledge_gaps.find(
        {"tenant_id": tenant_id, "status": "open", "embedding": {"$exists": True}}
    ).to_list(1000)

    if len(gaps) < 2:
        return {"clusters": 0, "message": "Not enough gaps to cluster"}

    SIMILARITY_THRESHOLD = 0.85
    parent = {str(g["_id"]): str(g["_id"]) for g in gaps}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    embeddings = {}
    for gap in gaps:
        gid = str(gap["_id"])
        embeddings[gid] = np.array(gap["embedding"])

    gap_ids = list(embeddings.keys())
    for i in range(len(gap_ids)):
        for j in range(i + 1, len(gap_ids)):
            id_a, id_b = gap_ids[i], gap_ids[j]
            cos_sim = np.dot(embeddings[id_a], embeddings[id_b]) / (
                np.linalg.norm(embeddings[id_a]) * np.linalg.norm(embeddings[id_b])
            )
            if cos_sim > SIMILARITY_THRESHOLD:
                union(id_a, id_b)

    clusters = {}
    for gap_id in gap_ids:
        root = find(gap_id)
        if root not in clusters:
            clusters[root] = f"cluster_{root[:8]}"
        cluster_id = clusters[root]
        await db.knowledge_gaps.update_one(
            {"_id": ObjectId(gap_id)},
            {"$set": {"cluster_id": cluster_id}}
        )

    return {"clusters_created": len(clusters), "total_gaps": len(gaps)}


@router.post("/gaps/cleanup")
async def cleanup_duplicates(current_tenant: dict = Depends(get_current_tenant)):
    import re
    tenant_id = current_tenant["tenant_id"]

    gaps = await db.knowledge_gaps.find(
        {"tenant_id": tenant_id, "status": "open"}
    ).to_list(1000)

    def normalize_query(q):
        n = q.lower().strip()
        n = re.sub(r'[^\w\s]', '', n)
        n = re.sub(r'\s+', ' ', n)
        return n

    merged = 0
    seen = {}

    for gap in gaps:
        norm = normalize_query(gap["query"])
        if norm in seen:
            target_id = seen[norm]
            await db.knowledge_gaps.update_one(
                {"_id": ObjectId(target_id)},
                {
                    "$inc": {"count": gap.get("count", 1)},
                    "$set": {"last_seen": datetime.now(timezone.utc)}
                }
            )
            await db.knowledge_gaps.delete_one({"_id": gap["_id"]})
            merged += 1
        else:
            seen[norm] = str(gap["_id"])

    return {"merged": merged, "remaining": len(gaps) - merged}