from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel
from core.auth import create_access_token, get_current_admin, db, set_auth_cookie, clear_auth_cookie
from core.config import settings
import os

router = APIRouter(prefix="/admin", tags=["admin"])

class AdminLogin(BaseModel):
    username: str
    password: str

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

@router.post("/login")
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

@router.get("/tenants")
async def get_all_tenants(admin: dict = Depends(get_current_admin)):
    tenants_cursor = db.tenants.find({}, {"password_hash": 0})
    tenants = await tenants_cursor.to_list(length=None)

    for t in tenants:
        t["_id"] = str(t["_id"])

    return tenants

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
    await db.crawl_jobs.delete_many({"tenant_id": tenant_id})
    await db.faqs.delete_many({"tenant_id": tenant_id})
    await db.documents.delete_many({"tenant_id": tenant_id})
    await db.visitors.delete_many({"tenant_id": tenant_id})

    return {"message": "Tenant and associated data deleted successfully"}