from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import asyncio
import json
import re
import time

from core.auth import db
from core.redis import redis_client, get_redis_key
from services.embedder import embed_text
from services.llm.factory import get_llm, get_llm_raw, _to_lc_messages, extract_usage
from services.llm.pricing import calculate_cost
from services.vector_search import search_chunks
from repositories.knowledge_gap_repository import _vector_search_gaps
from views.responses import ChatSource
from repositories.lead_repository import LeadFormConfigRepository

from . import chat_prompts as prompts
from services.archival_service import archival_service
from services.visitor_profile_service import (
    get_enabled_profiles_for_classification,
    build_profile_classification_prompt,
    parse_profile_from_rewrite_response,
    classify_visitor_inline,
    get_visitor_profile_context,
)


MAX_HISTORY = 50
MAX_REWRITE_HISTORY = 12
DIRECT_ANSWER_THRESHOLD = 0.5

_form_config_repo = LeadFormConfigRepository()


class QueryClass(StrEnum):
    GREETING = "GREETING"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    PROCEED = "PROCEED"


@dataclass
class ChatTurnInput:
    tenant: dict
    session_id: str
    query: str
    visitor_id: str = ""
    current_url: str = ""
    current_page_title: str = ""
    message_id: str = ""


@dataclass
class ChatTurnResult:
    message_id: str
    answer: str
    sources: list[ChatSource]
    show_enquiry_form: bool = False
    enquiry_form_id: str = ""


_GREETING_PATTERN = re.compile(
    r'^(hi|hello|hey|yo|howdy|hola|namaste|namaskar|good\s*(morning|afternoon|evening|night)|'
    r'what\'?s?\s*up|sup|how\s*are\s*you|hru|gm|gn|bye|thanks|thank\s*you|ok|okay|'
    r'chalo|acha|theek\s*hai|haan|ji|sir|madam|boss|dost)\s*[!.?]*$',
    re.IGNORECASE,
)

_DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")


class ChatService:
    def _tenant_llm_provider_model(self, tenant: dict) -> tuple[str, str]:
        ai_cfg = tenant.get("ai") or {}
        provider = (ai_cfg.get("provider") or "openai").strip()
        model = (ai_cfg.get("model") or "gpt-4o-mini").strip()
        return provider, model

    @staticmethod
    def _build_form_tool(forms: list[dict]) -> dict:
        """Build OpenAI tool schema for form routing from tenant's form configs."""
        form_ids = sorted([f["form_id"] for f in forms if f.get("form_id")])
        if not form_ids:
            return {}
        form_descriptions = []
        for f in forms:
            fid = f.get("form_id", "")
            title = f.get("title", "Contact Form")
            trigger = f.get("trigger_instructions", "").strip()
            if fid:
                if trigger:
                    desc = f'"{title}" — EXCLUSIVE MATCH: {trigger}'
                else:
                    desc = f'"{title}"'
                form_descriptions.append(desc)
        forms_list = "\n".join(f"  - {d}" for d in form_descriptions)
        return {
            "type": "function",
            "function": {
                "name": "show_enquiry_form",
                "description": (
                    "Show a lead capture form to the user. "
                    "Call this when the user's intent clearly matches ONE of the available forms below. "
                    "Do NOT call this for general questions — only for action-oriented intent "
                    "(enrollment, demo, callback, scholarship, application, pricing, etc.).\n\n"
                    "When multiple forms could match, the EXCLUSIVE MATCH rules above determine which form to use. "
                    "Each form specifies the exact conditions under which it should be shown — follow those conditions strictly.\n\n"
                    "FOLLOW-UP RULE: If the user's message is a short affirmation (yes, sure, ok, please, yeah, haan, okay, alright, confirm) "
                    "and the previous assistant message offered a specific form or asked if the user wants help with something, "
                    "call the same form that was previously offered. Do NOT pick a different form on follow-ups.\n\n"
                    f"Available forms:\n{forms_list}\n\n"
                    "IMPORTANT: When you call this tool, you MUST also include a brief text response "
                    "to the user (e.g., 'Sure, here's the form for your request!'). "
                    "Never call this tool without also providing text."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "form_id": {
                            "type": "string",
                            "description": "The ID of the most relevant form to show",
                            "enum": form_ids,
                        }
                    },
                    "required": ["form_id"],
                },
            },
        }

    async def handle_message(self, turn: ChatTurnInput) -> ChatTurnResult:
        tenant_id = turn.tenant["tenant_id"]
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]
        provider, model = self._tenant_llm_provider_model(turn.tenant)

        summary, messages = await self._load_conversation_context(turn.session_id, tenant_id)
        classification = await self._classify_query(turn.query, summary, messages, provider, model)

        if classification == QueryClass.GREETING:
            visitor_name = await self._get_visitor_name(turn.visitor_id or turn.session_id, tenant_id)
            if visitor_name:
                answer = f"Hi {visitor_name}, welcome back to {business_name}! How can I help you today?"
            else:
                answer = f"Hello! Welcome to {business_name}. How can I help you today?"
            await self._track_visitor_message(turn.session_id, turn.visitor_id or turn.session_id, turn.tenant["tenant_id"])
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
            await self._track_visitor_message(turn.session_id, turn.visitor_id or turn.session_id, turn.tenant["tenant_id"])
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
                {"visitor_id": turn.visitor_id or turn.session_id, "tenant_id": tenant_id},
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
                await classify_visitor_inline(tenant_id, turn.visitor_id or turn.session_id, profile_name)
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

    async def handle_message_stream(self, turn: ChatTurnInput, on_token):
        """
        Streaming version of handle_message.
        Calls on_token(token_str) for each LLM token during answer generation.
        Non-answer LLM calls (classify, rewrite) run normally without streaming.
        """
        tenant_id = turn.tenant["tenant_id"]
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]
        provider, model = self._tenant_llm_provider_model(turn.tenant)

        summary, messages = await self._load_conversation_context(turn.session_id, tenant_id)
        classification = await self._classify_query(turn.query, summary, messages, provider, model)

        if classification == QueryClass.GREETING:
            visitor_name = await self._get_visitor_name(turn.visitor_id or turn.session_id, tenant_id)
            if visitor_name:
                answer = f"Hi {visitor_name}, welcome back to {business_name}! How can I help you today?"
            else:
                answer = f"Hello! Welcome to {business_name}. How can I help you today?"
            await self._track_visitor_message(turn.session_id, turn.visitor_id or turn.session_id, turn.tenant["tenant_id"])
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
            await self._track_visitor_message(turn.session_id, turn.visitor_id or turn.session_id, turn.tenant["tenant_id"])
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
                {"visitor_id": turn.visitor_id or turn.session_id, "tenant_id": tenant_id},
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
                await classify_visitor_inline(tenant_id, turn.visitor_id or turn.session_id, profile_name)
            except Exception as e:
                print(f"[CHAT] Profile classification failed: {e}")

        chunks = []
        top_score = 0.0
        if needs_search:
            chunks = await search_chunks(tenant_id, search_query)
            if chunks:
                top_score = chunks[0].get("score", 0.0)

        if chunks and top_score < DIRECT_ANSWER_THRESHOLD:
            chunks = []

        if not chunks:
            return await self._handle_no_chunks_stream(turn, summary, messages, classification, on_token)

        return await self._handle_answer_with_chunks_stream(turn, summary, messages, chunks, needs_search, on_token)

    async def _handle_no_chunks_stream(self, turn, summary, messages, classification, on_token):
        """Streaming version of _handle_no_chunks."""
        tenant_id = turn.tenant["tenant_id"]
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]
        tenant_ai_provider, tenant_ai_model = self._tenant_llm_provider_model(turn.tenant)
        gap_type = "out_of_scope" if classification == QueryClass.OUT_OF_SCOPE else await self._evaluate_no_match(
            turn.query, turn.tenant.get("description"), tenant_ai_provider, tenant_ai_model
        )

        messages.append({"role": "user", "content": turn.query})
        system_prompt = await self._build_no_match_prompt(turn, summary, messages, gap_type)

        forms = await _form_config_repo.get_all_enabled_for_tenant(tenant_id)
        tool_schema = self._build_form_tool(forms) if forms else None

        full_answer = ""
        show_form = False
        form_id = ""
        usage: dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0, "provider": tenant_ai_provider, "model": tenant_ai_model, "latency_ms": 0.0, "status": "success"}
        async for item in self._complete_answer_stream(system_prompt, messages, tenant_ai_provider, tenant_ai_model, tools=[tool_schema] if tool_schema else None, forms=forms):
            if isinstance(item, dict):
                full_answer = item["answer"]
                show_form = item["show_form"]
                form_id = item["form_id"]
                usage = item.get("usage", usage)
            else:
                full_answer += item
                await on_token(item)

        messages.append({"role": "assistant", "content": full_answer, "usage": usage})
        summary, messages = await self._compact_if_needed(summary, messages, tenant_ai_provider, tenant_ai_model)
        await self._persist_conversation(turn, summary, messages)
        await self._track_visitor_message(turn.session_id, turn.visitor_id or turn.session_id, turn.tenant["tenant_id"])
        if not show_form:
            await self._log_knowledge_gap(tenant_id, turn.query, turn.current_url, gap_type, turn.message_id)

        return ChatTurnResult(message_id=turn.message_id, answer=full_answer, sources=[], show_enquiry_form=show_form, enquiry_form_id=form_id)

    async def _handle_answer_with_chunks_stream(self, turn, summary, messages, chunks, needs_search, on_token):
        """Streaming version of _handle_answer_with_chunks."""
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

        identity_ctx = await self._get_visitor_identity_context(turn.visitor_id or turn.session_id, tenant_id)
        if identity_ctx:
            system_prompt += identity_ctx

        profile_context = await get_visitor_profile_context(tenant_id, turn.visitor_id or turn.session_id)
        if profile_context:
            system_prompt += profile_context

        if summary:
            system_prompt += f"\n\nHere is a summary of the conversation so far:\n{summary}"

        messages.append({"role": "user", "content": turn.query})
        tenant_ai_provider, tenant_ai_model = self._tenant_llm_provider_model(turn.tenant)

        forms = await _form_config_repo.get_all_enabled_for_tenant(turn.tenant["tenant_id"])
        tool_schema = self._build_form_tool(forms) if forms else None

        full_answer = ""
        show_form = False
        form_id = ""
        usage: dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0, "provider": tenant_ai_provider, "model": tenant_ai_model, "latency_ms": 0.0, "status": "success"}
        async for item in self._complete_answer_stream(system_prompt, messages, tenant_ai_provider, tenant_ai_model, tools=[tool_schema] if tool_schema else None, forms=forms):
            if isinstance(item, dict):
                full_answer = item["answer"]
                show_form = item["show_form"]
                form_id = item["form_id"]
                usage = item.get("usage", usage)
            else:
                full_answer += item
                await on_token(item)

        messages.append({"role": "assistant", "content": full_answer, "usage": usage})
        summary, messages = await self._compact_if_needed(summary, messages, tenant_ai_provider, tenant_ai_model)
        await self._persist_conversation(turn, summary, messages)
        await self._track_visitor_message(turn.session_id, turn.visitor_id or turn.session_id, turn.tenant["tenant_id"])

        return ChatTurnResult(message_id=turn.message_id, answer=full_answer, sources=sources, show_enquiry_form=show_form, enquiry_form_id=form_id)

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
        await self._track_visitor_message(turn.session_id, turn.visitor_id or turn.session_id, turn.tenant["tenant_id"])
        if not show_form:
            await self._log_knowledge_gap(tenant_id, turn.query, turn.current_url, gap_type, turn.message_id)

        return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=[], show_enquiry_form=show_form, enquiry_form_id=form_id)

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

        identity_ctx = await self._get_visitor_identity_context(turn.visitor_id or turn.session_id, tenant_id)
        if identity_ctx:
            system_prompt += identity_ctx

        profile_context = await get_visitor_profile_context(tenant_id, turn.visitor_id or turn.session_id)
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
        await self._track_visitor_message(turn.session_id, turn.visitor_id or turn.session_id, turn.tenant["tenant_id"])

        return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=sources, show_enquiry_form=show_form, enquiry_form_id=form_id)

    async def _classify_query(self, query: str, summary: str, messages: list[dict], provider: str = "openai", model: str = "gpt-4o-mini") -> QueryClass:
        q = query.strip()
        if self._is_greeting(q):
            return QueryClass.GREETING

        conversation_text = self._recent_conversation_text(summary, messages)
        user_prompt = q
        if conversation_text:
            user_prompt = f"Conversation so far:\n{conversation_text}\n\nLatest user message: {q}"

        try:
            llm = get_llm(provider, model)
            resp = await llm.ainvoke(
                [
                    {"role": "system", "content": prompts.QUERY_CLASSIFIER_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )
            label = (resp.content or "").strip().upper()
            return QueryClass(label) if label in QueryClass.__members__ else QueryClass.PROCEED
        except Exception:
            return QueryClass.PROCEED

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

    async def _complete_answer_stream(self, system_prompt: str, messages: list[dict], provider: str = "openai", model: str = "gpt-4o", tools: list[dict] | None = None, forms: list[dict] | None = None):
        """Stream answer tokens with optional tool calling. Yields token strings, then a final dict."""
        if tools:
            system_prompt += (
                "\n\nWhen the user expresses intent to take a specific action "
                "(enroll, book, apply, request a call back, etc.), use the show_enquiry_form tool "
                "to show the most relevant form. Always include a brief text response alongside the tool call."
            )
        api_messages = [{"role": "system", "content": system_prompt}] + messages[-MAX_HISTORY:]
        raw_llm = get_llm_raw(provider, model)
        lc_messages = _to_lc_messages(api_messages)

        if tools:
            llm_with_tools = raw_llm.bind_tools(tools, tool_choice="auto")
        else:
            llm_with_tools = raw_llm

        full_answer = ""
        tool_call_args_by_index: dict[int, str] = {}
        tool_call_names: dict[int, str] = {}
        usage: dict[str, Any] = {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "reasoning_tokens": 0, "cached_tokens": 0,
            "provider": provider, "model": model,
            "latency_ms": 0.0, "status": "success",
        }

        start = time.perf_counter()
        try:
            async for chunk in llm_with_tools.astream(lc_messages):
                if isinstance(chunk, dict) and "usage" in chunk:
                    # Final usage dict from _LLMWrapper.astream
                    stream_usage = chunk["usage"]
                    usage["prompt_tokens"] = stream_usage.get("prompt_tokens", 0) or 0
                    usage["completion_tokens"] = stream_usage.get("completion_tokens", 0) or 0
                    usage["total_tokens"] = stream_usage.get("total_tokens", 0) or 0
                    usage["latency_ms"] = stream_usage.get("latency_ms", 0.0)
                    usage["status"] = stream_usage.get("status", "success")
                    if stream_usage.get("error"):
                        usage["error"] = stream_usage["error"]
                    continue
                if chunk.content and isinstance(chunk.content, str):
                    full_answer += chunk.content
                    yield chunk.content
                for tc_chunk in (getattr(chunk, "tool_call_chunks", None) or []):
                    idx: int = tc_chunk.get("index", 0)  # type: ignore[assignment]
                    if tc_chunk.get("name"):
                        tool_call_names[idx] = tc_chunk["name"]
                    if tc_chunk.get("args"):
                        tool_call_args_by_index[idx] = tool_call_args_by_index.get(idx, "") + tc_chunk["args"]
                # Capture usage from streaming chunks
                usage_meta = getattr(chunk, "usage_metadata", None)
                if usage_meta:
                    usage["prompt_tokens"] = getattr(usage_meta, "input_tokens", 0) or 0
                    usage["completion_tokens"] = getattr(usage_meta, "output_tokens", 0) or 0
                    usage["total_tokens"] = getattr(usage_meta, "total_tokens", 0) or 0
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            usage["latency_ms"] = round(latency_ms, 1)
            usage["status"] = "error"
            usage["error"] = str(e)[:200]
            yield {"answer": full_answer, "show_form": False, "form_id": "", "usage": usage}
            return

        if usage["latency_ms"] == 0.0:
            usage["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)

        show_form = False
        form_id = ""
        for idx, args_str in tool_call_args_by_index.items():
            if tool_call_names.get(idx) == "show_enquiry_form":
                try:
                    args = json.loads(args_str)
                    if args.get("form_id"):
                        show_form = True
                        form_id = args["form_id"]
                except (json.JSONDecodeError, KeyError):
                    pass

        if show_form and not full_answer:
            fallback = "Let me get that for you!"
            full_answer = fallback
            yield fallback

        yield {"answer": full_answer, "show_form": show_form, "form_id": form_id, "usage": usage}

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

    async def _track_visitor_message(self, session_id: str, visitor_id: str, tenant_id: str) -> None:
        await db.visitors.update_one(
            {"visitor_id": visitor_id, "tenant_id": tenant_id},
            {"$addToSet": {"conversation_ids": session_id}, "$inc": {"total_messages": 1}},
        )

    async def _compact_if_needed(self, summary: str, messages: list[dict], provider: str = "openai", model: str = "gpt-4o-mini") -> tuple[str, list[dict]]:
        if len(messages) <= 32:
            return summary, messages

        # Summarize the oldest messages beyond the most recent 32, then trim to 30
        messages_to_summarize = messages[:-32]
        summary = await self._summarize_past_context(summary, messages_to_summarize, provider, model)
        messages = messages[-30:]
        return summary, messages

    async def _summarize_past_context(self, previous_summary: str, messages_to_summarize: list[dict], provider: str = "openai", model: str = "gpt-4o-mini") -> str:
        formatted_history = "\n".join([
            f"{'Visitor' if msg['role'] == 'user' else 'Bot'}: {msg['content']}"
            for msg in messages_to_summarize
        ])

        total_chars = sum(len(msg["content"]) for msg in messages_to_summarize) + len(previous_summary)
        word_limit = max(80, min(500, total_chars // 20))
        max_tokens = word_limit * 2
        previous_summary_block = f"Previous Summary:\n{previous_summary}\n\n" if previous_summary else ""
        prompt = prompts.SUMMARY_PROMPT.format(
            word_limit=word_limit,
            previous_summary_block=previous_summary_block,
            formatted_history=formatted_history,
        )

        try:
            llm = get_llm(provider, model)
            resp = await llm.ainvoke(
                [
                    {"role": "system", "content": prompts.SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
            return (resp.content or "").strip()
        except Exception as e:
            print(f"Failed to summarize chat history: {e}")
            return previous_summary

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

    async def _log_knowledge_gap(self, tenant_id: str, query: str, url: str, gap_type: str, message_id: str) -> None:
        try:
            from datetime import datetime, timezone

            embedding = await embed_text(query)

            best_match = None
            best_similarity = 0.0

            results = await _vector_search_gaps(tenant_id, embedding, threshold=0.85, limit=5)
            for gap in results:
                score = gap.get("score", 0)
                if score > best_similarity:
                    best_similarity = score
                    best_match = gap

            if best_match and best_similarity > 0.85:
                await db.knowledge_gaps.update_one(
                    {"_id": best_match["_id"]},
                    {"$inc": {"count": 1}, "$set": {"last_seen": datetime.now(timezone.utc)}},
                )
                print(f"[KNOWLEDGE] Merged query with existing gap (similarity: {best_similarity:.3f})")
                return

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

    def _build_sources(self, chunks: list[dict]) -> list[ChatSource]:
        sources = []
        seen_sources = set()
        for c in chunks:
            url = c.get("url", "")
            if not url.startswith("http://") and not url.startswith("https://"):
                continue
            section_title = c.get("section_title")
            section_path = c.get("section_path")
            source_key = (url, section_path or section_title or "")
            if source_key not in seen_sources:
                sources.append(ChatSource(
                    url=url,
                    title=c.get("title") or "Relevant Page",
                    section_title=section_title,
                    section_path=section_path,
                ))
                seen_sources.add(source_key)
        return sources

    def _format_context_chunk(self, chunk: dict) -> str:
        title = chunk.get("title") or "Relevant Page"
        section = chunk.get("section_path") or chunk.get("section_title")
        heading = f"Source ({chunk['url']})"
        if section:
            heading = f"{heading} - {title} - {section}"
        elif title:
            heading = f"{heading} - {title}"
        return f"{heading}:\n{chunk['text']}"

    async def _get_visitor_name(self, visitor_id: str, tenant_id: str) -> str | None:
        try:
            visitor = await db.visitors.find_one(
                {"visitor_id": visitor_id, "tenant_id": tenant_id},
                {"identity.name": 1}
            )
            if visitor:
                identity = visitor.get("identity") or {}
                name = identity.get("name")
                if name and name.strip():
                    return name.strip()
        except Exception:
            pass
        return None

    async def _get_visitor_identity_context(self, visitor_id: str, tenant_id: str) -> str:
        name = await self._get_visitor_name(visitor_id, tenant_id)
        if name:
            return f"\nThe visitor's name is {name}. Naturally use their name in conversation when appropriate."
        return ""

    def _is_greeting(self, query: str) -> bool:
        return bool(_GREETING_PATTERN.match(query.strip()))
