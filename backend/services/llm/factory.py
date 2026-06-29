from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from core.config import settings

DEFAULT_PROVIDER: str = "openai"
DEFAULT_MODEL_FALLBACK: str = "gpt-4o-mini"


def _normalize_provider(provider: str | None) -> str:
    return (provider or "").strip().lower() or DEFAULT_PROVIDER


def _normalize_model(model: str | None) -> str:
    return (model or "").strip() or DEFAULT_MODEL_FALLBACK


def _to_lc_messages(messages: list[dict[str, Any]]):
    """Convert role/content dicts to LangChain message objects."""
    lc_messages = []
    for m in messages:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "")
        if not role:
            continue
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))
    return lc_messages


@dataclass
class _LLMWrapper:
    """Wraps a LangChain BaseChatModel to accept dict messages (backward compat)."""
    _llm: BaseChatModel

    async def ainvoke(self, messages: list[dict[str, Any]]) -> Any:
        lc_messages = _to_lc_messages(messages)
        return await self._llm.ainvoke(lc_messages)


def get_llm(provider: str, model: str) -> _LLMWrapper:
    """
    Provider-agnostic LLM factory.

    Returns a wrapper with `.ainvoke(dict_messages)` support.
    Provider-specific code lives only in this module.
    """
    provider_norm = _normalize_provider(provider)
    model_norm = _normalize_model(model)

    try:
        if provider_norm == "openai":
            from langchain_openai import ChatOpenAI
            return _LLMWrapper(_llm=ChatOpenAI(
                model=model_norm,
                api_key=settings.OPENAI_API_KEY,
                max_retries=3,
            ))

        if provider_norm == "groq":
            from langchain_openai import ChatOpenAI
            return _LLMWrapper(_llm=ChatOpenAI(
                model=model_norm,
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1",
                max_retries=3,
            ))

        if provider_norm == "openrouter":
            from langchain_openai import ChatOpenAI
            return _LLMWrapper(_llm=ChatOpenAI(
                model=model_norm,
                api_key=settings.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
                max_retries=3,
            ))

        raise ValueError(f"Unknown LLM provider: {provider_norm}")

    except Exception as e:
        print(
            f"[LLM] init failed provider={provider_norm} model={model_norm} err={e!r}; falling back to OpenAI."
        )
        try:
            from langchain_openai import ChatOpenAI
            return _LLMWrapper(_llm=ChatOpenAI(
                model=DEFAULT_MODEL_FALLBACK,
                api_key=settings.OPENAI_API_KEY,
                max_retries=3,
            ))
        except Exception as e2:
            raise RuntimeError(f"LLM fallback to OpenAI failed: {e2!r}") from e2
