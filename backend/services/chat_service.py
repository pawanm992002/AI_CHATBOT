from dataclasses import dataclass
from enum import StrEnum
import json
import re

import numpy as np

from core.auth import db
from core.redis import redis_client
from services.embedder import openai_client
from services.vector_search import search_chunks
from views.responses import ChatSource
from repositories.lead_repository import LeadFormConfigRepository

from . import chat_prompts as prompts


MAX_HISTORY = 50
MAX_REWRITE_HISTORY = 12
DIRECT_ANSWER_THRESHOLD = 0.5

_form_config_repo = LeadFormConfigRepository()


class QueryClass(StrEnum):
    GREETING = "GREETING"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SEARCH_READY = "SEARCH_READY"
    NEEDS_REWRITE = "NEEDS_REWRITE"


@dataclass
class ChatTurnInput:
    tenant: dict
    session_id: str
    query: str
    current_url: str = ""
    current_page_title: str = ""
    message_id: str = ""


@dataclass
class ChatTurnResult:
    message_id: str
    answer: str
    sources: list[ChatSource]
    show_enquiry_form: bool = False


_GREETING_PATTERN = re.compile(
    r'^(hi|hello|hey|yo|howdy|hola|namaste|namaskar|good\s*(morning|afternoon|evening|night)|'
    r'what\'?s?\s*up|sup|how\s*are\s*you|hru|gm|gn|bye|thanks|thank\s*you|ok|okay|'
    r'chalo|acha|theek\s*hai|haan|ji|sir|madam|boss|dost)\s*[!.?]*$',
    re.IGNORECASE,
)

_CONTEXTUAL_FOLLOWUP_PATTERN = re.compile(
    r"^\s*(tell\s+me\s+more|more|more\s+about\s+(it|this|that|the\s+exam)|"
    r"details?|explain|what\s+else|eligibility|fees?|date|exam\s+date|"
    r"syllabus|registration|apply|how\s+to\s+apply|where|when|in\s+.+)\s*[?.!]*\s*$",
    re.IGNORECASE,
)

_DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")


class ChatService:
    async def _get_enquiry_form_instruction(self, tenant_id: str) -> str:
        """Get the enquiry form instruction for a tenant based on their lead form config."""
        config = await _form_config_repo.get_enabled_for_tenant(tenant_id)
        if not config:
            return prompts.NO_ENQUIRY_FORM_INSTRUCTION
        trigger = config.get("trigger_instructions", "").strip()
        if trigger:
            return f"However, if {trigger}, offer to help and at the end of your response append [ENQUIRY_FORM]. "
        return prompts.DEFAULT_ENQUIRY_FORM_INSTRUCTION

    async def handle_message(self, turn: ChatTurnInput) -> ChatTurnResult:
        tenant_id = turn.tenant["tenant_id"]
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]

        summary, messages = await self._load_conversation_context(turn.session_id)
        classification = await self._classify_query(turn.query, summary, messages)

        if classification == QueryClass.GREETING:
            answer = f"Hello! Welcome to {business_name}. How can I help you today?"
            await self._track_visitor_message(turn.session_id)
            return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=[])

        if classification == QueryClass.OUT_OF_SCOPE:
            messages.append({"role": "user", "content": turn.query})
            system_prompt = prompts.NO_MATCH_OUT_OF_SCOPE_PROMPT.format(business_name=business_name)
            answer, show_form = await self._complete_answer(system_prompt, messages)
            messages.append({"role": "assistant", "content": answer})
            summary, messages = await self._compact_if_needed(summary, messages)
            await self._persist_conversation(turn, summary, messages)
            await self._track_visitor_message(turn.session_id)
            if not show_form:
                await self._log_knowledge_gap(tenant_id, turn.query, turn.current_url, "out_of_scope", turn.message_id)
            return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=[], show_enquiry_form=show_form)

        search_query = turn.query
        needs_search = True
        if self._is_contextual_followup(turn.query) and (summary or messages):
            search_query = self._build_contextual_search_query(turn.query, summary, messages)
        elif classification == QueryClass.NEEDS_REWRITE:
            search_query = await self._rewrite_search_query(turn.query, summary, messages)
        elif classification == QueryClass.SEARCH_READY:
            search_query = turn.query
        else:
            needs_search = False

        print(f"[CHAT] query='{turn.query}' class={classification} search_query='{search_query}' needs_search={needs_search}")

        chunks = []
        top_score = 0.0
        if needs_search:
            chunks = await search_chunks(tenant_id, search_query)
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

    async def _handle_no_chunks(
        self,
        turn: ChatTurnInput,
        summary: str,
        messages: list[dict],
        classification: QueryClass,
    ) -> ChatTurnResult:
        tenant_id = turn.tenant["tenant_id"]
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]
        gap_type = "out_of_scope" if classification == QueryClass.OUT_OF_SCOPE else await self._evaluate_no_match(
            turn.query, turn.tenant.get("description")
        )
        print(f"[CHAT] No match. Gap type: {gap_type}")

        messages.append({"role": "user", "content": turn.query})
        system_prompt = self._build_no_match_prompt(turn, summary, messages, gap_type)
        answer, show_form = await self._complete_answer(system_prompt, messages)
        messages.append({"role": "assistant", "content": answer})

        summary, messages = await self._compact_if_needed(summary, messages)
        await self._persist_conversation(turn, summary, messages)
        await self._track_visitor_message(turn.session_id)
        if not show_form:
            await self._log_knowledge_gap(tenant_id, turn.query, turn.current_url, gap_type, turn.message_id)

        return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=[], show_enquiry_form=show_form)

    async def _handle_answer_with_chunks(
        self,
        turn: ChatTurnInput,
        summary: str,
        messages: list[dict],
        chunks: list[dict],
        needs_search: bool,
    ) -> ChatTurnResult:
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]
        sources = self._build_sources(chunks)
        enquiry_instruction = await self._get_enquiry_form_instruction(turn.tenant["tenant_id"])

        if needs_search:
            context_text = "\n\n".join([self._format_context_chunk(c) for c in chunks])
            system_prompt = prompts.ANSWER_WITH_CONTEXT_PROMPT.format(
                business_name=business_name,
                current_url=turn.current_url,
                current_page_title=turn.current_page_title,
                context_text=context_text,
                enquiry_form_instruction=enquiry_instruction,
            )
        else:
            system_prompt = prompts.DIRECT_ANSWER_PROMPT.format(
                business_name=business_name,
                enquiry_form_instruction=enquiry_instruction,
            )

        if summary:
            system_prompt += f"\n\nHere is a summary of the conversation so far:\n{summary}"

        messages.append({"role": "user", "content": turn.query})
        answer, show_form = await self._complete_answer(system_prompt, messages)
        messages.append({"role": "assistant", "content": answer})

        summary, messages = await self._compact_if_needed(summary, messages)
        await self._persist_conversation(turn, summary, messages)
        await self._track_visitor_message(turn.session_id)

        return ChatTurnResult(message_id=turn.message_id, answer=answer, sources=sources, show_enquiry_form=show_form)

    async def _classify_query(self, query: str, summary: str, messages: list[dict]) -> QueryClass:
        q = query.strip()
        if self._is_greeting(q):
            return QueryClass.GREETING
        if self._is_contextual_followup(q) and (summary or messages):
            return QueryClass.NEEDS_REWRITE
        if _DEVANAGARI_PATTERN.search(q):
            return QueryClass.NEEDS_REWRITE

        conversation_text = self._recent_conversation_text(summary, messages)
        user_prompt = q
        if conversation_text:
            user_prompt = f"Conversation so far:\n{conversation_text}\n\nLatest user message: {q}"

        try:
            resp = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompts.QUERY_CLASSIFIER_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=20,
                temperature=0.0,
            )
            label = resp.choices[0].message.content.strip().upper()
            return QueryClass(label) if label in QueryClass.__members__ else QueryClass.NEEDS_REWRITE
        except Exception:
            return QueryClass.SEARCH_READY

    async def _rewrite_search_query(self, query: str, summary: str, messages: list[dict]) -> str:
        conversation_text = self._recent_conversation_text(summary, messages)
        user_prompt = f"Latest user message: {query.strip()}"
        if conversation_text:
            user_prompt = (
                f"Conversation so far:\n{conversation_text}\n\n"
                f"Latest user message: {query.strip()}"
            )

        try:
            resp = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompts.QUERY_REWRITE_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=80,
                temperature=0.0,
            )
            rewritten = resp.choices[0].message.content.strip()
            return rewritten if rewritten and len(rewritten) <= 240 else query.strip()
        except Exception:
            return query.strip()

    async def _build_no_match_prompt(self, turn: ChatTurnInput, summary: str, messages: list[dict], gap_type: str) -> str:
        business_name = turn.tenant.get("business_name") or turn.tenant["domain"]
        enquiry_instruction = await self._get_enquiry_form_instruction(turn.tenant["tenant_id"])

        if self._is_contextual_followup(turn.query) and (summary or messages):
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
                enquiry_form_instruction=enquiry_instruction,
            )
        else:
            prompt = prompts.NO_MATCH_GENERIC_PROMPT.format(
                business_name=business_name,
                enquiry_form_instruction=enquiry_instruction,
            )

        if summary:
            prompt += f"\n\nHere is a summary of the conversation so far:\n{summary}"
        return prompt

    async def _complete_answer(self, system_prompt: str, messages: list[dict], model: str = "gpt-4o") -> tuple[str, bool]:
        api_messages = [{"role": "system", "content": system_prompt}] + messages[-MAX_HISTORY:]
        response = await openai_client.chat.completions.create(
            model=model,
            messages=api_messages,
        )
        answer = response.choices[0].message.content
        show_form = "[ENQUIRY_FORM]" in answer
        if show_form:
            answer = answer.replace("[ENQUIRY_FORM]", "").strip()
        return answer, show_form

    async def _load_conversation_context(self, session_id: str) -> tuple[str, list[dict]]:
        cache_key = f"chat_session:{session_id}"
        try:
            cached_data_str = await redis_client.get(cache_key)
            if cached_data_str:
                cached_data = json.loads(cached_data_str)
                return cached_data.get("summary", ""), cached_data.get("messages", [])
        except Exception as e:
            print(f"Redis get failed: {e}")

        session = await db.conversations.find_one({"session_id": session_id})
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
        cache_key = f"chat_session:{turn.session_id}"
        await db.conversations.update_one(
            {"session_id": turn.session_id},
            {"$set": {
                "tenant_id": turn.tenant["tenant_id"],
                "current_url": turn.current_url,
                "summary": summary,
                "messages": messages,
            }},
            upsert=True,
        )
        try:
            await redis_client.setex(cache_key, 3600, json.dumps({"summary": summary, "messages": messages}))
        except Exception as e:
            print(f"Redis set failed: {e}")

    async def _track_visitor_message(self, session_id: str) -> None:
        await db.visitors.update_one(
            {"session_id": session_id},
            {"$addToSet": {"conversation_ids": session_id}, "$inc": {"total_messages": 1}},
        )

    async def _compact_if_needed(self, summary: str, messages: list[dict]) -> tuple[str, list[dict]]:
        if len(messages) < 32:
            return summary, messages

        messages_to_keep = messages[-30:]
        messages_to_summarize = messages[:-30]
        summary = await self._summarize_past_context(summary, messages_to_summarize)
        return summary, messages_to_keep

    async def _summarize_past_context(self, previous_summary: str, messages_to_summarize: list[dict]) -> str:
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
            resp = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompts.SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"Failed to summarize chat history: {e}")
            return previous_summary

    async def _evaluate_no_match(self, query: str, description: str | None = None) -> str:
        business_context = f"\nThis website is about: {description}" if description else ""
        try:
            resp = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompts.NO_MATCH_EVALUATOR_PROMPT.format(business_context=business_context)},
                    {"role": "user", "content": query},
                ],
                max_tokens=20,
                temperature=0.0,
            )
            result = resp.choices[0].message.content.strip().upper()
            if "OUT_OF_SCOPE" in result:
                return "out_of_scope"
            return "no_context"
        except Exception:
            return "no_context"

    async def _log_knowledge_gap(self, tenant_id: str, query: str, url: str, gap_type: str, message_id: str) -> None:
        try:
            normalized = query.lower().strip()
            normalized = re.sub(r"[^\w\s]", "", normalized)
            normalized = re.sub(r"\s+", " ", normalized)

            embedding_resp = await openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=query,
            )
            embedding = embedding_resp.data[0].embedding
            new_embedding = np.array(embedding)

            open_gaps = await db.knowledge_gaps.find({
                "tenant_id": tenant_id,
                "status": "open",
                "embedding": {"$exists": True},
            }, {
                "query": 1,
                "embedding": 1,
                "count": 1,
            }).to_list(1000)

            best_match = None
            best_similarity = 0.0
            similarity_threshold = 0.85
            for gap in open_gaps:
                if not gap.get("embedding"):
                    continue
                existing_embedding = np.array(gap["embedding"])
                similarity = np.dot(new_embedding, existing_embedding) / (
                    np.linalg.norm(new_embedding) * np.linalg.norm(existing_embedding)
                )

                gap_normalized = re.sub(r"[^\w\s]", "", gap["query"].lower().strip())
                gap_normalized = re.sub(r"\s+", " ", gap_normalized)
                if gap_normalized == normalized:
                    similarity = 1.0

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = gap

            if best_match and best_similarity > similarity_threshold:
                from datetime import datetime, timezone

                await db.knowledge_gaps.update_one(
                    {"_id": best_match["_id"]},
                    {"$inc": {"count": 1}, "$set": {"last_seen": datetime.now(timezone.utc)}},
                )
                print(f"[KNOWLEDGE] Merged query with existing gap (similarity: {best_similarity:.3f})")
                return

            from datetime import datetime, timezone

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

    def _is_greeting(self, query: str) -> bool:
        return bool(_GREETING_PATTERN.match(query.strip()))

    def _is_contextual_followup(self, query: str) -> bool:
        return bool(_CONTEXTUAL_FOLLOWUP_PATTERN.match(query.strip()))
