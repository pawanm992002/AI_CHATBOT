from fastapi import APIRouter, Depends, HTTPException
from core.auth import db, get_current_tenant
from services.archival_service import archival_service

router = APIRouter(prefix="/dashboard", tags=["conversations"])


@router.get("/conversations/{conversation_id}/full")
async def get_full_conversation(
    conversation_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    result = await archival_service.get_full_conversation(conversation_id, tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    conv = await db.conversations.find_one(
        {"session_id": conversation_id, "tenant_id": tenant_id},
        {"_id": 0},
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Not Found")
    return conv