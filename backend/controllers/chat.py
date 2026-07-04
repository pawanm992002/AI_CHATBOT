from datetime import datetime, timezone
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from core.auth import db, verify_api_key
from core.config import settings
from models.requests import ChatRequest, FeedbackRequest
from services.chat_service import ChatService, ChatTurnInput
from views.responses import ChatResponse, ChatSource, WidgetConfigResponse
from repositories.lead_repository import LeadFormConfigRepository


router = APIRouter(tags=["chat"])
chat_service = ChatService()
_form_config_repo = LeadFormConfigRepository()


class VisitorProfileResponse(BaseModel):
    profile_label: Optional[str] = None
    profile_color: Optional[str] = None


def _client_ip(request: Request) -> str:
    if request.client:
        return request.client.host
    return request.headers.get("x-forwarded-for", "0.0.0.0").split(",")[0].strip()

MAX_QUERY_LENGTH = 500
PER_TENANT_RATE_LIMIT = 100
PER_SESSION_RATE_LIMIT = 20
RATE_WINDOW_SECONDS = 60


@router.get("/widget/config", response_model=WidgetConfigResponse)
async def get_widget_config(current_tenant: dict = Depends(verify_api_key)):
    manual = current_tenant.get("suggested_questions_manual", [])
    auto = current_tenant.get("suggested_questions_auto", [])
    suggested = manual if manual else auto

    # Get active lead form config
    lead_form_config = await _form_config_repo.get_enabled_for_tenant(current_tenant["tenant_id"])
    lead_form = None
    if lead_form_config:
        lead_form = {
            "form_id": lead_form_config["form_id"],
            "title": lead_form_config["title"],
            "fields": lead_form_config.get("fields", []),
            "trigger_instructions": lead_form_config.get("trigger_instructions", ""),
            "enabled": lead_form_config.get("enabled", True),
        }

    return {
        "theme": current_tenant.get("theme", "default"),
        "suggested_questions": suggested,
        "show_sources": current_tenant.get("show_sources", True),
        "lead_form": lead_form,
    }


@router.get("/widget/visitor-profile", response_model=VisitorProfileResponse)
async def get_visitor_profile(
    visitor_id: str = Query(...),
    current_tenant: dict = Depends(verify_api_key),
):
    tenant_id = current_tenant["tenant_id"]
    visitor = await db.visitors.find_one(
        {"visitor_id": visitor_id, "tenant_id": tenant_id},
        {"profile_id": 1, "profile_label": 1},
    )
    if not visitor or not visitor.get("profile_id"):
        return VisitorProfileResponse()

    profile = await db.visitor_profiles.find_one(
        {"profile_id": visitor["profile_id"], "tenant_id": tenant_id},
        {"name": 1, "color": 1},
    )
    if not profile:
        return VisitorProfileResponse()

    return VisitorProfileResponse(
        profile_label=profile.get("name"),
        profile_color=profile.get("color", "#6366f1"),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    req: ChatRequest,
    fastapi_response: Response,
    current_tenant: dict = Depends(verify_api_key),
):
    tenant_id = current_tenant["tenant_id"]
    session_id = request.cookies.get("chat_session_id") or req.session_id or str(uuid.uuid4())
    visitor_id = req.visitor_id or session_id

    if len(req.query) > MAX_QUERY_LENGTH:
        raise HTTPException(status_code=400, detail="Query too long.")
    
    from core.rate_limiter import check_rate_limit
    if await check_rate_limit(f"rate_limit:chat:tenant:{tenant_id}", limit=PER_TENANT_RATE_LIMIT, window=RATE_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    if await check_rate_limit(f"rate_limit:chat:session:{session_id}", limit=PER_SESSION_RATE_LIMIT, window=RATE_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")

    fastapi_response.set_cookie(
        key="chat_session_id",
        value=session_id,
        max_age=31536000,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
    )

    await _upsert_visitor(
        session_id=session_id,
        visitor_id=visitor_id,
        tenant_id=tenant_id,
        current_url=req.current_url,
        current_page_title=req.current_page_title,
        client_ip=_client_ip(request),
    )

    message_id = str(uuid.uuid4())
    result = await chat_service.handle_message(
        ChatTurnInput(
            tenant=current_tenant,
            session_id=session_id,
            visitor_id=visitor_id,
            query=req.query,
            current_url=req.current_url,
            current_page_title=req.current_page_title,
            message_id=message_id,
        )
    )

    if result.show_enquiry_form and result.enquiry_form_id:
        valid_form = await _form_config_repo.get_by_form_id(
            current_tenant["tenant_id"], result.enquiry_form_id
        )
        if not valid_form or not valid_form.get("enabled", True):
            result.show_enquiry_form = False
            result.enquiry_form_id = ""
            result.answer = " "

    return ChatResponse(
        message_id=result.message_id,
        answer=result.answer,
        sources=result.sources,
        show_enquiry_form=result.show_enquiry_form,
        enquiry_form_id=result.enquiry_form_id,
    )


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest, current_tenant: dict = Depends(verify_api_key)):
    visitor_id = req.visitor_id or req.session_id
    await db.message_feedback.update_one(
        {
            "tenant_id": current_tenant["tenant_id"],
            "session_id": req.session_id,
            "message_id": req.message_id,
        },
        {"$set": {
            "tenant_id": current_tenant["tenant_id"],
            "session_id": req.session_id,
            "visitor_id": visitor_id,
            "message_id": req.message_id,
            "rating": req.rating,
            "created_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return {"status": "ok"}


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, key_hash: str = Query(...)):
    # Limit WS connection attempts: 30 connection attempts per minute per IP
    from core.rate_limiter import check_rate_limit
    ip = websocket.client.host if websocket.client else "0.0.0.0"
    if await check_rate_limit(f"rate_limit:ws_conn:{ip}", limit=30, window=60):
        await websocket.accept()
        await websocket.close(code=4003, reason="Too many connection attempts")
        return

    await websocket.accept()

    tenant = await db.tenants.find_one({"api_key_hash": key_hash})
    if not tenant:
        await websocket.close(code=4001, reason="Invalid API key")
        return

    status_val = tenant.get("status", "approved")
    if status_val == "disabled":
        await websocket.close(code=4003, reason="Tenant is disabled")
        return
    elif status_val != "approved":
        await websocket.close(code=4003, reason="Tenant is not active")
        return

    await websocket.send_json({"type": "authenticated"})

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            if data.get("type") != "message":
                await websocket.send_json({"type": "error", "detail": "Unknown message type"})
                continue

            query = data.get("query", "").strip()
            current_url = data.get("current_url", "")
            current_page_title = data.get("current_page_title", "")
            session_id = data.get("session_id") or str(uuid.uuid4())
            visitor_id = data.get("visitor_id") or session_id

            if not query:
                await websocket.send_json({"type": "error", "detail": "Empty query"})
                continue
            if len(query) > MAX_QUERY_LENGTH:
                await websocket.send_json({"type": "error", "detail": "Query too long"})
                continue

            tenant_id = tenant["tenant_id"]
            if await check_rate_limit(f"rate_limit:chat:tenant:{tenant_id}", limit=PER_TENANT_RATE_LIMIT, window=RATE_WINDOW_SECONDS):
                await websocket.send_json({"type": "error", "detail": "Too many requests. Please slow down."})
                continue
            if await check_rate_limit(f"rate_limit:chat:session:{session_id}", limit=PER_SESSION_RATE_LIMIT, window=RATE_WINDOW_SECONDS):
                await websocket.send_json({"type": "error", "detail": "Too many requests. Please slow down."})
                continue

            await _upsert_visitor(
                session_id=session_id,
                visitor_id=visitor_id,
                tenant_id=tenant_id,
                current_url=current_url,
                current_page_title=current_page_title,
                client_ip="",
            )

            message_id = str(uuid.uuid4())

            async def send_token(token: str):
                await websocket.send_json({"type": "token", "content": token})

            try:
                result = await chat_service.handle_message_stream(
                    ChatTurnInput(
                        tenant=tenant,
                        session_id=session_id,
                        visitor_id=visitor_id,
                        query=query,
                        current_url=current_url,
                        current_page_title=current_page_title,
                        message_id=message_id,
                    ),
                    on_token=send_token,
                )
            except Exception as e:
                print(f"[WS] Chat service error: {e}")
                await websocket.send_json({"type": "error", "detail": "Failed to generate response"})
                continue

            if result.sources:
                await websocket.send_json({
                    "type": "sources",
                    "data": [source.model_dump() for source in result.sources],
                })

            if result.show_enquiry_form and result.enquiry_form_id:
                valid_form = await _form_config_repo.get_by_form_id(
                    tenant["tenant_id"], result.enquiry_form_id
                )
                if valid_form and valid_form.get("enabled", True):
                    await websocket.send_json({"type": "enquiry_form", "form_id": result.enquiry_form_id})
                else:
                    result.show_enquiry_form = False
                    result.enquiry_form_id = ""
                    result.answer = " "
            await websocket.send_json({"type": "done", "message_id": result.message_id, "answer": result.answer})

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass


async def _archive_old_sessions_bg(old_session_ids: list[str], tenant_id: str) -> None:
    try:
        from services.archival_service import archival_service
        for s_id in old_session_ids:
            await archival_service.archive_entire_session(s_id, tenant_id)
    except Exception as e:
        print(f"[ARCHIVAL] Background archival of old sessions failed: {e}")


async def _upsert_visitor(
    session_id: str,
    tenant_id: str,
    current_url: str,
    current_page_title: str,
    client_ip: str,
    visitor_id: str = "",
) -> None:
    try:
        now = datetime.now(timezone.utc)
        key = visitor_id or session_id
        visitor = await db.visitors.find_one(
            {"visitor_id": key, "tenant_id": tenant_id},
            {"ip_history": {"$slice": -1}, "page_views": {"$slice": -1}},
        )

        if visitor and visitor.get("conversation_ids"):
            if session_id not in visitor["conversation_ids"]:
                old_ids = [c for c in visitor["conversation_ids"] if c != session_id]
                if old_ids:
                    import asyncio
                    asyncio.create_task(_archive_old_sessions_bg(old_ids, tenant_id))

        needs_ip = bool(client_ip) and (
            not visitor or not visitor.get("ip_history") or visitor["ip_history"][-1]["ip"] != client_ip
        )
        needs_page = (
            not visitor
            or not visitor.get("page_views")
            or visitor["page_views"][-1]["url"] != current_url
            or visitor["page_views"][-1]["title"] != current_page_title
        )

        update: dict[str, object] = {"$set": {"last_seen_at": now, "tenant_id": tenant_id}}
        push: dict[str, object] = {}
        if not visitor:
            update["$setOnInsert"] = {
                "visitor_id": key,
                "session_id": session_id,
                "first_seen_at": now,
                "total_messages": 0,
            }
        update["$addToSet"] = {"conversation_ids": session_id}

        if needs_ip:
            push["ip_history"] = {
                "$each": [{"ip": client_ip, "seen_at": now}],
                "$slice": -20,
            }
        if needs_page:
            push["page_views"] = {
                "$each": [{"url": current_url, "title": current_page_title, "timestamp": now}],
                "$slice": -50,
            }
        if push:
            update["$push"] = push

        await db.visitors.update_one({"visitor_id": key, "tenant_id": tenant_id}, update, upsert=True)
    except Exception as e:
        print(f"[UPSERT] visitor error for visitor={key} session={session_id}: {e}")
