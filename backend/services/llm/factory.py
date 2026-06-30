from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

from core.config import settings

DEFAULT_PROVIDER: str = "openai"
DEFAULT_MODEL_FALLBACK: str = "gpt-4o-mini"


def extract_usage(response: Any, provider: str, model: str, latency_ms: float = 0.0) -> dict[str, Any]:
    """Extract token usage metadata from a LangChain LLM response.

    Returns a dict with prompt_tokens, completion_tokens, total_tokens,
    reasoning_tokens, cached_tokens, provider, model, latency_ms,
    and status. Missing values default to 0.
    """
    usage: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
        "provider": provider,
        "model": model,
        "latency_ms": round(latency_ms, 1),
        "status": "success",
    }

    try:
        meta = getattr(response, "response_metadata", None) or {}
        token_usage = meta.get("token_usage") or {}
        if token_usage:
            usage["prompt_tokens"] = token_usage.get("prompt_tokens", 0) or 0
            usage["completion_tokens"] = token_usage.get("completion_tokens", 0) or 0
            usage["total_tokens"] = token_usage.get("total_tokens", 0) or 0
            usage["reasoning_tokens"] = token_usage.get("reasoning_tokens", 0) or 0
            usage["cached_tokens"] = token_usage.get("cached_tokens", 0) or 0
            return usage

        # LangChain may also store usage in usage_metadata
        usage_meta = getattr(response, "usage_metadata", None) or {}
        if usage_meta:
            usage["prompt_tokens"] = usage_meta.get("input_tokens", 0) or 0
            usage["completion_tokens"] = usage_meta.get("output_tokens", 0) or 0
            usage["total_tokens"] = usage_meta.get("total_tokens", 0) or 0
    except Exception:
        pass

    return usage


def _normalize_provider(provider: str | None) -> str:
    return (provider or "").strip().lower() or DEFAULT_PROVIDER


def _normalize_model(model: str | None) -> str:
    return (model or "").strip() or DEFAULT_MODEL_FALLBACK


def _to_lc_messages(messages: list[dict[str, Any]]):
    """Convert role/content dicts to LangChain message objects.

    Handles system, human, assistant (with optional tool_calls), and tool roles.
    """
    lc_messages = []
    for m in messages:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "")
        if not role:
            continue
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "tool":
            lc_messages.append(ToolMessage(
                content=content,
                tool_call_id=m.get("tool_call_id", ""),
            ))
        elif role == "assistant":
            msg = AIMessage(content=content)
            if m.get("tool_calls"):
                msg.tool_calls = m["tool_calls"]
            lc_messages.append(msg)
        else:
            lc_messages.append(HumanMessage(content=content))
    return lc_messages


@dataclass
class _LLMWrapper:
    """Wraps a LangChain BaseChatModel to accept dict messages (backward compat)."""
    _llm: BaseChatModel

    async def ainvoke(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        lc_messages = _to_lc_messages(messages)
        start = time.perf_counter()
        try:
            result = await self._llm.ainvoke(lc_messages, **kwargs)
            latency_ms = (time.perf_counter() - start) * 1000
            # Attach latency to response for extract_usage
            if not hasattr(result, "_latency_ms"):
                result._latency_ms = latency_ms
            return result
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            # Re-raise with latency info attached to the exception
            e._latency_ms = latency_ms
            raise

    async def astream(self, messages: list[dict[str, Any]], **kwargs) -> AsyncGenerator[str | dict[str, Any], None]:
        """Stream tokens from the LLM, yielding each token string.

        Yields token strings during generation, then a final dict with usage metadata:
        {"usage": {"prompt_tokens": int, "completion_tokens": int, ...}}
        """
        lc_messages = _to_lc_messages(messages)
        usage_data: dict[str, Any] | None = None
        start = time.perf_counter()
        try:
            async for chunk in self._llm.astream(lc_messages, **kwargs):
                if chunk.content and isinstance(chunk.content, str):
                    yield chunk.content
                # Capture usage from the final chunk
                usage_meta = getattr(chunk, "usage_metadata", None)
                if usage_meta:
                    usage_data = {
                        "usage": {
                            "prompt_tokens": getattr(usage_meta, "input_tokens", 0) or 0,
                            "completion_tokens": getattr(usage_meta, "output_tokens", 0) or 0,
                            "total_tokens": getattr(usage_meta, "total_tokens", 0) or 0,
                        }
                    }
            latency_ms = (time.perf_counter() - start) * 1000
            if usage_data:
                usage_data["usage"]["latency_ms"] = round(latency_ms, 1)
                usage_data["usage"]["status"] = "success"
            yield usage_data or {"usage": {"latency_ms": round(latency_ms, 1), "status": "success"}}
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            yield {"usage": {"latency_ms": round(latency_ms, 1), "status": "error", "error": str(e)[:200]}}
            raise


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


def get_llm_raw(provider: str, model: str) -> BaseChatModel:
    """Return the raw LangChain BaseChatModel for bind_tools() usage."""
    return get_llm(provider, model)._llm
