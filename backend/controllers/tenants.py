import os
import string
import json
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from fastapi.responses import HTMLResponse
from models.requests import TenantRegisterRequest, TenantLoginRequest, SuggestedQuestionsUpdateRequest
from views.responses import TokenResponse, TenantResponse
from core.auth import db, get_password_hash, verify_password, create_access_token, get_current_tenant, set_auth_cookie, clear_auth_cookie, hash_api_key
from repositories.tenant_repository import TenantRepository
import uuid
import secrets
from datetime import datetime, timezone

router = APIRouter(prefix="/tenants", tags=["tenants"])
test_router = APIRouter(tags=["test"])
tenant_repo = TenantRepository()

_DEFAULT_AI = {"provider": "openai", "model": "gpt-4o-mini"}
_MODELS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "models.json")


def _build_knowledge_html(sources: list, faq_count: int) -> str:
    websites = [s for s in sources if s.get("source_type") == "website"]
    docs = [s for s in sources if s.get("source_type") in ("pdf", "text")]
    has_any = websites or docs or faq_count > 0

    if not has_any:
        return (
            '<div class="empty-state">'
            '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
            '<p>No knowledge sources configured yet.</p>'
            '<p class="empty-hint">Add content in the dashboard to get started.</p>'
            '</div>'
        )

    columns = []

    if websites:
        items = "".join(
            '<div class="source-item">'
            '<div class="source-icon">\U0001F310</div>'
            '<div class="source-info">'
            f'<span class="source-name" title="{s["name"]}">{s["name"]}</span>'
            f'<span class="source-meta">{s.get("chunk_count", 0):,} chunks &middot; {s.get("config", {}).get("pages_found", 0)} pages</span>'
            '</div></div>'
            for s in websites
        )
        columns.append(f'<div class="knowledge-col"><h4 class="col-title">\U0001F310 Websites ({len(websites)})</h4>{items}</div>')
    else:
        columns.append('<div class="knowledge-col"><h4 class="col-title">\U0001F310 Websites</h4><p class="col-empty">No website sources yet</p></div>')

    if docs:
        items = "".join(
            '<div class="source-item">'
            '<div class="source-icon">\U0001F4C4</div>'
            '<div class="source-info">'
            f'<span class="source-name" title="{s["name"]}">{s["name"]}</span>'
            f'<span class="source-meta">{s.get("chunk_count", 0):,} chunks</span>'
            '</div></div>'
            for s in docs
        )
        columns.append(f'<div class="knowledge-col"><h4 class="col-title">\U0001F4C4 Documents ({len(docs)})</h4>{items}</div>')
    else:
        columns.append('<div class="knowledge-col"><h4 class="col-title">\U0001F4C4 Documents</h4><p class="col-empty">No documents uploaded yet</p></div>')

    if faq_count > 0:
        columns.append(
            f'<div class="knowledge-col">'
            f'<h4 class="col-title">\u2753 FAQs ({faq_count})</h4>'
            f'<div class="source-item">'
            f'<div class="source-icon">\u2753</div>'
            f'<div class="source-info">'
            f'<span class="source-name">Questions &amp; Answers</span>'
            f'<span class="source-meta">{faq_count} questions answered</span>'
            f'</div></div></div>'
        )
    else:
        columns.append('<div class="knowledge-col"><h4 class="col-title">\u2753 FAQs</h4><p class="col-empty">No FAQs added yet</p></div>')

    return f'<div class="knowledge-grid">{"".join(columns)}</div>'


def _build_leads_html(lead_forms: list) -> str:
    if not lead_forms:
        return (
            '<div class="empty-state">'
            '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
            '<p>No lead forms configured.</p>'
            '<p class="empty-hint">Set one up in the dashboard to capture visitor enquiries.</p>'
            '</div>'
        )

    items = []
    for form in lead_forms:
        status = "\u2705 Active" if form.get("enabled", True) else "\u23F8\uFE0F Disabled"
        field_count = len(form.get("fields", []))
        items.append(
            '<div class="lead-item">'
            '<div class="lead-info">'
            f'<span class="lead-name">{form.get("title", "Untitled Form")}</span>'
            f'<span class="lead-meta">{field_count} field{"s" if field_count != 1 else ""} &middot; {status}</span>'
            '</div></div>'
        )

    return f'<div class="leads-list">{"".join(items)}</div>'


def _load_models_catalog() -> list[dict]:
    try:
        with open(_MODELS_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load models catalog at {_MODELS_PATH}: {e!r}") from e


def _validate_provider_model(provider: str, model: str) -> None:
    provider_norm = (provider or "").strip().lower()
    model_norm = (model or "").strip()
    allowed = any(
        (m.get("provider") or "").strip().lower() == provider_norm and (m.get("id") or "").strip() == model_norm
        for m in _load_models_catalog()
    )
    if not allowed:
        raise HTTPException(status_code=400, detail=f"Invalid provider/model: {provider}/{model}")

@router.post("/register")
async def register(tenant: TenantRegisterRequest):
    existing = await tenant_repo.get_by_domain(tenant.domain)
    if existing:
        raise HTTPException(status_code=400, detail="Domain already registered")

    tenant_id = str(uuid.uuid4())
    api_key = f"pending_{secrets.token_urlsafe(32)}"

    tenant_data = {
        "tenant_id": tenant_id,
        "api_key": api_key,
        "api_key_hash": hash_api_key(api_key),
        "domain": tenant.domain,
        "business_name": tenant.business_name,
        "email": tenant.email,
        "plan": tenant.plan,
        "theme": tenant.theme,
        "description": tenant.description,
        "password_hash": get_password_hash(tenant.password),
        "suggested_questions_manual": [],
        "suggested_questions_auto": [],
        "show_sources": True,
        "ai": dict(_DEFAULT_AI),
        "created_at": datetime.now(timezone.utc),
        "status": "pending"
    }
    await tenant_repo.create(tenant_data)

    return {"message": "Registration successful! Your account is pending administrator approval."}

@router.post("/login", response_model=TokenResponse)
async def login(tenant: TenantLoginRequest, response: Response, request: Request):
    db_tenant = await tenant_repo.get_by_domain(tenant.domain)
    if not db_tenant or not verify_password(tenant.password, db_tenant["password_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect domain or password")

    status_val = db_tenant.get("status", "approved")
    if status_val == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant is disabled")
    elif status_val == "pending":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your registration is pending approval")
    elif status_val == "rejected":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your registration has been rejected")

    access_token = create_access_token(data={"sub": db_tenant["tenant_id"], "role": "tenant"})
    set_auth_cookie(response, access_token, request)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(response: Response, request: Request):
    clear_auth_cookie(response, request)
    return {"message": "logged out"}

@router.get("/me", response_model=TenantResponse)
async def get_me(current_tenant: dict = Depends(get_current_tenant)):
    return {
        "tenant_id": current_tenant["tenant_id"],
        "domain": current_tenant["domain"],
        "business_name": current_tenant.get("business_name"),
        "email": current_tenant.get("email"),
        "plan": current_tenant.get("plan", "free"),
        "theme": current_tenant.get("theme", "default"),
        "description": current_tenant.get("description"),
        "api_key": current_tenant["api_key"],
        "suggested_questions_manual": current_tenant.get("suggested_questions_manual", []),
        "suggested_questions_auto": current_tenant.get("suggested_questions_auto", []),
        "show_sources": current_tenant.get("show_sources", True),
        "ai": current_tenant.get("ai", dict(_DEFAULT_AI)),
        "created_at": current_tenant.get("created_at", datetime.now(timezone.utc)),
    }

@router.post("/rotate_key")
async def rotate_key(current_tenant: dict = Depends(get_current_tenant)):
    new_api_key = f"sk_live_{secrets.token_urlsafe(32)}"
    await tenant_repo.update_api_key_hash(current_tenant["tenant_id"], hash_api_key(new_api_key))
    await tenant_repo.update(current_tenant["tenant_id"], {"api_key": new_api_key})
    return {"api_key": new_api_key}

@router.put("/description")
async def update_description(description: str, current_tenant: dict = Depends(get_current_tenant)):
    await tenant_repo.update(current_tenant["tenant_id"], {"description": description})
    return {"status": "ok", "description": description}

@router.put("/info")
async def update_business_info(
    business_name: str | None = None,
    email: str | None = None,
    current_tenant: dict = Depends(get_current_tenant),
):
    updates = {}
    if business_name is not None:
        updates["business_name"] = business_name
    if email is not None:
        updates["email"] = email
    if updates:
        await tenant_repo.update(current_tenant["tenant_id"], updates)
    return {"status": "ok", **updates}

@router.put("/widget-settings")
async def update_widget_settings(show_sources: bool, current_tenant: dict = Depends(get_current_tenant)):
    await tenant_repo.update(current_tenant["tenant_id"], {"show_sources": show_sources})
    return {"status": "ok", "show_sources": show_sources}

@router.put("/ai")
async def update_ai_config(payload: dict, current_tenant: dict = Depends(get_current_tenant)):
    provider = (payload.get("provider") or "").strip()
    model = (payload.get("model") or "").strip()

    if not provider or not model:
        raise HTTPException(status_code=400, detail="provider and model are required")

    _validate_provider_model(provider, model)

    ok = await tenant_repo.update(
        current_tenant["tenant_id"],
        {"ai": {"provider": provider.lower(), "model": model}},
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {"status": "ok", "ai": {"provider": provider.lower(), "model": model}}

@router.get("/stats")
async def get_stats(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]
    pages = await db.pages.count_documents({"tenant_id": tenant_id})
    chunks = await db.chunks.count_documents({"tenant_id": tenant_id})
    queries = await db.conversations.count_documents({"tenant_id": tenant_id})
    crawl_sources = await db.crawl_jobs.count_documents({"tenant_id": tenant_id, "status": "done"})
    doc_sources = await db.sources.count_documents({"tenant_id": tenant_id})
    return {
        "pages_crawled": pages,
        "chunks_indexed": chunks,
        "queries_this_month": queries,
        "knowledge_sources": crawl_sources + doc_sources,
    }

@router.put("/suggested-questions")
async def update_suggested_questions(req: SuggestedQuestionsUpdateRequest, current_tenant: dict = Depends(get_current_tenant)):
    await tenant_repo.update(current_tenant["tenant_id"], {"suggested_questions_manual": req.questions})
    return {"status": "ok", "questions": req.questions}

@router.get("/analytics/feedback")
async def get_feedback_analytics(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]
    total = await db.message_feedback.count_documents({"tenant_id": tenant_id})
    likes = await db.message_feedback.count_documents({"tenant_id": tenant_id, "rating": "like"})
    dislikes = await db.message_feedback.count_documents({"tenant_id": tenant_id, "rating": "dislike"})
    return {
        "total": total,
        "likes": likes,
        "dislikes": dislikes,
        "like_ratio": round(likes / total * 100, 1) if total > 0 else 0,
    }


@test_router.get("/{business_name_slug}/test", response_class=HTMLResponse)
async def test_chatbot(business_name_slug: str, current_tenant: dict = Depends(get_current_tenant)):
    """Serve a standalone test page with the widget pre-configured with tenant's API key."""
    tenant_id = current_tenant["tenant_id"]

    # Query explicit sources
    sources = await db.sources.find({"tenant_id": tenant_id}).to_list(100)
    for s in sources:
        s.pop("_id", None)
        s["chunk_count"] = await db.chunks.count_documents({
            "tenant_id": tenant_id, "source_id": s["source_id"]
        })

    # Query crawl-derived website sources
    crawl_jobs = await db.crawl_jobs.find(
        {"tenant_id": tenant_id, "status": "done"}
    ).to_list(100)
    for job in crawl_jobs:
        sources.append({
            "source_type": "website",
            "name": job.get("seed_url", "Website"),
            "chunk_count": job.get("chunks_created", 0),
            "config": {"pages_found": job.get("pages_found", 0)},
        })

    # Query FAQs
    faq_count = await db.faqs.count_documents({"tenant_id": tenant_id})

    # Query lead forms
    lead_forms = await db.lead_form_configs.find({"tenant_id": tenant_id}).to_list(10)
    for lf in lead_forms:
        lf.pop("_id", None)

    # Build HTML sections
    knowledge_html = _build_knowledge_html(sources, faq_count)
    leads_html = _build_leads_html(lead_forms)

    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "test_page.html")
    with open(template_path) as f:
        template = string.Template(f.read())

    html = template.safe_substitute(
        business_name=current_tenant.get("business_name") or current_tenant["domain"],
        domain=current_tenant.get("domain") or "localhost",
        description=current_tenant.get("description") or "",
        api_key=current_tenant["api_key"],
        api_base_url=current_tenant.get("api_base_url") or "",
        knowledge_html=knowledge_html,
        leads_html=leads_html,
    )
    return HTMLResponse(content=html)