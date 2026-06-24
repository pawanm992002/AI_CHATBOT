import asyncio
from core.auth import db
from services.embedder import embed_text
from services.tokens import count_tokens

MAX_PARENT_CONTEXT_TOKENS = 1600
CHILD_CONTEXT_RADIUS = 1
BM25_INDEX_NAME = "BM25_textsearch"

async def _vector_search(tenant_id: str, query_vector: list[float], limit: int) -> list[dict]:
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": max(limit * 10, 100),
                "limit": limit,
                "filter": {"tenant_id": tenant_id}
            }
        },
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"_id": 0, "text": 1, "url": 1, "title": 1, "parent_id": 1,
                      "section_title": 1, "section_path": 1, "chunk_index": 1,
                      "parent_index": 1, "child_index": 1, "token_count": 1, "score": 1}},
    ]
    return await db.chunks.aggregate(pipeline).to_list(length=limit)


async def _bm25_search(tenant_id: str, query: str, top_k: int) -> list[dict]:
    try:
        pipeline = [
            {
                "$search": {
                    "index": BM25_INDEX_NAME,
                    "text": {"query": query, "path": ["text", "section_title"]}
                }
            },
            {"$match": {"tenant_id": tenant_id}},
            {"$addFields": {"score": {"$meta": "searchScore"}}},
            {"$project": {"_id": 0, "text": 1, "url": 1, "title": 1, "parent_id": 1,
                          "section_title": 1, "section_path": 1, "chunk_index": 1,
                          "parent_index": 1, "child_index": 1, "token_count": 1, "score": 1}},
            {"$limit": top_k},
        ]
        return await db.chunks.aggregate(pipeline).to_list(length=top_k)
    except Exception:
        # If BM25 index doesn't exist yet, silently skip
        return []


async def search_chunks(tenant_id: str, query: str, top_k: int = 5):
    query_vector = await embed_text(query)
    vector_slots = max(top_k - 2, 1)   # 3 slots from vector
    bm25_slots = top_k - vector_slots  # 2 slots from BM25
    child_limit = vector_slots * 3     # 9 candidates needed to find 3 unique parents

    # Run vector search and BM25 search in parallel
    vector_task = _vector_search(tenant_id, query_vector, child_limit)
    bm25_task = _bm25_search(tenant_id, query, bm25_slots * 3)
    vector_results, bm25_results = await asyncio.gather(vector_task, bm25_task)

    # Guaranteed slots: 3 from vector, 2 from BM25, deduplicated
    seen_ids = set()
    merged = []

    # First: guaranteed vector slots
    for r in vector_results:
        pid = r.get("parent_id")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            merged.append(r)
            if len(merged) >= vector_slots:
                break

    # Then: guaranteed BM25 slots (filling gaps vector didn't cover)
    bm25_added = 0
    for r in bm25_results:
        if bm25_added >= bm25_slots:
            break
        pid = r.get("parent_id")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            merged.append(r)
            bm25_added += 1

    # Finally: if BM25 didn't fill all its slots, fill with more vector results
    if len(merged) < top_k:
        for r in vector_results:
            pid = r.get("parent_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                merged.append(r)
                if len(merged) >= top_k:
                    break

    child_results = merged

    parent_ids = list(dict.fromkeys(r["parent_id"] for r in child_results if r.get("parent_id")))
    parents_by_id = {}
    if parent_ids:
        parents = await db.parents.find(
            {"tenant_id": tenant_id, "parent_id": {"$in": parent_ids}},
            {
                "_id": 0,
                "parent_id": 1,
                "url": 1,
                "title": 1,
                "section_title": 1,
                "section_path": 1,
                "headings": 1,
                "text": 1,
                "token_count": 1,
                "parent_index": 1,
            },
        ).to_list(length=len(parent_ids))
        parents_by_id = {parent["parent_id"]: parent for parent in parents}

    results = []
    seen_contexts = set()
    for child in child_results:
        parent = parents_by_id.get(child.get("parent_id"))
        if parent:
            key = parent["parent_id"]
            if key in seen_contexts:
                continue

            context_text, context_scope = await _context_for_parent_match(tenant_id, parent, child)
            merged = {
                "parent_id": parent["parent_id"],
                "url": parent["url"],
                "title": parent.get("title"),
                "section_title": parent.get("section_title"),
                "section_path": parent.get("section_path"),
                "headings": parent.get("headings", {}),
                "text": context_text,
                "context_scope": context_scope,
                "parent_index": parent.get("parent_index"),
                "score": child["score"],
                "child_text": child["text"],
                "child_index": child.get("child_index"),
            }
        else:
            key = f"{child.get('url')}:{child.get('chunk_index')}:{child.get('text')}"
            if key in seen_contexts:
                continue

            merged = child

        seen_contexts.add(key)
        results.append(merged)
        if len(results) >= top_k:
            break

    return results

async def _context_for_parent_match(tenant_id: str, parent: dict, child: dict) -> tuple[str, str]:
    parent_text = parent.get("text", "")
    parent_token_count = parent.get("token_count")
    if parent_token_count is None:
        parent_token_count = count_tokens(parent_text)

    if parent_token_count <= MAX_PARENT_CONTEXT_TOKENS:
        return parent_text, "parent_section"

    child_index = child.get("child_index")
    if child_index is None:
        return child.get("text", ""), "matched_child"

    start_index = max(0, child_index - CHILD_CONTEXT_RADIUS)
    end_index = child_index + CHILD_CONTEXT_RADIUS
    child_window = await db.chunks.find(
        {
            "tenant_id": tenant_id,
            "parent_id": parent["parent_id"],
            "child_index": {"$gte": start_index, "$lte": end_index},
        },
        {
            "_id": 0,
            "text": 1,
            "child_index": 1,
        },
    ).sort("child_index", 1).to_list(length=(CHILD_CONTEXT_RADIUS * 2) + 1)

    if not child_window:
        return child.get("text", ""), "matched_child"

    return "\n\n".join(item["text"] for item in child_window), "child_window"
