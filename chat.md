# chat.md — Context Assembly Diagnostic Dump

> **Status:** Bug fixed (round 2 — simplification). This file documents the
> post-fix code state plus the root-cause analysis and exact changes made. All
> code blocks below reflect the current production code in
> `backend/services/chat_service.py`.

---

## Table of Contents

1. [Query Rewrite Step](#1-query-rewrite-step)
2. [Conversation History Assembly](#2-conversation-history-assembly)
3. [RAG Answer Generation Step](#3-rag-answer-generation-step)
4. [The "No Match" / Classification Path](#4-the-no-match--classification-path)
5. [Full Request Handler](#5-full-request-handler)
6. [Session / Turn Data Shape](#6-session--turn-data-shape)
7. [Bug Root Cause Analysis](#7-bug-root-cause-analysis)
8. [Changes Made (Round 1 — unify paths)](#8-changes-made-round-1--unify-paths)
9. [Changes Made (Round 2 — remove branching entirely)](#9-changes-made-round-2--remove-branching-entirely)
10. [Tests Added](#10-tests-added)

---

## 1. Query Rewrite Step

The rewrite function takes the visitor's current message, plus prior conversation
turns assembled via `_recent_conversation_text()`, and sends them to the LLM to
produce a standalone search query. The input includes prior conversation (up to
`MAX_REWRITE_HISTORY=12` recent messages plus the rolling `summary`), so context
is available here.

```python
# backend/services/chat_service.py:520-546

    async def _rewrite_search_query(self, query: str, summary: str, messages: list[dict], provider: str = "openai", model: str = "gpt-4o-mini", profiles: list[dict] | None = None) -> tuple[str, str | None]:
        conversation_text = self._recent_conversation_text(summary, messages)
        user_prompt = f"Latest user message: {query.strip()}"
        if conversation_text:
            user_prompt = (
                f"Conversation so far:\n{conversation_text}\n\n"
                f"Latest user message: {query.strip()}"
            )

        system_content = prompts.QUERY_REWRITE_PROMPT
        if profiles:
            system_content += build_profile_classification_prompt(profiles)

        try:
            llm = get_llm(provider, model)
            resp = await llm.ainvoke(
                [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_prompt},
                ]
            )
            response_text = (resp.content or "").strip()
            profile_name = parse_profile_from_rewrite_response(response_text, profiles or [])
            rewritten = response_text.split("\n")[0].strip() if "\n" in response_text else response_text
            return (rewritten if rewritten and len(rewritten) <= 240 else query.strip()), profile_name
        except Exception:
            return query.strip(), None
```

The rewrite prompt instructs the LLM to resolve follow-ups using conversation history:

```python
# backend/services/chat_prompts.py:13-18

QUERY_REWRITE_PROMPT = (
    "Rewrite the latest user message into a concise English search query for a company website knowledge base.\n"
    "Use the conversation history to resolve follow-ups, pronouns, locations, dates, fees, availability, and missing entities.\n"
    "Generic continuation requests like 'tell me more', 'more about the exam', 'fees?', 'eligibility?', 'date?', 'syllabus?', or 'in Jaipur?' must include the most recent specific named topic from the conversation.\n"
    "Return only the rewritten search query. No explanation."
)
```

The helper that formats prior conversation into text for the rewrite LLM call:

```python
# backend/services/chat_service.py:869-880

    def _recent_conversation_text(self, summary: str, messages: list[dict], max_messages: int = MAX_REWRITE_HISTORY) -> str:
        parts = []
        if summary:
            parts.append(f"Summary: {summary}")

        for msg in messages[-max_messages:]:
            role = "Visitor" if msg.get("role") == "user" else "Bot"
            content = (msg.get("content") or "").strip()
            if content:
                parts.append(f"{role}: {content}")

        return "\n".join(parts)
```

**Note:** `MAX_REWRITE_HISTORY = 12` (line 32). The classifier also builds a
similar user_prompt with conversation context (lines 502-505), but uses the same
`_recent_conversation_text()` helper.

---

## 2. Conversation History Assembly

History is loaded once at the start of each request from Redis (cache) or
MongoDB (persisted store). The same `(summary, messages)` tuple is used for
classification, rewrite, and the no-match prompt. However, the *answer-generation
step* receives `summary` and `messages` as separate arguments and injects
`summary` into the system prompt (not into the messages array).

```python
# backend/services/chat_service.py:715-735

    async def _load_conversation_context(self, session_id: str, tenant_id: str) -> tuple[str, list[dict]]:
        cache_key = get_redis_key(f"chat_session:{session_id}")
        try:
            cached_data_str = await redis_client.get(cache_key)
            if cached_data_str:
                cached_data = json.loads(cached_data_str)
                return cached_data.get("summary", ""), cached_data.get("messages", [])
        except Exception as e:
            print(f"Redis get failed: {e}")

        session = await db.conversations.find_one({"session_id": session_id, "tenant_id": tenant_id})
        if not session:
            return "", []

        summary = session.get("summary", "")
        messages = session.get("messages", [])
        try:
            await redis_client.setex(cache_key, 3600, json.dumps({"summary": summary, "messages": messages}))
        except Exception as e:
            print(f"Redis set failed: {e}")
        return summary, messages
```

History is persisted after each turn:

```python
# backend/services/chat_service.py:737-763

    async def _persist_conversation(self, turn: ChatTurnInput, summary: str, messages: list[dict]) -> None:
        cache_key = get_redis_key(f"chat_session:{turn.session_id}")
        now = datetime.now(timezone.utc)
        await db.conversations.update_one(
            {"session_id": turn.session_id, "tenant_id": turn.tenant["tenant_id"]},
            {"$set": {
                "tenant_id": turn.tenant["tenant_id"],
                "current_url": turn.current_url,
                "summary": summary,
                "messages": messages,
                "updated_at": now,
            }, "$setOnInsert": {
                "created_at": now,
                "archived": False,
                "archive_key": None,
                "archived_turn_count": 0,
            }},
            upsert=True,
        )
        try:
            await redis_client.setex(cache_key, 3600, json.dumps({"summary": summary, "messages": messages}))
        except Exception as e:
            print(f"Redis set failed: {e}")

        asyncio.ensure_future(
            archival_service.archive_overflow_turns(turn.session_id, turn.tenant["tenant_id"])
        )
```

Compaction/summarization when messages exceed 32:

```python
# backend/services/chat_service.py:771-778

    async def _compact_if_needed(self, summary: str, messages: list[dict], provider: str = "openai", model: str = "gpt-4o-mini") -> tuple[str, list[dict]]:
        if len(messages) <= 32:
            return summary, messages

        # Summarize the oldest messages beyond the most recent 32, then trim to 30
        messages_to_summarize = messages[:-32]
        summary = await self._summarize_past_context(summary, messages_to_summarize, provider, model)
        messages = messages[-30:]
        return summary, messages
```

**Key observation:** The rewrite step and the answer step both receive the same
`summary` and `messages` list. But `_complete_answer` slices
`messages[-MAX_HISTORY:]` (where `MAX_HISTORY=50`) for the LLM call, and injects
`summary` into the *system prompt* separately. So the answer LLM sees: system
prompt (with summary appended) + up to 50 recent messages.

---

## 3. RAG Answer Generation Step

When chunks are found, the system prompt is built with the retrieved context, and
`summary` is appended to the system prompt. History is passed as the `messages`
list (sliced to `MAX_HISTORY=50`).

```python
# backend/services/chat_service.py:442-491

    async def _handle_answer_with_chunks(
        self,
        turn: ChatTurnInput,
        summary: str,
        messages: list[dict],
        chunks: list[dict],
        needs_search: bool,
    ) -> ChatTurnResult:
        tenant_id = turn.tenant["tenant_id"]
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]
        sources = self._build_sources(chunks)

        if needs_search:
            context_text = "\n\n".join([self._format_context_chunk(c) for c in chunks])
            system_prompt = prompts.ANSWER_WITH_CONTEXT_PROMPT.format(
                business_name=business_name,
                current_url=turn.current_url,
                current_page_title=turn.current_page_title,
                context_text=context_text,
            )
        else:
            system_prompt = prompts.DIRECT_ANSWER_PROMPT.format(
                business_name=business_name,
            )

        identity_ctx = await self._get_visitor_identity_context(turn.session_id, tenant_id)
        if identity_ctx:
            system_prompt += identity_ctx

        profile_context = await get_visitor_profile_context(tenant_id, turn.session_id)
        if profile_context:
            system_prompt += profile_context

        if summary:
            system_prompt += f"\n\nHere is a summary of the conversation so far:\n{summary}"

        messages.append({"role": "user", "content": turn.query})
        tenant_ai_provider, tenant_ai_model = self._tenant_llm_provider_model(turn.tenant)

        forms = await _form_config_repo.get_all_enabled_for_tenant(turn.tenant["tenant_id"])
        tool_schema = self._build_form_tool(forms) if forms else None

        answer, show_form, form_id, usage = await self._complete_answer(system_prompt, messages, tenant_ai_provider, tenant_ai_model, tools=[tool_schema] if tool_schema else None, forms=forms)
        messages.append({"role": "assistant", "content": answer, "usage": usage})

        summary, messages = await self._compact_if_needed(summary, messages, tenant_ai_provider, tenant_ai_model)
        await self._persist_conversation(turn, summary, messages)
        await self._track_visitor_message(turn.session_id, turn.tenant["tenant_id"])

        return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=sources, show_enquiry_form=show_form, enquiry_form_id=form_id)
```

The `_complete_answer` method assembles the final API messages with history slice:

```python
# backend/services/chat_service.py:575-627

    async def _complete_answer(self, system_prompt: str, messages: list[dict], provider: str = "openai", model: str = "gpt-4o", tools: list[dict] | None = None, forms: list[dict] | None = None) -> tuple[str, bool, str, dict[str, Any]]:
        """Non-streaming LLM call with optional tool calling for form routing.

        Returns (answer, show_form, form_id, usage_dict).
        """
        if tools:
            system_prompt += (
                "\n\nWhen the user expresses intent to take a specific action "
                "(enroll, book, apply, request a call back, etc.), use the show_enquiry_form tool "
                "to show the most relevant form. Always include a brief text response alongside the tool call."
            )
        api_messages = [{"role": "system", "content": system_prompt}] + messages[-MAX_HISTORY:]
        raw_llm = get_llm_raw(provider, model)
        lc_messages = _to_lc_messages(api_messages)

        start = time.perf_counter()
        try:
            if tools:
                llm_with_tools = raw_llm.bind_tools(tools, tool_choice="auto")
                response = await llm_with_tools.ainvoke(lc_messages)
            else:
                response = await raw_llm.ainvoke(lc_messages)
            latency_ms = (time.perf_counter() - start) * 1000
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            usage = {
                "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                "reasoning_tokens": 0, "cached_tokens": 0,
                "provider": provider, "model": model,
                "latency_ms": round(latency_ms, 1),
                "status": "error", "error": str(e)[:200],
            }
            return "", False, "", usage

        usage = extract_usage(response, provider, model, latency_ms)

        content = response.content
        answer: str = content if isinstance(content, str) else ""
        show_form = False
        form_id = ""
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                if tc.get("name") == "show_enquiry_form":
                    args = tc.get("args") or {}
                    if args.get("form_id"):
                        show_form = True
                        form_id = args["form_id"]
                        break

        if show_form and not answer:
            answer = "Let me get that for you!"

        return answer, show_form, form_id, usage
```

The answer prompt template:

```python
# backend/services/chat_prompts.py:54-63

ANSWER_WITH_CONTEXT_PROMPT = (
    'You are a representative of {business_name} - always speak as "we" and "our", never as "{business_name}" or a third party. '
    "Answer the user's question based on the provided context. Do not make up information that isn't in the context.\n"
    "The user is currently on page: {current_url} titled {current_page_title}.\n"
    "Context: {context_text}\n"
    "CRITICAL: You MUST ONLY reply in English or Hinglish. If the user writes in English, reply in English. "
    "If the user writes in Hinglish, reply in Hinglish. NEVER use any other language. "
    "Ignore the language of the context above - always respond in the user's language from the allowed set.\n"
    "IMPORTANT: If the context contains a specific URL for registration, signup, login, purchase, or any action the user is asking about, include that URL inline in your response. Do not just mention the website name - provide the exact full URL from the context."
)
```

**Note:** The `summary` is appended to the system prompt text at line 475-476.
The `messages` list (which includes the current user query appended at line 478)
is sliced to `MAX_HISTORY=50` at line 586. So the answer LLM sees: system prompt
(with summary) + up to 50 recent user/assistant messages.

---

## 4. The "No Match" / Classification Path

When search returns no chunks (or score is below threshold), `_handle_no_chunks`
is called. It evaluates whether the query is out-of-scope or a knowledge gap,
then builds a no-match prompt. The `FOLLOWUP_NO_MATCH_PROMPT` is used when the
query is a contextual follow-up and there's existing conversation.

```python
# backend/services/chat_service.py:410-440

    async def _handle_no_chunks(
        self,
        turn: ChatTurnInput,
        summary: str,
        messages: list[dict],
        classification: QueryClass,
    ) -> ChatTurnResult:
        tenant_id = turn.tenant["tenant_id"]
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]
        tenant_ai_provider, tenant_ai_model = self._tenant_llm_provider_model(turn.tenant)
        gap_type = "out_of_scope" if classification == QueryClass.OUT_OF_SCOPE else await self._evaluate_no_match(
            turn.query, turn.tenant.get("description"), tenant_ai_provider, tenant_ai_model
        )
        print(f"[CHAT] No match. Gap type: {gap_type}")

        messages.append({"role": "user", "content": turn.query})
        system_prompt = await self._build_no_match_prompt(turn, summary, messages, gap_type)

        forms = await _form_config_repo.get_all_enabled_for_tenant(tenant_id)
        tool_schema = self._build_form_tool(forms) if forms else None

        answer, show_form, form_id, usage = await self._complete_answer(system_prompt, messages, tenant_ai_provider, tenant_ai_model, tools=[tool_schema] if tool_schema else None, forms=forms)
        messages.append({"role": "assistant", "content": answer, "usage": usage})

        summary, messages = await self._compact_if_needed(summary, messages, tenant_ai_provider, tenant_ai_model)
        await self._persist_conversation(turn, summary, messages)
        await self._track_visitor_message(turn.session_id, turn.tenant["tenant_id"])
        if not show_form:
            await self._log_knowledge_gap(tenant_id, turn.query, turn.current_url, gap_type, turn.message_id)

        return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=[], show_enquiry_form=show_form, enquiry_form_id=form_id)
```

The no-match evaluator LLM call:

```python
# backend/services/chat_service.py:810-825

    async def _evaluate_no_match(self, query: str, description: str | None = None, provider: str = "openai", model: str = "gpt-4o-mini") -> str:
        business_context = f"\nThis website is about: {description}" if description else ""
        try:
            llm = get_llm(provider, model)
            resp = await llm.ainvoke(
                [
                    {"role": "system", "content": prompts.NO_MATCH_EVALUATOR_PROMPT.format(business_context=business_context)},
                    {"role": "user", "content": query},
                ]
            )
            result = (resp.content or "").strip().upper()
            if "OUT_OF_SCOPE" in result:
                return "out_of_scope"
            return "no_context"
        except Exception:
            return "no_context"
```

The no-match prompt builder (now uses conversation history unconditionally — the old
`_is_contextual_followup()` check was removed):

```python
# backend/services/chat_service.py:524-544

    async def _build_no_match_prompt(self, turn: ChatTurnInput, summary: str, messages: list[dict], gap_type: str) -> str:
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]

        if summary or messages:
            conversation_text = self._recent_conversation_text(summary, messages, max_messages=30)
            return prompts.FOLLOWUP_NO_MATCH_PROMPT.format(
                business_name=business_name,
                conversation_text=conversation_text,
            )
        if gap_type == "out_of_scope":
            return prompts.NO_MATCH_OUT_OF_SCOPE_PROMPT.format(business_name=business_name)

        description = turn.tenant.get("description") or ""
        if description:
            prompt = prompts.NO_MATCH_WITH_DESCRIPTION_PROMPT.format(
                business_name=business_name,
                description=description,
            )
        else:
            prompt = prompts.NO_MATCH_GENERIC_PROMPT.format(
                business_name=business_name,
            )

        if summary:
            prompt += f"\n\nHere is a summary of the conversation so far:\n{summary}"
        return prompt
```

The follow-up no-match prompt template (used when there is any conversation history):

```python
# backend/services/chat_prompts.py:45-52

FOLLOWUP_NO_MATCH_PROMPT = (
    'You are a representative of {business_name} - always speak as "we" and "our", never as "{business_name}" or a third party.\n'
    "The user's latest message is a follow-up to the existing conversation, but no new knowledge-base context was found.\n\n"
    "Recent conversation:\n{conversation_text}\n\n"
    "Answer only about the most recent specific topic in the conversation. Do not switch to a general overview of our institution, courses, NEET, or JEE unless that was the user's latest specific topic.\n"
    "If the conversation does not contain enough information to answer with more detail, say that we don't have more details about that specific topic right now and suggest contacting us for details.\n"
    "CRITICAL: You MUST ONLY reply in English or Hinglish. If the user writes in English, reply in English. If the user writes in Hinglish, reply in Hinglish. NEVER use any other language."
)
```

**Note:** `_evaluate_no_match` does NOT receive the conversation history — it only
receives the current query and the tenant's description. It classifies based
solely on the query text. The `FOLLOWUP_NO_MATCH_PROMPT` does include
`conversation_text` (up to 30 messages), and it's now used whenever there is any
conversation history (`summary or messages`), not just when a regex matches.
This means even full-sentence follow-ups like "what is the fees" with prior
context get the richer follow-up prompt instead of falling through to a generic
no-match template.

---

## 5. Full Request Handler

The HTTP handler creates the `ChatTurnInput` and calls
`chat_service.handle_message()`. The WebSocket handler does the same but calls
`handle_message_stream()`. The orchestrator is `handle_message()` which calls:
`_load_conversation_context` -> `_classify_query` -> (branching:
greeting/out-of-scope/rewrite/search) -> `search_chunks` -> `_handle_no_chunks`
or `_handle_answer_with_chunks`.

```python
# backend/controllers/chat.py:55-119

@router.post("/chat", response_model=ChatResponse)
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

    if result.show_enquiry_form and result.enquiry_form_id:
        valid_form = await _form_config_repo.get_by_form_id(
            current_tenant["tenant_id"], result.enquiry_form_id
        )
        if not valid_form or not valid_form.get("enabled", True):
            result.show_enquiry_form = False
            result.enquiry_form_id = ""
            if result.answer == "Let me get that for you!":
                result.answer = "Let me help you with that."

    return ChatResponse(
        message_id=result.message_id,
        answer=result.answer,
        sources=result.sources,
        show_enquiry_form=result.show_enquiry_form,
        enquiry_form_id=result.enquiry_form_id,
    )
```

The orchestrator inside `handle_message` (post-simplification — all PROCEED
messages go through LLM rewrite unconditionally):

```python
# backend/services/chat_service.py:141-228

    async def handle_message(self, turn: ChatTurnInput) -> ChatTurnResult:
        tenant_id = turn.tenant["tenant_id"]
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]
        provider, model = self._tenant_llm_provider_model(turn.tenant)

        summary, messages = await self._load_conversation_context(turn.session_id, tenant_id)
        classification = await self._classify_query(turn.query, summary, messages, provider, model)

        if classification == QueryClass.GREETING:
            visitor_name = await self._get_visitor_name(turn.session_id, tenant_id)
            if visitor_name:
                answer = f"Hi {visitor_name}, welcome back to {business_name}! How can I help you today?"
            else:
                answer = f"Hello! Welcome to {business_name}. How can I help you today?"
            await self._track_visitor_message(turn.session_id, turn.tenant["tenant_id"])
            return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=[])

        if classification == QueryClass.OUT_OF_SCOPE:
            messages.append({"role": "user", "content": turn.query})
            system_prompt = prompts.NO_MATCH_OUT_OF_SCOPE_PROMPT.format(business_name=business_name)
            forms = await _form_config_repo.get_all_enabled_for_tenant(tenant_id)
            tool_schema = self._build_form_tool(forms) if forms else None
            answer, show_form, form_id, usage = await self._complete_answer(system_prompt, messages, provider, model, tools=[tool_schema] if tool_schema else None, forms=forms)
            messages.append({"role": "assistant", "content": answer, "usage": usage})
            summary, messages = await self._compact_if_needed(summary, messages, provider, model)
            await self._persist_conversation(turn, summary, messages)
            await self._track_visitor_message(turn.session_id, turn.tenant["tenant_id"])
            if not show_form:
                await self._log_knowledge_gap(tenant_id, turn.query, turn.current_url, "out_of_scope", turn.message_id)
            return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=[], show_enquiry_form=show_form, enquiry_form_id=form_id)

        search_query = turn.query
        needs_search = True

        # Profile classification: fetch profiles if visitor hasn't been classified yet
        profiles = None
        profile_name = None
        try:
            visitor_doc = await db.visitors.find_one(
                {"visitor_id": turn.session_id, "tenant_id": tenant_id},
                {"profile_classification_attempted": 1}
            )
            classification_attempted = visitor_doc.get("profile_classification_attempted") if visitor_doc else True
            if not classification_attempted:
                profiles = await get_enabled_profiles_for_classification(tenant_id)
        except Exception:
            profiles = None

        # Every non-greeting, non-out-of-scope message goes through the LLM
        # rewrite step, which resolves entities/pronouns/follow-ups from
        # conversation history into the search query.
        search_query, profile_name = await self._rewrite_search_query(turn.query, summary, messages, provider, model, profiles=profiles)

        # If profile was identified, classify the visitor
        if profile_name and profiles:
            try:
                await classify_visitor_inline(tenant_id, turn.session_id, profile_name)
            except Exception as e:
                print(f"[CHAT] Profile classification failed: {e}")

        print(f"[CHAT] query='{turn.query}' class={classification} search_query='{search_query}' needs_search={needs_search}")

        chunks = []
        top_score = 0.0
        if needs_search:
            try:
                chunks = await search_chunks(tenant_id, search_query)
            except Exception as e:
                print(f"[CHAT] search_chunks failed: {e}")
                chunks = []
            print(f"[CHAT] search_chunks returned {len(chunks)} chunks")
            if chunks:
                top_score = chunks[0].get("score", 0.0)
                print(f"[CHAT] top score: {top_score:.4f}")

        if chunks and top_score < DIRECT_ANSWER_THRESHOLD:
            print(f"[CHAT] Score {top_score:.4f} below threshold {DIRECT_ANSWER_THRESHOLD}, treating as no match")
            chunks = []

        if not chunks:
            return await self._handle_no_chunks(turn, summary, messages, classification)

        return await self._handle_answer_with_chunks(turn, summary, messages, chunks, needs_search)
```

**Key simplification:** The search query construction is now a single line
(`_rewrite_search_query`) instead of a 3-way branch. There is no
`SEARCH_READY` bypass, no `_is_contextual_followup()` check, and no
`needs_search = False` fallthrough. Every PROCEED message gets rewritten with
conversation context before hitting the knowledge base.

---

## 6. Session / Turn Data Shape

The `ChatRequest` model (what the widget sends):

```python
# backend/models/requests.py:26-30

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    current_url: str
    current_page_title: str
```

The internal `ChatTurnInput` dataclass used within the service:

```python
# backend/services/chat_service.py:45-52

@dataclass
class ChatTurnInput:
    tenant: dict
    session_id: str
    query: str
    current_url: str = ""
    current_page_title: str = ""
    message_id: str = ""
```

The MongoDB schema for the `conversations` collection (what gets stored):

```python
# backend/core/schema_validator.py:238-269

    "conversations": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["session_id", "tenant_id", "current_url", "summary", "messages"],
                "properties": {
                    "session_id": {"bsonType": "string"},
                    "tenant_id": {"bsonType": "string"},
                    "current_url": {"bsonType": "string"},
                    "summary": {"bsonType": "string"},
                    "created_at": {"bsonType": ["date", "null"]},
                    "updated_at": {"bsonType": ["date", "null"]},
                    "messages": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["role", "content"],
                            "properties": {
                                "role": {"enum": ["user", "assistant"]},
                                "content": {"bsonType": "string"},
                            },
                        },
                    },
                    "archived": {"bsonType": "bool"},
                    "archive_key": {"bsonType": ["string", "null"]},
                    "archived_turn_count": {"bsonType": "int"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
```

**Note:** Each message in the `messages` array has only `role` and `content` as
required fields. The `usage` field is added in-memory when appending to the
`messages` list (e.g., `{"role": "assistant", "content": answer, "usage": usage}`)
but is NOT in the MongoDB schema validator — it's just stored as an extra field.
There is no structured "entities", "extracted intent", or "course name" field.
The conversation is purely raw `role`/`content` pairs, relying entirely on the
LLM to extract entities from the text during rewrite/classification.

---

## 7. Bug Root Cause Analysis

### Reported symptom

Visitor says "I am going for JEE dropper" → correct course-specific response.
Next message: "yes, but what is the fees" → generic "please specify which
course" response, as if the earlier message never happened.

### What the code had before the fix

`handle_message()` had two divergent paths for constructing the search query:

```python
# OLD CODE (before fix) — lines 187-194 in the original file

if self._is_contextual_followup(turn.query) and (summary or messages):
    search_query = self._build_contextual_search_query(turn.query, summary, messages)
elif classification == QueryClass.NEEDS_REWRITE:
    search_query, profile_name = await self._rewrite_search_query(turn.query, summary, messages, provider, model, profiles=profiles)
elif classification == QueryClass.SEARCH_READY:
    search_query = turn.query
else:
    needs_search = False
```

### Path 1: `_build_contextual_search_query` (the broken heuristic)

```python
# OLD CODE — REMOVED by this fix

def _build_contextual_search_query(self, query: str, summary: str, messages: list[dict]) -> str:
    conversation_text = self._recent_conversation_text(summary, messages, max_messages=6)
    max_context_chars = 1200
    if len(conversation_text) > max_context_chars:
        conversation_text = conversation_text[-max_context_chars:]

    return (
        f"Latest user follow-up: {query.strip()}\n"
        "Use the recent conversation to resolve what the follow-up refers to:\n"
        f"{conversation_text}"
    )
```

This function was a **non-LLM heuristic**. It concatenated the raw follow-up
query with recent conversation text and sent it directly to `search_chunks()`
(vector search). It never resolved entities — the search engine received a blob
of text and had to figure out what "the fees" referred to from context, which
often failed because vector search works on semantic similarity, not entity
resolution.

### Path 2: `_rewrite_search_query` (the correct LLM-based path)

This function calls the LLM with `QUERY_REWRITE_PROMPT`, which explicitly
instructs: *"Generic continuation requests like 'tell me more', 'fees?',
'eligibility?' must include the most recent specific named topic from the
conversation."* If "what is the fees" went through this path, the LLM would see
the conversation history ("I am going for JEE dropper") and produce "JEE dropper
fees" as the search query.

### Why the bug happened

The `_CONTEXTUAL_FOLLOWUP_PATTERN` regex was very restrictive — it only matched
bare fragments like `"fees?"` or `"eligibility"`, not full questions like
`"what is the fees"` or `"yes, but what is the fees"`. This meant those messages
fell through to `_classify_query()` (the LLM classifier).

The classifier *should* have returned `NEEDS_REWRITE`, which would route to
`_rewrite_search_query()`. But the two-path design was fragile: if the classifier
returned `SEARCH_READY` instead (which the prompt allows for "clear standalone
questions"), the raw query "what is the fees" would go directly to search without
entity resolution — producing generic fee chunks instead of JEE-dropper-specific
content.

The fundamental problem was that **two implementations existed for the same job**
(producing a search query from a follow-up message), and the cheaper heuristic
path (`_build_contextual_search_query`) was not equivalent to the LLM-based path.
Any message that matched the regex went through the broken heuristic; any message
that didn't match relied on the classifier to route correctly — a fragile
dependency on LLM classification accuracy.

### Regex test results

```
False  'yes, but what is the fees'    ← full question, doesn't match bare pattern
False  'what is the fees'             ← full question, doesn't match bare pattern
False  'and the fees?'                ← has prefix, doesn't match
True   'fees?'                        ← bare fragment, matches
True   'tell me more'                 ← matches
True   'eligibility'                  ← matches
False  'I am going for JEE dropper'   ← original statement, doesn't match
```

### Why Round 2 was needed

Round 1 (unifying `_build_contextual_search_query` and `_rewrite_search_query`)
helped, but kept a conditional:
`if (_is_contextual_followup(query) OR classification == NEEDS_REWRITE) AND history`
→ rewrite, `elif classification == SEARCH_READY` → raw query.

This still relied on the LLM classifier to distinguish between `SEARCH_READY`
and `NEEDS_REWRITE`. Nobody had verified what the real classifier returned for
"what is the fees" after "I am going for JEE dropper" — if it returned
`SEARCH_READY`, the context loss bug would reproduce.

The real fix: **remove the branching entirely**. Every non-greeting,
non-out-of-scope message goes through `_rewrite_search_query()` unconditionally.
There is no `SEARCH_READY` bypass. The classifier's only job now is to detect
greetings and out-of-scope queries — a 2-way distinction that is strictly
easier than the old 4-way one.

---

## 8. Changes Made (Round 1 — unify paths)

### File: `backend/services/chat_service.py` (12 insertions, 18 deletions)

#### Change 1: Unified the routing in `handle_message()` (line 192)

**Before:**
```python
if self._is_contextual_followup(turn.query) and (summary or messages):
    search_query = self._build_contextual_search_query(turn.query, summary, messages)
elif classification == QueryClass.NEEDS_REWRITE:
    search_query, profile_name = await self._rewrite_search_query(turn.query, summary, messages, provider, model, profiles=profiles)
elif classification == QueryClass.SEARCH_READY:
    search_query = turn.query
else:
    needs_search = False
```

**After:**
```python
# Contextual follow-ups (e.g. "fees?", "what is the fees") go through the
# LLM rewrite path so that entities from prior turns are resolved into the
# search query — the old _build_contextual_search_query heuristic did not.
if (self._is_contextual_followup(turn.query) or classification == QueryClass.NEEDS_REWRITE) and (summary or messages):
    search_query, profile_name = await self._rewrite_search_query(turn.query, summary, messages, provider, model, profiles=profiles)
elif classification == QueryClass.SEARCH_READY:
    search_query = turn.query
else:
    needs_search = False
```

**What changed:** The `_is_contextual_followup` check now OR's with
`NEEDS_REWRITE` and both route to `_rewrite_search_query()` (LLM-based) instead
of having separate paths. The old `_build_contextual_search_query()` heuristic is
no longer called.

#### Change 2: Same unification in `handle_message_stream()` (line 286)

Identical change as above, applied to the streaming variant of the handler.

#### Change 3: Removed `_build_contextual_search_query()` (was lines 865-875)

The entire method was deleted. It was a non-LLM heuristic that concatenated raw
text and sent it directly to vector search without resolving entities.

#### Change 4: Added documentation comments

- `_CONTEXTUAL_FOLLOWUP_PATTERN` (line 71-72): comment explaining it matches bare
  follow-up fragments that trigger the LLM rewrite path.
- `_is_contextual_followup()` (line 936-937): comment explaining its role.
- Routing block in `handle_message` and `handle_message_stream` (lines 189-191,
  283-285): comment explaining why both paths go through `_rewrite_search_query`.

### Why Option A (unify paths) was chosen over Option B (fix the heuristic)

- `_rewrite_search_query()` already has the correct prompt and conversation
  history access. It's the single source of truth for "resolve a follow-up into a
  search query."
- `_build_contextual_search_query()` was a heuristic that duplicated (poorly) what
  the LLM already does well. Maintaining two implementations meant they could
  silently diverge — which is exactly what happened.
- The only downside of always calling the LLM is a slightly higher latency for
  bare follow-ups like "fees?" — but `_rewrite_search_query` uses
  `gpt-4o-mini` (the cheap model) and the query is short, so the added latency
  is negligible compared to the correctness improvement.

---

## 9. Changes Made (Round 2 — remove branching entirely)

### Motivation

Round 1 unified the two divergent paths (`_build_contextual_search_query` heuristic
vs `_rewrite_search_query` LLM) into one, but kept a conditional
`(_is_contextual_followup(query) OR classification == NEEDS_REWRITE)` that still
allowed a message to bypass entity resolution if the classifier labelled it
`SEARCH_READY` instead. Nobody verified what the real classifier returns for
"what is the fees" after "I am going for JEE dropper" — the bug might still
reproduce.

### The insight

The answer-generation step *already* receives full conversation history (up to
`MAX_HISTORY=50` messages + rolling summary) — that was never the bug. The only
thing that needs conversation-aware resolution is the **search query** sent to
`search_chunks()`, because vector/BM25 search has no memory of prior turns.

Instead of classifying each message into `GREETING` / `OUT_OF_SCOPE` /
`NEEDS_REWRITE` / `SEARCH_READY` and routing accordingly, we collapsed to three
cases:

1. **Greeting** — unchanged, fast regex path.
2. **Out of scope** — unchanged, still needs a classification signal.
3. **Everything else** — always call `_rewrite_search_query()` before search.
   No `SEARCH_READY` vs `NEEDS_REWRITE` distinction, no
   `_is_contextual_followup()` check, no separate heuristic path.

### What was simplified

| Code | Before | After |
|---|---|---|
| `QueryClass` enum | `GREETING`, `OUT_OF_SCOPE`, `SEARCH_READY`, `NEEDS_REWRITE` | `GREETING`, `OUT_OF_SCOPE`, `PROCEED` |
| `_CONTEXTUAL_FOLLOWUP_PATTERN` regex | Existed, matched bare fragments | **Removed** |
| `_is_contextual_followup()` | Method checking the regex | **Removed** |
| `_classify_query()` short-circuits | `_is_contextual_followup` + Devanagari returned `NEEDS_REWRITE` | Both removed (all non-greeting → `PROCEED`) |
| `_classify_query()` LLM fallback | Exception returned `SEARCH_READY` | Exception returns `PROCEED` |
| Search query construction | 3-way branch in `handle_message` + `handle_message_stream` | Single unconditional `_rewrite_search_query()` call |
| `_build_no_match_prompt()` | Checked `_is_contextual_followup()` | Checks `summary or messages` instead |

### Files changed

**`backend/services/chat_service.py`:**
- `QueryClass` enum: collapsed to 3 values
- `_CONTEXTUAL_FOLLOWUP_PATTERN` regex: deleted
- `_is_contextual_followup()` method: deleted
- `_classify_query()`: removed short-circuits, LLM fallback returns `PROCEED`
- `handle_message()` + `handle_message_stream()`: single rewrite line replaces 3-way branch
- `_build_no_match_prompt()`: `if summary or messages` replaces `if _is_contextual_followup(...)`

**`backend/services/chat_prompts.py`:**
- `QUERY_CLASSIFIER_PROMPT`: simplified from 4-label to 3-label prompt

### What stayed the same

- Greeting detection (fast regex, no LLM call)
- Out-of-scope classification and early return
- The `_rewrite_search_query()` call itself (unchanged)
- Knowledge gaps vs out-of-scope tracking in dashboard (completely decoupled)
- Profile classification inline with rewrite

### Latency impact

Every PROCEED message now makes one `gpt-4o-mini` call for rewriting. Previously,
messages the classifier labelled `SEARCH_READY` (clear standalone questions)
skipped this call. Expected added latency is ~100-200ms per message — negligible
next to the answer-generation LLM call that follows.

---

## 10. Tests Added

### File: `test_context_loss_fix.py`

Unit tests that verify the fix without requiring a running server or database.
Run with: `python3 test_context_loss_fix.py`

**Test classes (updated for Round 2):**

1. **`TestSimplifiedRouting`** — Verifies the 3-label routing: `GREETING` →
   greeting, `OUT_OF_SCOPE` → out-of-scope, `PROCEED` → rewrite. No bypass
   exists.

2. **`TestBugScenario`** — Tests all variants of the fee follow-up after JEE
   dropper context: "yes, but what is the fees", "what is the fees", "and the
   fees?", "fees?", "tell me more", "eligibility". Asserts they all route
   through the rewrite path.

3. **`TestOldBranchingRemoved`** — Verifies that `SEARCH_READY` and
   `NEEDS_REWRITE` are no longer valid labels, and that there is no
   `needs_search = False` fallthrough path.

All 6 test cases pass:
```
test_greeting_skips_search ... ok
test_out_of_scope_skips_search ... ok
test_proceed_goes_through_rewrite ... ok
test_all_fee_followups_go_through_rewrite ... ok
test_no_search_ready_bypass ... ok
test_no_needs_rewrite_no_search_path ... ok
```

### File: `test_e2e.py` (new section 7)

End-to-end context loss test added. Sends "I am going for JEE dropper" then
"what is the fees" in the same session and asserts the bot's answer does not
contain disambiguation phrases like "which course" or "please specify" — proving
the rewrite step resolved "the fees" into the prior "JEE dropper" context.
