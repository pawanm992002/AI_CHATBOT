import os
import string
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import HTMLResponse
from models.requests import TenantRegisterRequest, TenantLoginRequest, SuggestedQuestionsUpdateRequest
from views.responses import TokenResponse, TenantResponse
from core.auth import db, get_password_hash, verify_password, create_access_token, get_current_tenant, set_auth_cookie, clear_auth_cookie, hash_api_key
from repositories.tenant_repository import TenantRepository
import uuid
import secrets
from datetime import datetime, timezone

router = APIRouter(prefix="/tenants", tags=["tenants"])
tenant_repo = TenantRepository()

@router.post("/register", response_model=TokenResponse)
async def register(tenant: TenantRegisterRequest, response: Response, request: Request):
    existing = await tenant_repo.get_by_domain(tenant.domain)
    if existing:
        raise HTTPException(status_code=400, detail="Domain already registered")

    tenant_id = str(uuid.uuid4())
    api_key = f"sk_live_{secrets.token_urlsafe(32)}"

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
        "created_at": datetime.now(timezone.utc)
    }
    await tenant_repo.create(tenant_data)

    access_token = create_access_token(data={"sub": tenant_id, "role": "tenant"})
    set_auth_cookie(response, access_token, request)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=TokenResponse)
async def login(tenant: TenantLoginRequest, response: Response, request: Request):
    db_tenant = await tenant_repo.get_by_domain(tenant.domain)
    if not db_tenant or not verify_password(tenant.password, db_tenant["password_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect domain or password")

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

@router.put("/widget-settings")
async def update_widget_settings(show_sources: bool, current_tenant: dict = Depends(get_current_tenant)):
    await tenant_repo.update(current_tenant["tenant_id"], {"show_sources": show_sources})
    return {"status": "ok", "show_sources": show_sources}

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


@router.get("/test", response_class=HTMLResponse)
async def test_chatbot(current_tenant: dict = Depends(get_current_tenant)):
    """Serve a standalone test page with the widget pre-configured with tenant's API key."""
    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "test_page.html")
    with open(template_path) as f:
        template = string.Template(f.read())

    html = template.safe_substitute(
        business_name=current_tenant.get("business_name") or current_tenant["domain"],
        api_key=current_tenant["api_key"],
        api_base_url=current_tenant.get("api_base_url") or "",
    )
    return HTMLResponse(content=html)