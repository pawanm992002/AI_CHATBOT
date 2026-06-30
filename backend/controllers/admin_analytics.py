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
