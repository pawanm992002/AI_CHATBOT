from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel
from core.auth import create_access_token, get_current_admin, db, set_auth_cookie, clear_auth_cookie
from core.config import settings
import os

from core.rate_limiter import RateLimiter

router = APIRouter(prefix="/admin", tags=["admin"])

class AdminLogin(BaseModel):
    username: str
    password: str

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

@router.post("/login", dependencies=[Depends(RateLimiter(limit=5, window=60, key_prefix="admin_login"))])
async def admin_login(creds: AdminLogin, response: Response, request: Request):
    if creds.username == ADMIN_USERNAME and creds.password == ADMIN_PASSWORD:
        access_token = create_access_token(data={"sub": "system_admin", "role": "admin"})
        set_auth_cookie(response, access_token, request)
        return {"access_token": access_token, "token_type": "bearer"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect admin username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

@router.post("/logout")
async def admin_logout(response: Response, request: Request):
    clear_auth_cookie(response, request)
    return {"message": "logged out"}

@router.get("/me")
async def admin_me(admin: dict = Depends(get_current_admin)):
    return {"username": admin["username"], "role": admin["role"]}

import secrets
import math
from core.auth import hash_api_key

@router.get("/tenants")
async def get_all_tenants(
    page: int = 1,
    limit: int = 10,
    search: str | None = None,
    status: str | None = None,
    admin: dict = Depends(get_current_admin)
):
    query = {}
    if status:
        query["status"] = status
    if search:
        search_regex = {"$regex": search, "$options": "i"}
        query["$or"] = [
            {"business_name": search_regex},
            {"email": search_regex},
            {"domain": search_regex}
        ]

    total = await db.tenants.count_documents(query)
    skip = (page - 1) * limit
    tenants_cursor = db.tenants.find(query, {"password_hash": 0}).skip(skip).limit(limit)
    tenants = await tenants_cursor.to_list(length=limit)

    for t in tenants:
        t["_id"] = str(t["_id"])

    total_pages = math.ceil(total / limit) if limit > 0 else 0

    return {
        "items": tenants,
        "total": total,
        "page": page,
        "page_size": limit,
        "total_pages": total_pages
    }

@router.post("/tenants/{tenant_id}/approve")
async def approve_tenant(tenant_id: str, admin: dict = Depends(get_current_admin)):
    tenant = await db.tenants.find_one({"tenant_id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = {"status": "approved"}
    api_key = tenant.get("api_key", "")
    if not api_key or api_key.startswith("pending_"):
        new_api_key = f"sk_live_{secrets.token_urlsafe(32)}"
        update_data["api_key"] = new_api_key
        update_data["api_key_hash"] = hash_api_key(new_api_key)

    await db.tenants.update_one({"tenant_id": tenant_id}, {"$set": update_data})
    return {"message": "Tenant approved successfully", "api_key": update_data.get("api_key", api_key)}

@router.post("/tenants/{tenant_id}/reject")
async def reject_tenant(tenant_id: str, admin: dict = Depends(get_current_admin)):
    tenant = await db.tenants.find_one({"tenant_id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await db.tenants.update_one({"tenant_id": tenant_id}, {"$set": {"status": "rejected"}})
    return {"message": "Tenant rejected successfully"}

@router.post("/tenants/{tenant_id}/enable")
async def enable_tenant(tenant_id: str, admin: dict = Depends(get_current_admin)):
    tenant = await db.tenants.find_one({"tenant_id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = {"status": "approved"}
    api_key = tenant.get("api_key", "")
    if not api_key or api_key.startswith("pending_"):
        new_api_key = f"sk_live_{secrets.token_urlsafe(32)}"
        update_data["api_key"] = new_api_key
        update_data["api_key_hash"] = hash_api_key(new_api_key)

    await db.tenants.update_one({"tenant_id": tenant_id}, {"$set": update_data})
    return {"message": "Tenant enabled successfully", "api_key": update_data.get("api_key", api_key)}

@router.post("/tenants/{tenant_id}/disable")
async def disable_tenant(tenant_id: str, admin: dict = Depends(get_current_admin)):
    tenant = await db.tenants.find_one({"tenant_id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await db.tenants.update_one({"tenant_id": tenant_id}, {"$set": {"status": "disabled"}})
    return {"message": "Tenant disabled successfully"}

@router.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str, admin: dict = Depends(get_current_admin)):
    result = await db.tenants.delete_one({"tenant_id": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await db.pages.delete_many({"tenant_id": tenant_id})
    await db.chunks.delete_many({"tenant_id": tenant_id})
    await db.parents.delete_many({"tenant_id": tenant_id})
    await db.conversations.delete_many({"tenant_id": tenant_id})
    await db.sources.delete_many({"tenant_id": tenant_id})
    await db.leads.delete_many({"tenant_id": tenant_id})
    await db.lead_form_configs.delete_many({"tenant_id": tenant_id})
    await db.crawl_jobs.delete_many({"tenant_id": tenant_id})
    await db.faqs.delete_many({"tenant_id": tenant_id})
    await db.documents.delete_many({"tenant_id": tenant_id})
    await db.visitors.delete_many({"tenant_id": tenant_id})

    return {"message": "Tenant and associated data deleted successfully"}