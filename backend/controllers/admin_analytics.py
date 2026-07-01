"""Admin analytics controller — thin HTTP layer for platform-wide usage analytics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from core.auth import get_current_admin
from services import admin_analytics_service

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


@router.get("/overview")
async def overview(admin: dict = Depends(get_current_admin)):
    """Return platform-wide KPIs."""
    return await admin_analytics_service.get_platform_overview()


@router.get("/timeseries")
async def timeseries(
    period: str = "30d",
    admin: dict = Depends(get_current_admin),
):
    """Return daily time-series data for the given period."""
    return await admin_analytics_service.get_timeseries(period)


@router.get("/tenants")
async def tenants_usage(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = None,
    sort: str = "messages",
    order: str = "desc",
    period: str = "30d",
    admin: dict = Depends(get_current_admin),
):
    """Return per-tenant usage with pagination and sorting."""
    return await admin_analytics_service.get_tenants_usage(
        page=page, limit=limit, search=search, sort=sort, order=order, period=period,
    )


@router.get("/tenant/{tenant_id}")
async def tenant_analytics(
    tenant_id: str,
    period: str = "30d",
    admin: dict = Depends(get_current_admin),
):
    """Return detailed analytics for a single tenant."""
    result = await admin_analytics_service.get_tenant_analytics(tenant_id, period)
    if result is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return result


@router.get("/top-tenants")
async def top_tenants(
    sort: str = "messages",
    limit: int = Query(10, ge=1, le=50),
    admin: dict = Depends(get_current_admin),
):
    """Return top tenants sorted by the given metric."""
    return await admin_analytics_service.get_top_tenants(sort_by=sort, limit=limit)


@router.get("/models")
async def model_leaderboard(
    period: str = "30d",
    admin: dict = Depends(get_current_admin),
):
    """Return per-model usage leaderboard."""
    return await admin_analytics_service.get_model_leaderboard(period=period)


@router.get("/tenant/{tenant_id}/profile-stats")
async def tenant_profile_stats(
    tenant_id: str,
    admin: dict = Depends(get_current_admin),
):
    """Return visitor profile distribution for a tenant."""
    from core.auth import db
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "profile_id": {"$ne": None}}},
        {"$group": {"_id": "$profile_id", "label": {"$first": "$profile_label"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    results = await db.visitors.aggregate(pipeline).to_list(100)
    total = await db.visitors.count_documents({"tenant_id": tenant_id})
    items = [
        {"profile_id": r["_id"], "label": r.get("label"), "count": r["count"], "percentage": round(r["count"] / total * 100, 1) if total > 0 else 0}
        for r in results
    ]
    unclassified = total - sum(r["count"] for r in results)
    if unclassified > 0:
        items.append({"profile_id": None, "label": "Unclassified", "count": unclassified, "percentage": round(unclassified / total * 100, 1) if total > 0 else 0})
    return {"items": items, "total": total}
