from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import re
import asyncio

from core.auth import db
from core.config import settings
from services.llm.factory import get_llm
from repositories.visitor_profile_repository import VisitorProfileRepository


_profile_repo = VisitorProfileRepository()

_LLM_CLASSIFICATION_PROMPT = """You are a visitor classification system. Given a conversation transcript and candidate visitor profile descriptions, determine which profile best fits the visitor.

Profiles:
{profiles_text}

Conversation summary: The visitor has had {session_count} session(s), sent {message_count} message(s), visited {page_count} page(s), and submitted {lead_count} lead(s).

Conversation transcript from all sessions:
{transcript}

Visitor page views:
{page_views}

Lead form submissions:
{leads}

UTM source: {utm_source}

Respond with ONLY the profile name that best matches, or "NONE" if no profile fits. Match based on semantic fit between the visitor's behavior and the profile descriptions."""


def _match_page_visited(page_views: List[Dict[str, Any]], pattern: str) -> bool:
    for pv in page_views:
        url = pv.get("url", "")
        if pattern.endswith("*"):
            if url.startswith(pattern[:-1]):
                return True
        elif pattern.startswith("*") and pattern.endswith("*"):
            if pattern[1:-1] in url:
                return True
        elif pattern.startswith("*"):
            if url.endswith(pattern[1:]):
                return True
        elif url == pattern:
            return True
    return False


def _match_keyword(user_messages: List[str], keywords: List[str]) -> bool:
    for msg in user_messages:
        msg_lower = msg.lower()
        for kw in keywords:
            try:
                if re.search(kw, msg_lower, re.IGNORECASE):
                    return True
            except re.error:
                if kw.lower() in msg_lower:
                    return True
    return False


def _match_utm_source(visitor: Dict[str, Any], sources: List[str]) -> bool:
    utm = visitor.get("utm_source", "") or ""
    return utm.lower() in [s.lower() for s in sources]


class VisitorProfileService:

    async def classify_visitor(self, visitor_id: str, tenant_id: str) -> None:
        try:
            await self._classify_visitor_inner(visitor_id, tenant_id)
        except Exception as e:
            print(f"[VISITOR_PROFILE] Classification error for visitor {visitor_id}: {e}")

    async def _classify_visitor_inner(self, visitor_id: str, tenant_id: str) -> None:
        visitor = await db.visitors.find_one(
            {"session_id": visitor_id, "tenant_id": tenant_id}
        )
        if not visitor:
            return

        profiles = await _profile_repo.get_enabled_by_tenant(tenant_id)
        if not profiles:
            return

        session_ids = visitor.get("conversation_ids", [])
        all_messages = []
        for sid in session_ids:
            conv = await db.conversations.find_one(
                {"session_id": sid, "tenant_id": tenant_id},
                {"messages": 1}
            )
            if conv:
                all_messages.extend(conv.get("messages", []))

        total_messages = len(all_messages)
        page_views = visitor.get("page_views", [])
        user_messages = [
            m.get("content", "") for m in all_messages if m.get("role") == "user"
        ]

        leads_cursor = db.leads.find(
            {"session_id": {"$in": session_ids}, "tenant_id": tenant_id},
            {"_id": 0}
        ).sort("created_at", -1)
        leads = await leads_cursor.to_list(length=100)

        utm_source = visitor.get("utm_source", "") or ""

        matched_profile = self._evaluate_rules(
            profiles, page_views, leads, total_messages, user_messages, utm_source
        )

        source = "rule"
        reason = ""
        profile_id = None
        profile_label = None
        profile_confidence = None

        if matched_profile:
            profile_id = matched_profile["profile_id"]
            profile_label = matched_profile["name"]
            profile_confidence = 1.0
            reason = f"Rule match: {matched_profile.get('name', '')}"
        else:
            llm_profiles = [p for p in profiles if p.get("llm_criteria")]
            if llm_profiles:
                result = await self._evaluate_llm(
                    llm_profiles, visitor, all_messages, page_views,
                    leads, utm_source, tenant_id
                )
                if result:
                    profile_id, profile_label, reason, confidence = result
                    profile_confidence = confidence
                    source = "llm"
                    reason = reason or "LLM classification"

        now = datetime.now(timezone.utc)
        history_entry = {
            "profile_id": profile_id,
            "profile_label": profile_label,
            "assigned_at": now,
            "reason": reason,
            "source": source,
        } if profile_id else None

        update = {
            "$set": {
                "profile_id": profile_id,
                "profile_label": profile_label,
                "profile_confidence": profile_confidence,
                "last_classified_at": now,
            }
        }

        if history_entry:
            update["$push"] = {"profile_history": history_entry}

        await db.visitors.update_one(
            {"session_id": visitor_id, "tenant_id": tenant_id},
            update,
        )

    def _evaluate_rules(
        self,
        profiles: List[Dict[str, Any]],
        page_views: List[Dict[str, Any]],
        leads: List[Dict[str, Any]],
        total_messages: int,
        user_messages: List[str],
        utm_source: str,
    ) -> Optional[Dict[str, Any]]:
        sorted_profiles = sorted(
            profiles,
            key=lambda p: min((r.get("priority", 0) for r in p.get("rules", [])), default=0),
            reverse=True,
        )

        for profile in sorted_profiles:
            for rule in profile.get("rules", []):
                rule_type = rule.get("type", "")
                if rule_type == "page_visited":
                    if _match_page_visited(page_views, rule["pattern"]):
                        return profile
                elif rule_type == "lead_form_field":
                    for lead in leads:
                        custom_fields = lead.get("custom_fields", {}) or {}
                        val = custom_fields.get(rule["field_key"], "")
                        if val and rule["pattern"].lower() in val.lower():
                            return profile
                elif rule_type == "message_count_gte":
                    if total_messages >= rule["count"]:
                        return profile
                elif rule_type == "keyword_match":
                    if _match_keyword(user_messages, rule["keywords"]):
                        return profile
                elif rule_type == "utm_source":
                    if _match_utm_source({"utm_source": utm_source}, rule["sources"]):
                        return profile
        return None

    async def _evaluate_llm(
        self,
        profiles: List[Dict[str, Any]],
        visitor: Dict[str, Any],
        messages: List[Dict[str, Any]],
        page_views: List[Dict[str, Any]],
        leads: List[Dict[str, Any]],
        utm_source: str,
        tenant_id: str,
    ) -> Optional[tuple]:
        profiles_text = "\n".join(
            f"- {p['name']}: {p.get('llm_criteria', '')}"
            for p in profiles
        )

        transcript = "\n".join(
            f"{'Visitor' if m.get('role') == 'user' else 'Bot'}: {m.get('content', '')}"
            for m in messages[-30:]
        )

        page_views_text = "\n".join(
            f"- {pv.get('url', '')} ({pv.get('title', '')})"
            for pv in page_views[-10:]
        )

        leads_text = "\n".join(
            f"- {l.get('name', '')} ({l.get('email', '')}): custom_fields={l.get('custom_fields', {})}"
            for l in leads[-5:]
        )

        prompt = _LLM_CLASSIFICATION_PROMPT.format(
            profiles_text=profiles_text,
            session_count=len(visitor.get("conversation_ids", [])),
            message_count=len(messages),
            page_count=len(page_views),
            lead_count=len(leads),
            transcript=transcript[:3000],
            page_views=page_views_text[:1000],
            leads=leads_text[:1000],
            utm_source=utm_source or "none",
        )

        try:
            llm = get_llm("openai", "gpt-4o-mini")
            resp = await llm.ainvoke([
                {"role": "system", "content": "You are a visitor classification assistant. Respond with only the profile name or NONE."},
                {"role": "user", "content": prompt},
            ])
            result = (resp.content or "").strip()
            if result == "NONE" or not result:
                return None

            for p in profiles:
                if p["name"].lower() == result.lower():
                    return (p["profile_id"], p["name"], f"LLM matched: {result}", 0.85)
            return None
        except Exception as e:
            print(f"[VISITOR_PROFILE] LLM classification error: {e}")
            return None