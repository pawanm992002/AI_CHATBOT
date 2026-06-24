import uuid
from datetime import datetime, timezone

from core.auth import db
from services.embedder import embed_texts
from services.tokens import TOKEN_ENCODING_NAME, count_tokens
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

CHILD_CHUNK_TOKENS = 500
CHILD_CHUNK_OVERLAP_TOKENS = 80
MIN_CHILD_CHUNK_TOKENS = 40
MIN_SECTION_BODY_TOKENS = 8
EMBEDDING_BATCH_SIZE = 100
MARKDOWN_HEADERS = [
    ("#", "heading_1"),
    ("##", "heading_2"),
    ("###", "heading_3"),
    ("####", "heading_4"),
]
HEADING_KEYS = [header_name for _, header_name in MARKDOWN_HEADERS]


async def ingest_document(
    tenant_id: str,
    source_id: str,
    doc_id: str,
    content: str,
    title: str = "Untitled",
    url: str = "",
    crawl_id: str = "",
) -> dict:
    """Ingest a document into the chunking/embedding/storage pipeline.

    Args:
        tenant_id: Tenant UUID
        source_id: Source UUID (from the sources collection)
        doc_id: Unique ID for this document/page
        content: Text content (markdown or plain text)
        title: Document title
        url: Optional URL (for traceability)
        crawl_id: Optional crawl job ID (for website crawls, enables dedup)

    Returns:
        dict with keys: indexed (bool), chunks_created (int), embedding_errors (int)
    """
    content = content.strip()
    if not content or len(content) < 50:
        return {"indexed": False, "chunks_created": 0, "embedding_errors": 0}

    parent_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=MARKDOWN_HEADERS,
        strip_headers=False,
    )
    child_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=TOKEN_ENCODING_NAME,
        chunk_size=CHILD_CHUNK_TOKENS,
        chunk_overlap=CHILD_CHUNK_OVERLAP_TOKENS,
    )

    parent_sections = _build_parent_sections(parent_splitter, content, title)
    if not parent_sections:
        return {"indexed": False, "chunks_created": 0, "embedding_errors": 0}

    # Include crawl_id in records if provided (used by website crawl dedup)
    extra = {}
    if crawl_id:
        extra["crawl_id"] = crawl_id

    parent_docs = []
    child_records = []
    for parent_index, section in enumerate(parent_sections):
        parent_id = f"{doc_id}:{parent_index}"
        parent_text = section["text"]
        parent_docs.append({
            "tenant_id": tenant_id,
            "source_id": source_id,
            "page_id": doc_id,
            "parent_id": parent_id,
            "url": url,
            "title": title,
            "section_title": section["section_title"],
            "section_path": section["section_path"],
            "headings": section["headings"],
            "text": parent_text,
            "token_count": count_tokens(parent_text),
            "parent_index": parent_index,
            "indexed_at": datetime.now(timezone.utc),
            **extra,
        })

        child_chunks = _split_child_chunks(child_splitter, parent_text)
        section_label = section["section_title"] or section["section_path"]
        for child_index, child in enumerate(child_chunks):
            prefixed = f"{section_label}:\n{child}"
            child_records.append({
                "parent_id": parent_id,
                "parent_index": parent_index,
                "child_index": child_index,
                "section_title": section["section_title"],
                "section_path": section["section_path"],
                "headings": section["headings"],
                "text": child,
                "search_text": prefixed,
                "token_count": count_tokens(prefixed),
                **extra,
            })

    if not child_records:
        return {"indexed": False, "chunks_created": 0, "embedding_errors": 0}

    chunk_docs = []
    embedding_errors = 0
    for start in range(0, len(child_records), EMBEDDING_BATCH_SIZE):
        batch = child_records[start:start + EMBEDDING_BATCH_SIZE]
        try:
            embeddings = await embed_texts([item["search_text"] for item in batch])
        except Exception as exc:
            print(f"Embedding batch failed for {title}: {exc}")
            embedding_errors += len(batch)
            continue

        if len(embeddings) != len(batch):
            embedding_errors += len(batch)
            continue

        for offset, (chunk, embedding) in enumerate(zip(batch, embeddings)):
            if not embedding:
                embedding_errors += 1
                continue

            chunk_docs.append({
                "tenant_id": tenant_id,
                "source_id": source_id,
                "page_id": doc_id,
                "parent_id": chunk["parent_id"],
                "url": url,
                "title": title,
                "section_title": chunk["section_title"],
                "section_path": chunk["section_path"],
                "headings": chunk["headings"],
                "text": chunk["text"],
                "token_count": chunk["token_count"],
                "embedding": embedding,
                "chunk_index": start + offset,
                "parent_index": chunk["parent_index"],
                "child_index": chunk["child_index"],
                "indexed_at": datetime.now(timezone.utc),
                **extra,
            })

    if not chunk_docs:
        return {
            "indexed": False,
            "chunks_created": 0,
            "embedding_errors": embedding_errors or len(child_records),
        }

    page_doc = {
        "tenant_id": tenant_id,
        "source_id": source_id,
        "page_id": doc_id,
        "url": url,
        "title": title,
        "content": content,
        "indexed_at": datetime.now(timezone.utc),
        **extra,
    }

    try:
        await db.pages.insert_one(page_doc)
        await db.parents.insert_many(parent_docs)
        for start in range(0, len(chunk_docs), EMBEDDING_BATCH_SIZE):
            await db.chunks.insert_many(chunk_docs[start:start + EMBEDDING_BATCH_SIZE])
    except Exception:
        await db.pages.delete_many({"tenant_id": tenant_id, "page_id": doc_id})
        await db.parents.delete_many({"tenant_id": tenant_id, "page_id": doc_id})
        await db.chunks.delete_many({"tenant_id": tenant_id, "page_id": doc_id})
        raise

    return {
        "indexed": True,
        "chunks_created": len(chunk_docs),
        "embedding_errors": embedding_errors,
    }


def _build_parent_sections(
    splitter: MarkdownHeaderTextSplitter,
    content: str,
    page_title: str,
) -> list[dict]:
    import re

    sections = []
    for doc in splitter.split_text(content):
        text = doc.page_content.strip()
        if not text:
            continue

        body_text = _section_body_text(text)
        if not body_text or count_tokens(body_text) < MIN_SECTION_BODY_TOKENS:
            continue

        headings = {key: value for key, value in doc.metadata.items() if key in HEADING_KEYS}
        section_path_parts = [headings[key] for key in HEADING_KEYS if headings.get(key)]
        section_path = " > ".join(section_path_parts) or page_title or "Untitled section"
        section_title = section_path_parts[-1] if section_path_parts else page_title or "Untitled section"

        sections.append({
            "text": text,
            "section_title": section_title,
            "section_path": section_path,
            "headings": headings,
        })

    if sections:
        return sections

    return [{
        "text": content.strip(),
        "section_title": page_title or "Untitled section",
        "section_path": page_title or "Untitled section",
        "headings": {},
    }]


def _split_child_chunks(
    splitter: RecursiveCharacterTextSplitter,
    parent_text: str,
) -> list[str]:
    raw_chunks = [chunk.strip() for chunk in splitter.split_text(parent_text) if chunk.strip()]
    if len(raw_chunks) <= 1:
        return raw_chunks

    chunks = []
    pending = ""
    for chunk in raw_chunks:
        if pending:
            chunk = f"{pending}\n\n{chunk}"
            pending = ""

        if count_tokens(chunk) < MIN_CHILD_CHUNK_TOKENS:
            pending = chunk
            continue

        chunks.append(chunk)

    if pending:
        if chunks:
            chunks[-1] = f"{chunks[-1]}\n\n{pending}"
        else:
            chunks.append(pending)

    return chunks


def _section_body_text(section_text: str) -> str:
    import re

    body_lines = []
    for line in section_text.splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s+", line):
            continue
        body_lines.append(line)
    return "\n".join(body_lines).strip()


async def ingest_faq_pair(
    tenant_id: str,
    source_id: str,
    question: str,
    answer: str,
) -> str:
    """Ingest a single FAQ pair as a document."""
    import uuid
    from datetime import datetime, timezone

    doc_id = str(uuid.uuid4())
    content = f"Q: {question}\nA: {answer}"
    title = question[:80]

    result = await ingest_document(
        tenant_id=tenant_id,
        source_id=source_id,
        doc_id=doc_id,
        content=content,
        title=title,
    )

    if not result["indexed"]:
        raise Exception("Failed to index FAQ")

    return doc_id
