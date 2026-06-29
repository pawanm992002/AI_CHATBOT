from collections import defaultdict, deque
from datetime import datetime, timezone
import json
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from core.auth import db, limiter, verify_api_key
from core.config import settings
from models.requests import ChatRequest, FeedbackRequest
from services.chat_service import ChatService, ChatTurnInput
from views.responses import ChatResponse, ChatSource, WidgetConfigResponse
from repositories.lead_repository import LeadFormConfigRepository


router = APIRouter(tags=["chat"])
chat_service = ChatService()
_form_config_repo = LeadFormConfigRepository()

MAX_QUERY_LENGTH = 500
PER_TENANT_RATE_LIMIT = 100
PER_SESSION_RATE_LIMIT = 20
RATE_WINDOW_SECONDS = 60

_tenant_limits: dict[str, deque] = defaultdict(deque)
_session_limits: dict[str, deque] = defaultdict(deque)


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


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("60/minute")
async def chat(
    request: Request,
    req: ChatRequest,
    fastapi_response: Response,
    current_tenant: dict = Depends(verify_api_key),
):
    tenant_id = current_tenant["tenant_id"]
    session_id = request.cookies.get("chat_session_id") or req.session_id or str(uuid.uuid4())

    if len(req.query) > MAX_QUERY_LENGTH:
        raise HTTPException(status_code=400, detail="Query too long.")
    if not _check_rate_limit(tenant_id, _tenant_limits, PER_TENANT_RATE_LIMIT):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    if not _check_rate_limit(session_id, _session_limits, PER_SESSION_RATE_LIMIT):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")

    fastapi_response.set_cookie(
        key="chat_session_id",
        value=session_id,
        max_age=31536000,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    await _upsert_visitor(
        session_id=session_id,
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
            query=req.query,
            current_url=req.current_url,
            current_page_title=req.current_page_title,
            message_id=message_id,
        )
    )

    return ChatResponse(
        message_id=result.message_id,
        answer=result.answer,
        sources=result.sources,
        show_enquiry_form=result.show_enquiry_form,
    )


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest, current_tenant: dict = Depends(verify_api_key)):
    await db.message_feedback.update_one(
        {
            "tenant_id": current_tenant["tenant_id"],
            "session_id": req.session_id,
            "message_id": req.message_id,
        },
        {"$set": {
            "tenant_id": current_tenant["tenant_id"],
            "session_id": req.session_id,
            "message_id": req.message_id,
            "rating": req.rating,
            "created_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return {"status": "ok"}


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, key_hash: str = Query(...)):
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

            if not query:
                await websocket.send_json({"type": "error", "detail": "Empty query"})
                continue
            if len(query) > MAX_QUERY_LENGTH:
                await websocket.send_json({"type": "error", "detail": "Query too long"})
                continue

            tenant_id = tenant["tenant_id"]
            if not _check_rate_limit(tenant_id, _tenant_limits, PER_TENANT_RATE_LIMIT):
                await websocket.send_json({"type": "error", "detail": "Too many requests. Please slow down."})
                continue
            if not _check_rate_limit(session_id, _session_limits, PER_SESSION_RATE_LIMIT):
                await websocket.send_json({"type": "error", "detail": "Too many requests. Please slow down."})
                continue

            await _upsert_visitor(
                session_id=session_id,
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

            if result.show_enquiry_form:
                await websocket.send_json({"type": "enquiry_form"})
            await websocket.send_json({"type": "done", "message_id": result.message_id})

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass


def _check_rate_limit(key: str, limits: dict, max_reqs: int) -> bool:
    now = time.time()
    window_start = now - RATE_WINDOW_SECONDS
    dq = limits[key]
    while dq and dq[0] < window_start:
        dq.popleft()
    if len(dq) >= max_reqs:
        return False
    dq.append(now)
    return True


def _client_ip(request: Request) -> str:
    if request.client:
        return request.client.host
    return request.headers.get("x-forwarded-for", "0.0.0.0").split(",")[0].strip()


async def _upsert_visitor(
    session_id: str,
    tenant_id: str,
    current_url: str,
    current_page_title: str,
    client_ip: str,
) -> None:
    try:
        now = datetime.now(timezone.utc)
        visitor = await db.visitors.find_one(
            {"session_id": session_id},
            {"ip_history": {"$slice": -1}, "page_views": {"$slice": -1}},
        )

        needs_ip = bool(client_ip) and (
            not visitor or not visitor.get("ip_history") or visitor["ip_history"][-1]["ip"] != client_ip
        )
        needs_page = (
            not visitor
            or not visitor.get("page_views")
            or visitor["page_views"][-1]["url"] != current_url
            or visitor["page_views"][-1]["title"] != current_page_title
        )

        update = {"$set": {"last_seen_at": now, "tenant_id": tenant_id}}
        if not visitor:
            update["$setOnInsert"] = {
                "session_id": session_id,
                "first_seen_at": now,
                "conversation_ids": [],
                "total_messages": 0,
            }
        if needs_ip:
            update.setdefault("$push", {})["ip_history"] = {
                "$each": [{"ip": client_ip, "seen_at": now}],
                "$slice": -20,
            }
        if needs_page:
            update.setdefault("$push", {})["page_views"] = {
                "$each": [{"url": current_url, "title": current_page_title, "timestamp": now}],
                "$slice": -50,
            }

        await db.visitors.update_one({"session_id": session_id}, update, upsert=True)
    except Exception:
        pass
