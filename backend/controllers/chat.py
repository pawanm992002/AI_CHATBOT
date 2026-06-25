from fastapi import APIRouter, Depends, Request, Response, HTTPException, WebSocket, WebSocketDisconnect, Query
from models.requests import ChatRequest, FeedbackRequest
from views.responses import ChatResponse, ChatSource, WidgetConfigResponse
from core.auth import verify_api_key, db, limiter
from core.config import settings
from services.vector_search import search_chunks
from services.embedder import openai_client
from repositories.visitor_repository import VisitorRepository
from repositories.feedback_repository import FeedbackRepository
import uuid
import time
import numpy as np
from collections import defaultdict, deque
from datetime import datetime, timezone
import json
from core.redis import redis_client

router = APIRouter(tags=["chat"])

@router.get("/widget/config", response_model=WidgetConfigResponse)
async def get_widget_config(current_tenant: dict = Depends(verify_api_key)):
    manual = current_tenant.get("suggested_questions_manual", [])
    auto = current_tenant.get("suggested_questions_auto", [])
    suggested = manual if manual else auto
    return {
        "theme": current_tenant.get("theme", "default"),
        "suggested_questions": suggested,
        "show_sources": current_tenant.get("show_sources", True),
    }

# Max messages to send to GPT-4o (2 per turn)
MAX_HISTORY = 50
MAX_QUERY_LENGTH = 500
PER_TENANT_RATE_LIMIT = 100
PER_SESSION_RATE_LIMIT = 20
RATE_WINDOW_SECONDS = 60
DIRECT_ANSWER_THRESHOLD = 0.5

# In-memory sliding window rate limiters (reset on server restart)
_tenant_limits: dict[str, deque] = defaultdict(deque)
_session_limits: dict[str, deque] = defaultdict(deque)


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


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("60/minute")
async def chat(request: Request, req: ChatRequest, fastapi_response: Response, current_tenant: dict = Depends(verify_api_key)):
    tenant_id = current_tenant["tenant_id"]
    business_name = current_tenant.get("business_name") or current_tenant["domain"]
    message_id = str(uuid.uuid4())

    # --- Max query length ---
    if len(req.query) > MAX_QUERY_LENGTH:
        raise HTTPException(status_code=400, detail="Query too long.")

    # --- Per-tenant rate limit (catches distributed attacks on a single key) ---
    if not _check_rate_limit(tenant_id, _tenant_limits, PER_TENANT_RATE_LIMIT):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")

    # --- Cookie-based session resolution ---
    now = datetime.now(timezone.utc)
    session_id = request.cookies.get("chat_session_id") or req.session_id
    if not session_id:
        session_id = str(uuid.uuid4())

    # --- Per-session rate limit (catches a single abusive user) ---
    if not _check_rate_limit(session_id, _session_limits, PER_SESSION_RATE_LIMIT):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")

    fastapi_response.set_cookie(
        key="chat_session_id",
        value=session_id,
        max_age=31536000,  # 1 year
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    # --- Upsert visitor document ---
    try:
        client_ip = request.client.host if request.client else request.headers.get("x-forwarded-for", "0.0.0.0").split(",")[0].strip()
        visitor = await db.visitors.find_one({"session_id": session_id}, {"ip_history": {"$slice": -1}, "page_views": {"$slice": -1}})

        needs_ip = not visitor or not visitor.get("ip_history") or visitor["ip_history"][-1]["ip"] != client_ip
        needs_page = not visitor or not visitor.get("page_views") or visitor["page_views"][-1]["url"] != req.current_url or visitor["page_views"][-1]["title"] != req.current_page_title

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
                "$each": [{"url": req.current_url, "title": req.current_page_title, "timestamp": now}],
                "$slice": -50,
            }

        if update:
            await db.visitors.update_one({"session_id": session_id}, update, upsert=True)
    except Exception:
        pass  # Visitor tracking must never break the chat
    # --- end session resolution ---

    # Step 1: Fast greeting check (regex, no LLM)
    if _is_greeting(req.query):
        print(f"[CHAT] Greeting detected: '{req.query}'")
        answer = f"Hello! Welcome to {business_name}. How can I help you today?"
        await db.visitors.update_one(
            {"session_id": session_id},
            {"$addToSet": {"conversation_ids": session_id},
             "$inc": {"total_messages": 1}}
        )
        return ChatResponse(message_id=message_id, answer=answer, sources=[])

    # Step 2: LLM rewrite query + Vector search
    search_query, needs_search, _ = await _rewrite_search_query(req.query)
    print(f"[CHAT] query='{req.query}' → search_query='{search_query}' needs_search={needs_search}")

    chunks = []
    top_score = 0.0

    if needs_search:
        chunks = await search_chunks(tenant_id, search_query)
        print(f"[CHAT] search_chunks returned {len(chunks)} chunks")
        if chunks:
            top_score = chunks[0].get("score", 0.0)
            print(f"[CHAT] top score: {top_score:.4f}")

    # If score is below threshold, treat as no match
    if chunks and top_score < DIRECT_ANSWER_THRESHOLD:
        print(f"[CHAT] Score {top_score:.4f} below threshold {DIRECT_ANSWER_THRESHOLD}, treating as no match")
        chunks = []

    # --- Retrieve conversation history (with Redis cache + Mongo fallback) ---
    cache_key = f"chat_session:{session_id}"
    cached_data = None
    try:
        cached_data_str = await redis_client.get(cache_key)
        if cached_data_str:
            cached_data = json.loads(cached_data_str)
    except Exception as e:
        print(f"Redis get failed: {e}")

    if cached_data:
        summary = cached_data.get("summary", "")
        messages = cached_data.get("messages", [])
    else:
        # Fallback to MongoDB
        session = await db.conversations.find_one({"session_id": session_id})
        if session:
            summary = session.get("summary", "")
            messages = session.get("messages", [])
        else:
            summary = ""
            messages = []
        
        # Populate Redis cache
        try:
            await redis_client.setex(cache_key, 3600, json.dumps({"summary": summary, "messages": messages}))
        except Exception as e:
            print(f"Redis set failed: {e}")

    # Step 3: No knowledge match found — evaluate reason
    if not chunks:
        gap_type = await _evaluate_no_match(req.query, current_tenant.get("description"))
        print(f"[CHAT] No match. Gap type: {gap_type}")

        messages.append({"role": "user", "content": req.query})

        description = current_tenant.get("description") or ""
        if gap_type == "out_of_scope":
            no_match_prompt = f"""You are a representative of {business_name} — always speak as "we" and "our", never as "{business_name}" or a third party. The user's question is unrelated to our business. Politely let them know you can only help with questions about {business_name}. CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish. If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish, reply in Hinglish. NEVER use any other language."""
        elif description:
            no_match_prompt = f"""You are a representative of {business_name} — always speak as "we" and "our", never as "{business_name}" or a third party.

About this website: {description}
If the user asks about this website, what it does, or what it offers, use the description above to provide a helpful overview. Do not make up information beyond what is provided. CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish (a mix of Hindi and English). If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish (Hindi written in English script), reply in Hinglish. NEVER use any other language. However, if the user is asking about pricing, demo, purchasing, or wants to be contacted, offer to help and at the end of your response append [ENQUIRY_FORM]. Otherwise, politely say you don't have that information."""
        else:
            no_match_prompt = f"""You are a representative of {business_name} — always speak as "we" and "our", never as "{business_name}" or a third party.
You do not have information about this question. Politely say you don't have that information and suggest the user contact us for more details. CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish. If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish, reply in Hinglish. NEVER use any other language. However, if the user is asking about pricing, demo, purchasing, or wants to be contacted, offer to help and at the end of your response append [ENQUIRY_FORM]."""

        if summary:
            no_match_prompt += f"\n\nHere is a summary of the conversation so far:\n{summary}"
        
        api_messages = [{"role": "system", "content": no_match_prompt}] + messages[-MAX_HISTORY:]
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=api_messages
        )
        answer = response.choices[0].message.content
        show_form = "[ENQUIRY_FORM]" in answer
        if show_form:
            answer = answer.replace("[ENQUIRY_FORM]", "").strip()
        messages.append({"role": "assistant", "content": answer})
        
        # --- Context Summarization Compaction ---
        if len(messages) >= 32:
            messages_to_keep = messages[-30:]
            messages_to_summarize = messages[:-30]
            summary = await _summarize_past_context(summary, messages_to_summarize)
            messages = messages_to_keep

        # Update MongoDB
        await db.conversations.update_one(
            {"session_id": session_id},
            {"$set": {
                "tenant_id": tenant_id,
                "current_url": req.current_url,
                "summary": summary,
                "messages": messages
            }},
            upsert=True
        )

        # Update Redis cache
        try:
            await redis_client.setex(cache_key, 3600, json.dumps({"summary": summary, "messages": messages}))
        except Exception as e:
            print(f"Redis set failed: {e}")

        await db.visitors.update_one(
            {"session_id": session_id},
            {"$addToSet": {"conversation_ids": session_id},
             "$inc": {"total_messages": 1}}
        )
        if not show_form:
            await _log_knowledge_gap(tenant_id, req.query, req.current_url, gap_type, message_id)
        return ChatResponse(message_id=message_id, answer=answer, sources=[], show_enquiry_form=show_form)

    context_text = "\n\n".join([
        _format_context_chunk(c)
        for c in chunks
    ])

    # Sources list
    sources = []
    seen_sources = set()
    for c in chunks:
        section_title = c.get("section_title")
        section_path = c.get("section_path")
        source_key = (c["url"], section_path or section_title or "")
        if source_key not in seen_sources:
            sources.append(ChatSource(
                url=c["url"],
                title=c.get("title") or "Relevant Page",
                section_title=section_title,
                section_path=section_path,
            ))
            seen_sources.add(source_key)

    if not needs_search:
        system_prompt = f"You are a representative of {business_name}. Respond conversationally to the user using 'we' and 'our', never referring to yourself as a third party. Do not answer questions unrelated to {business_name}. CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish (a mix of Hindi and English). If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish (Hindi written in English script), reply in Hinglish. NEVER use any other language. If the user asks about pricing, demo, purchasing, or wants to be contacted, offer to help and at the end of your response append [ENQUIRY_FORM]."
    else:
        system_prompt = f"""You are a representative of {business_name} — always speak as "we" and "our", never as "{business_name}" or a third party. Answer the user's question based on the provided context. Do not make up information that isn't in the context.
The user is currently on page: {req.current_url} titled {req.current_page_title}.
Context: {context_text}
CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish (a mix of Hindi and English). If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish (Hindi written in English script), reply in Hinglish. NEVER use any other language. Ignore the language of the context above — always respond in the user's language from the allowed set.
If the user asks about pricing, demo, purchasing, or wants to be contacted, offer to help and at the end of your response append [ENQUIRY_FORM].
IMPORTANT: If the context contains a specific URL for registration, signup, login, purchase, or any action the user is asking about, include that URL inline in your response (as a clickable link or clearly written out). Do not just mention the website name — provide the exact full URL from the context."""

    if summary:
        system_prompt += f"\n\nHere is a summary of the conversation so far:\n{summary}"

    messages.append({"role": "user", "content": req.query})

    # Send only the last MAX_HISTORY messages to control token usage.
    # Full history is still stored in MongoDB (see update below).
    api_messages = [{"role": "system", "content": system_prompt}] + messages[-MAX_HISTORY:]

    response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=api_messages
    )
    answer = response.choices[0].message.content

    # Detect and strip enquiry form marker
    show_form = "[ENQUIRY_FORM]" in answer
    if show_form:
        answer = answer.replace("[ENQUIRY_FORM]", "").strip()

    messages.append({"role": "assistant", "content": answer})

    # --- Context Summarization Compaction ---
    if len(messages) >= 32:
        messages_to_keep = messages[-30:]
        messages_to_summarize = messages[:-30]
        summary = await _summarize_past_context(summary, messages_to_summarize)
        messages = messages_to_keep

    # Update MongoDB (keeps messages capped at max 30 messages / 15 turns)
    await db.conversations.update_one(
        {"session_id": session_id},
        {"$set": {
            "tenant_id": tenant_id,
            "current_url": req.current_url,
            "summary": summary,
            "messages": messages
        }},
        upsert=True
    )

    # Update Redis cache
    try:
        await redis_client.setex(cache_key, 3600, json.dumps({"summary": summary, "messages": messages}))
    except Exception as e:
        print(f"Redis set failed: {e}")

    # Track conversation and message count on visitor
    await db.visitors.update_one(
        {"session_id": session_id},
        {"$addToSet": {"conversation_ids": session_id},
         "$inc": {"total_messages": 1}}
    )

    return ChatResponse(message_id=message_id, answer=answer, sources=sources, show_enquiry_form=show_form)


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

    # --- Authenticate via hashed API key ---
    tenant = await db.tenants.find_one({"api_key_hash": key_hash})
    if not tenant:
        await websocket.close(code=4001, reason="Invalid API key")
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
            business_name = tenant.get("business_name") or tenant["domain"]
            message_id = str(uuid.uuid4())

            # --- Rate limits ---
            if not _check_rate_limit(tenant_id, _tenant_limits, PER_TENANT_RATE_LIMIT):
                await websocket.send_json({"type": "error", "detail": "Too many requests. Please slow down."})
                continue

            if not _check_rate_limit(session_id, _session_limits, PER_SESSION_RATE_LIMIT):
                await websocket.send_json({"type": "error", "detail": "Too many requests. Please slow down."})
                continue

            # --- Visitor tracking ---
            now = datetime.now(timezone.utc)
            try:
                await db.visitors.update_one(
                    {"session_id": session_id},
                    {"$set": {"last_seen_at": now, "tenant_id": tenant_id},
                     "$setOnInsert": {"session_id": session_id, "first_seen_at": now, "conversation_ids": [], "total_messages": 0}},
                    upsert=True
                )
            except Exception:
                pass

            # --- Greeting fast-path ---
            if _is_greeting(query):
                answer = f"Hello! Welcome to {business_name}. How can I help you today?"
                await websocket.send_json({"type": "token", "content": answer})
                await websocket.send_json({"type": "done", "message_id": message_id})
                try:
                    await db.visitors.update_one(
                        {"session_id": session_id},
                        {"$addToSet": {"conversation_ids": session_id}, "$inc": {"total_messages": 1}}
                    )
                except Exception:
                    pass
                continue

            # --- Query rewrite + vector search ---
            search_query, needs_search, _ = await _rewrite_search_query(query)

            chunks = []
            top_score = 0.0
            if needs_search:
                chunks = await search_chunks(tenant_id, search_query)
                if chunks:
                    top_score = chunks[0].get("score", 0.0)

            if chunks and top_score < DIRECT_ANSWER_THRESHOLD:
                chunks = []

            # --- Conversation history ---
            cache_key = f"chat_session:{session_id}"
            summary = ""
            messages = []
            try:
                cached_data_str = await redis_client.get(cache_key)
                if cached_data_str:
                    cached_data = json.loads(cached_data_str)
                    summary = cached_data.get("summary", "")
                    messages = cached_data.get("messages", [])
            except Exception:
                pass

            if not messages and not summary:
                session = await db.conversations.find_one({"session_id": session_id})
                if session:
                    summary = session.get("summary", "")
                    messages = session.get("messages", [])

            # --- Build prompt ---
            if not chunks:
                gap_type = await _evaluate_no_match(query, tenant.get("description"))
                messages.append({"role": "user", "content": query})

                description = tenant.get("description") or ""
                if gap_type == "out_of_scope":
                    system_prompt = f"You are a representative of {business_name} — always speak as \"we\" and \"our\", never as \"{business_name}\" or a third party. The user's question is unrelated to our business. Politely let them know you can only help with questions about {business_name}. CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish. If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish, reply in Hinglish. NEVER use any other language."
                elif description:
                    system_prompt = f"""You are a representative of {business_name} — always speak as "we" and "our", never as "{business_name}" or a third party.

About this website: {description}
If the user asks about this website, what it does, or what it offers, use the description above to provide a helpful overview. Do not make up information beyond what is provided. CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish (a mix of Hindi and English). If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish (Hindi written in English script), reply in Hinglish. NEVER use any other language. However, if the user is asking about pricing, demo, purchasing, or wants to be contacted, offer to help and at the end of your response append [ENQUIRY_FORM]. Otherwise, politely say you don't have that information."""
                else:
                    system_prompt = f"""You are a representative of {business_name} — always speak as "we" and "our", never as "{business_name}" or a third party.
You do not have information about this question. Politely say you don't have that information and suggest the user contact us for more details. CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish. If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish, reply in Hinglish. NEVER use any other language. However, if the user is asking about pricing, demo, purchasing, or wants to be contacted, offer to help and at the end of your response append [ENQUIRY_FORM]."""

                if summary:
                    system_prompt += f"\n\nHere is a summary of the conversation so far:\n{summary}"

                sources_to_send = []
            else:
                context_text = "\n\n".join([_format_context_chunk(c) for c in chunks])

                sources_to_send = []
                seen_sources = set()
                for c in chunks:
                    section_title = c.get("section_title")
                    section_path = c.get("section_path")
                    source_key = (c["url"], section_path or section_title or "")
                    if source_key not in seen_sources:
                        sources_to_send.append({"url": c["url"], "title": c.get("title") or "Relevant Page", "section_title": section_title, "section_path": section_path})
                        seen_sources.add(source_key)

                if not needs_search:
                    system_prompt = f"You are a representative of {business_name}. Respond conversationally to the user using 'we' and 'our', never referring to yourself as a third party. Do not answer questions unrelated to {business_name}. CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish (a mix of Hindi and English). If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish (Hindi written in English script), reply in Hinglish. NEVER use any other language. If the user asks about pricing, demo, purchasing, or wants to be contacted, offer to help and at the end of your response append [ENQUIRY_FORM]."
                else:
                    system_prompt = f"""You are a representative of {business_name} — always speak as "we" and "our", never as "{business_name}" or a third party. Answer the user's question based on the provided context. Do not make up information that isn't in the context.
The user is currently on page: {current_url} titled {current_page_title}.
Context: {context_text}
CRITICAL: You MUST ONLY reply in English, Hindi, or Hinglish (a mix of Hindi and English). If the user writes in English, reply in English. If the user writes in Hindi (Devanagari script), reply in Hindi. If the user writes in Hinglish (Hindi written in English script), reply in Hinglish. NEVER use any other language. Ignore the language of the context above — always respond in the user's language from the allowed set.
If the user asks about pricing, demo, purchasing, or wants to be contacted, offer to help and at the end of your response append [ENQUIRY_FORM]."""

                if summary:
                    system_prompt += f"\n\nHere is a summary of the conversation so far:\n{summary}"

                gap_type = None
                messages.append({"role": "user", "content": query})

            # --- Send sources before streaming ---
            if sources_to_send:
                await websocket.send_json({"type": "sources", "data": sources_to_send})

            # --- Stream LLM response ---
            api_messages = [{"role": "system", "content": system_prompt}] + messages[-MAX_HISTORY:]
            full_answer = ""
            show_form = False

            try:
                stream = await openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=api_messages,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_answer += delta.content
                        await websocket.send_json({"type": "token", "content": delta.content})
            except Exception as e:
                print(f"[WS] Stream error: {e}")
                await websocket.send_json({"type": "error", "detail": "Failed to generate response"})
                continue

            # --- Post-processing ---
            show_form = "[ENQUIRY_FORM]" in full_answer
            if show_form:
                full_answer = full_answer.replace("[ENQUIRY_FORM]", "").strip()
                await websocket.send_json({"type": "enquiry_form"})

            messages.append({"role": "assistant", "content": full_answer})

            # --- Summarization compaction ---
            if len(messages) >= 32:
                messages_to_keep = messages[-30:]
                messages_to_summarize = messages[:-30]
                summary = await _summarize_past_context(summary, messages_to_summarize)
                messages = messages_to_keep

            # --- Persist conversation ---
            try:
                await db.conversations.update_one(
                    {"session_id": session_id},
                    {"$set": {"tenant_id": tenant_id, "current_url": current_url, "summary": summary, "messages": messages}},
                    upsert=True
                )
                await redis_client.setex(cache_key, 3600, json.dumps({"summary": summary, "messages": messages}))
            except Exception:
                pass

            # --- Visitor tracking ---
            try:
                await db.visitors.update_one(
                    {"session_id": session_id},
                    {"$addToSet": {"conversation_ids": session_id}, "$inc": {"total_messages": 1}}
                )
            except Exception:
                pass

            # --- Knowledge gap logging ---
            if not chunks and not show_form and gap_type:
                await _log_knowledge_gap(tenant_id, query, current_url, gap_type, message_id)

            await websocket.send_json({"type": "done", "message_id": message_id})

    except WebSocketDisconnect:
        print(f"[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass


def _format_context_chunk(chunk: dict) -> str:
    title = chunk.get("title") or "Relevant Page"
    section = chunk.get("section_path") or chunk.get("section_title")
    heading = f"Source ({chunk['url']})"
    if section:
        heading = f"{heading} - {title} - {section}"
    elif title:
        heading = f"{heading} - {title}"

    return f"{heading}:\n{chunk['text']}"


# Simple in-memory cache for query rewrites (cleared on server restart)
_query_rewrite_cache: dict[str, tuple[str, bool, bool]] = {}

_QUERY_REWRITE_SYSTEM_PROMPT = (
    "You are a query router for a company website chatbot. "
    "Your job is to classify the user's message into exactly one of three outputs:\n\n"

    "1. Reply GREETING\n"
    "   → When the user is doing general conversation, small talk, or chit-chat that any chatbot can handle naturally.\n"
    "   → Examples: 'hi', 'hello', 'how are you', 'thanks', 'okay', 'got it', 'bye', "
    "'aap kaisa hain', 'theek hai', 'shukriya', 'accha'\n"
    "   → No search needed — the chatbot can respond directly.\n\n"

    "2. Reply OUT_OF_SCOPE\n"
    "   → ONLY when the query is clearly about something that has NOTHING to do with the company or its business:\n"
    "     - Famous people (e.g. 'Virat Kohli kaun hai')\n"
    "     - Coding problems (e.g. 'LeetCode two sum solution')\n"
    "     - General knowledge / trivia (e.g. 'capital of France')\n"
    "     - Weather, news, jokes, entertainment\n"
    "     - Politics, sports scores, unrelated current events\n"
    "   → CRITICAL: If the query could POSSIBLY be about the company, its programs, eligibility, "
    "courses, exams, schedules, fees, scholarships, results, or any business-related topic, "
    "ALWAYS classify as a search query — NEVER as OUT_OF_SCOPE.\n"
    "   → When in doubt, classify as a search query.\n\n"

    "3. Otherwise → Rewrite as a search query\n"
    "   → If the query is about the company, its programs, eligibility, products, services, "
    "pricing, support, installation, or anything a business website chatbot should answer:\n"
    "   → Translate to English if needed, then rewrite as a concise English search query.\n"
    "   → Respond with ONLY the rewritten query — no explanation, no quotes, no preamble.\n\n"

    "IMPORTANT: Respond with exactly one of: 'GREETING', 'OUT_OF_SCOPE', or a rewritten English search query."
)

# --- Greeting detection (fast-path regex, no LLM) ---
import re
_GREETING_PATTERN = re.compile(
    r'^(hi|hello|hey|yo|howdy|hola|namaste|namaskar|good\s*(morning|afternoon|evening|night)|'
    r'what\'?s?\s*up|sup|how\s*are\s*you|hru|gm|gn|bye|thanks|thank\s*you|ok|okay|'
    r'chalo|acha|theek\s*hai|haan|ji|sir|madam|boss|dost)\s*[!.?]*$',
    re.IGNORECASE
)

def _is_greeting(query: str) -> bool:
    """Fast regex check for greetings — no LLM call needed."""
    return bool(_GREETING_PATTERN.match(query.strip()))


# --- Evaluate reason when no knowledge match found ---
async def _evaluate_no_match(query: str, description: str = None) -> str:
    """Classify why no match was found: 'out_of_scope' or 'knowledge_gap'.
    
    Default to knowledge_gap unless clearly unrelated to any business.
    """
    business_context = f"\nThis website is about: {description}" if description else ""
    
    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    f"The user asked a question to a business website chatbot but no answer was found.{business_context}\n\n"
                    "Is this CLEARLY unrelated to any business website? (sports, weather, politics, celebrities, "
                    "jokes, coding, math, personal opinions, unrelated trivia)\n"
                    "- YES → OUT_OF_SCOPE\n"
                    "- NO / Maybe → KNOWLEDGE_GAP\n\n"
                    "Default to KNOWLEDGE_GAP if unsure.\n"
                    "Respond with ONLY: OUT_OF_SCOPE or KNOWLEDGE_GAP"
                )},
                {"role": "user", "content": query},
            ],
            max_tokens=20,
            temperature=0.0,
        )
        result = resp.choices[0].message.content.strip().upper()
        if "OUT_OF_SCOPE" in result:
            return "out_of_scope"
        return "knowledge_gap"
    except Exception:
        return "knowledge_gap"


async def _rewrite_search_query(query: str) -> tuple[str, bool, bool]:
    """Returns (search_query, needs_search, is_out_of_scope).
    Greetings → needs_search=False, is_out_of_scope=False.
    Out-of-scope → needs_search=False, is_out_of_scope=True.
    Searchable → needs_search=True, is_out_of_scope=False.
    """
    q = query.strip()
    if len(q) < 4:
        return q, False, False

    # Check cache
    cached = _query_rewrite_cache.get(q)
    if cached is not None:
        return cached

    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _QUERY_REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": q},
            ],
            max_tokens=60,
            temperature=0.0,
        )
        response_text = resp.choices[0].message.content.strip()

        if response_text == "GREETING":
            result = (q, False, False)
        elif response_text == "OUT_OF_SCOPE":
            result = (q, False, True)
        else:
            rewritten = response_text
            # Sanity check: don't use if it's empty or absurdly long
            if not rewritten or len(rewritten) > 200:
                rewritten = q
            result = (rewritten, True, False)

        # Cache the result
        _query_rewrite_cache[q] = result
        return result
    except Exception:
        # If the LLM call fails, fall back to the original query and treat as searchable
        return q, True, False


async def _summarize_past_context(previous_summary: str, messages_to_summarize: list[dict]) -> str:
    """Summarize older chat history to save tokens and manage window context."""
    formatted_history = "\n".join([
        f"{'Visitor' if msg['role'] == 'user' else 'Bot'}: {msg['content']}"
        for msg in messages_to_summarize
    ])
    
    total_chars = sum(len(msg["content"]) for msg in messages_to_summarize) + len(previous_summary)
    word_limit = max(80, min(500, total_chars // 20))
    max_tokens = word_limit * 2

    prompt = (
        "You are an AI assistant helping a website chatbot maintain its context. "
        "Summarize the following chat history between a Visitor and a Bot. "
        "Focus on the visitor's core intent, questions asked, and key information provided. "
        "Do not lose track of important customer details (like names, choices, or issues). "
        f"Keep the summary concise (under {word_limit} words) and professional.\n\n"
    )
    if previous_summary:
        prompt += f"Previous Summary:\n{previous_summary}\n\n"
    
    prompt += f"New Conversation Segment:\n{formatted_history}\n\nNew Summary:"
    
    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes chat history segments."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.3
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"Failed to summarize chat history: {e}")
        return previous_summary


async def _log_knowledge_gap(tenant_id: str, query: str, url: str, gap_type: str, message_id: str):
    """Log a knowledge gap with embedding for similarity clustering."""
    try:
        # Normalize query for better matching (generic, no hardcoded words)
        import re
        normalized = query.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)  # remove punctuation
        normalized = re.sub(r'\s+', ' ', normalized)  # collapse whitespace

        # Generate embedding for the query
        embedding_resp = await openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=query,
        )
        embedding = embedding_resp.data[0].embedding
        new_embedding = np.array(embedding)

        # Find all open gaps with embeddings for similarity comparison
        open_gaps = await db.knowledge_gaps.find({
            "tenant_id": tenant_id,
            "status": "open",
            "embedding": {"$exists": True},
        }, {
            "query": 1,
            "embedding": 1,
            "count": 1,
        }).to_list(1000)

        # Find the most similar gap (highest cosine similarity)
        best_match = None
        best_similarity = 0.0
        SIMILARITY_THRESHOLD = 0.85

        for gap in open_gaps:
            if gap.get("embedding"):
                sim_embedding = np.array(gap["embedding"])
                cos_sim = np.dot(sim_embedding, new_embedding) / (np.linalg.norm(sim_embedding) * np.linalg.norm(new_embedding))

                # Exact match after normalization
                gap_normalized = re.sub(r'[^\w\s]', '', gap["query"].lower().strip())
                gap_normalized = re.sub(r'\s+', ' ', gap_normalized)
                if gap_normalized == normalized:
                    cos_sim = 1.0

                if cos_sim > best_similarity:
                    best_similarity = cos_sim
                    best_match = gap

        # Merge with most similar gap if above threshold
        if best_match and best_similarity > SIMILARITY_THRESHOLD:
            await db.knowledge_gaps.update_one(
                {"_id": best_match["_id"]},
                {"$inc": {"count": 1}, "$set": {"last_seen": datetime.now(timezone.utc)}}
            )
            print(f"[KNOWLEDGE] Merged query with existing gap (similarity: {best_similarity:.3f})")
            return

        # Create new gap
        await db.knowledge_gaps.insert_one({
            "tenant_id": tenant_id,
            "query": query,
            "url": url,
            "gap_type": gap_type,
            "message_id": message_id,
            "embedding": embedding,
            "count": 1,
            "status": "open",
            "resolved_by_faq_id": None,
            "cluster_id": None,
            "first_seen": datetime.now(timezone.utc),
            "last_seen": datetime.now(timezone.utc),
        })
        print(f"[KNOWLEDGE] Created new gap: {query[:50]}...")
    except Exception as e:
        print(f"[KNOWLEDGE] Error logging gap: {e}")
