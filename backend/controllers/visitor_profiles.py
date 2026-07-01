import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth import db, get_current_tenant
from models.visitor_profile import (
    VisitorProfileCreate,
    VisitorProfileUpdate,
    VisitorProfileResponse,
)
from repositories.visitor_profile_repository import VisitorProfileRepository
from services.visitor_profile_service import VisitorProfileService

router = APIRouter(prefix="/dashboard", tags=["visitor-profiles"])
_repo = VisitorProfileRepository()
_service = VisitorProfileService()


def _profile_to_response(p: dict) -> VisitorProfileResponse:
    return VisitorProfileResponse(
        profile_id=p["profile_id"],
        tenant_id=p["tenant_id"],
        name=p["name"],
        description=p.get("description", ""),
        color=p.get("color", "#6366f1"),
        rules=p.get("rules", []),
        llm_criteria=p.get("llm_criteria"),
        enabled=p.get("enabled", True),
        created_at=p["created_at"],
        updated_at=p["updated_at"],
    )


@router.get("/visitor-profiles/stats")
async def profile_stats(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]
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


@router.get("/visitor-profiles", response_model=list[VisitorProfileResponse])
async def list_profiles(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]
    profiles = await _repo.get_by_tenant(tenant_id)
    return [_profile_to_response(p) for p in profiles]


@router.post("/visitor-profiles", response_model=VisitorProfileResponse, status_code=201)
async def create_profile(
    req: VisitorProfileCreate,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    data = req.model_dump(exclude_unset=True)
    profile = await _repo.create(tenant_id, data)
    return _profile_to_response(profile)


@router.put("/visitor-profiles/{profile_id}", response_model=VisitorProfileResponse)
async def update_profile(
    profile_id: str,
    req: VisitorProfileUpdate,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    existing = await _repo.get_by_profile_id(tenant_id, profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Profile not found")

    data = req.model_dump(exclude_unset=True, exclude_none=True)
    ok = await _repo.update(tenant_id, profile_id, data)
    if not ok:
        raise HTTPException(status_code=404, detail="Profile not found")

    updated = await _repo.get_by_profile_id(tenant_id, profile_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profile_to_response(updated)


@router.delete("/visitor-profiles/{profile_id}")
async def delete_profile(
    profile_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    ok = await _repo.delete(tenant_id, profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Profile not found")

    await db.visitors.update_many(
        {"tenant_id": tenant_id, "profile_id": profile_id},
        {"$set": {"profile_id": None, "profile_label": None, "profile_confidence": None}},
    )
    return {"status": "ok"}


@router.get("/visitors")
async def list_visitors(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    profile_id: Optional[str] = None,
    search: Optional[str] = None,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    skip = (page - 1) * page_size

    query: dict = {"tenant_id": tenant_id}
    if profile_id:
        query["profile_id"] = profile_id
    if search:
        query["$or"] = [
            {"session_id": {"$regex": search, "$options": "i"}},
            {"identity.name": {"$regex": search, "$options": "i"}},
            {"identity.email": {"$regex": search, "$options": "i"}},
        ]

    total = await db.visitors.count_documents(query)
    cursor = db.visitors.find(query, {"_id": 0}).sort("last_seen_at", -1).skip(skip).limit(page_size)
    items = await cursor.to_list(length=page_size)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@router.get("/visitors/{visitor_id}")
async def get_visitor(
    visitor_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    visitor = await db.visitors.find_one(
        {"visitor_id": visitor_id, "tenant_id": tenant_id},
        {"_id": 0},
    )
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    leads_cursor = db.leads.find(
        {"visitor_id": visitor_id, "tenant_id": tenant_id},
        {"_id": 0},
    ).sort("created_at", -1)
    leads = await leads_cursor.to_list(length=100)

    return {**visitor, "leads": leads}


@router.post("/visitors/{visitor_id}/reclassify")
async def reclassify_visitor(
    visitor_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    await _service.classify_visitor(visitor_id, tenant_id, trigger="manual")
    return {"status": "ok", "message": "Reclassification triggered"}


@router.put("/visitors/{visitor_id}/profile")
async def set_visitor_profile(
    visitor_id: str,
    payload: dict,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    profile_id = payload.get("profile_id")
    profile_label = None
    if profile_id:
        profile = await _repo.get_by_profile_id(tenant_id, profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        profile_label = profile["name"]

    now = datetime.now(timezone.utc)
    update: dict = {
        "profile_id": profile_id,
        "profile_label": profile_label,
        "profile_confidence": 1.0 if profile_id else None,
        "last_classified_at": now,
    }

    if profile_id:
        await db.visitors.update_one(
            {"visitor_id": visitor_id, "tenant_id": tenant_id},
            {
                "$set": update,
                "$push": {
                    "profile_history": {
                        "profile_id": profile_id,
                        "profile_label": profile_label,
                        "assigned_at": now,
                        "reason": payload.get("reason", "Manual override"),
                        "source": "rule",
                        "trigger": "manual",
                    }
                },
            },
        )
    else:
        await db.visitors.update_one(
            {"visitor_id": visitor_id, "tenant_id": tenant_id},
            {"$set": update},
        )

    return {"status": "ok"}


@router.put("/visitors/{visitor_id}/identity")
async def update_visitor_identity(
    visitor_id: str,
    payload: dict,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    identity = {
        "name": payload.get("name"),
        "email": payload.get("email"),
        "phone": payload.get("phone"),
        "updated_at": datetime.now(timezone.utc),
    }

    await db.visitors.update_one(
        {"visitor_id": visitor_id, "tenant_id": tenant_id},
        {"$set": {"identity": identity}},
    )
    return {"status": "ok"}


@router.delete("/visitors/{visitor_id}/identity")
async def clear_visitor_identity(
    visitor_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    await db.visitors.update_one(
        {"visitor_id": visitor_id, "tenant_id": tenant_id},
        {"$set": {"identity": {"name": None, "email": None, "phone": None, "updated_at": None, "source_lead_id": None}}},
    )
    return {"status": "ok"}