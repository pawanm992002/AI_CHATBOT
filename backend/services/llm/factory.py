from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from openai import AsyncOpenAI

DEFAULT_PROVIDER: str = "openai"
DEFAULT_MODEL_FALLBACK: str = "gpt-4o-mini"


def _normalize_provider(provider: str | None) -> str:
    return (provider or "").strip().lower() or DEFAULT_PROVIDER


def _normalize_model(model: str | None) -> str:
    return (model or "").strip() or DEFAULT_MODEL_FALLBACK


@dataclass
class _ChatLike:
    """
    Minimal LangChain-like interface for this codebase:
      - business logic calls `await llm.ainvoke(messages)`
      - returns an object with `.content` containing the assistant text
    """
    _client: AsyncOpenAI
    _model: str

    async def ainvoke(self, messages: list[dict[str, Any]]) -> Any:
        # Coerce to OpenAI-compatible message params: [{"role": "...", "content": "..."}]
        coerced_messages: list[dict[str, str]] = []
        for m in messages:
            role = (m.get("role") or "").strip()
            content = (m.get("content") or "")
            if not role:
                continue
            coerced_messages.append({"role": role, "content": content})

        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=coerced_messages,  # type: ignore[arg-type]
        )
        content = resp.choices[0].message.content or ""
        return type("LLMResult", (), {"content": content})


def get_llm(provider: str, model: str) -> Any:
    """
    Provider-agnostic LLM factory using OpenAI-compatible APIs.

    This repo does not have `langchain_openai` / `langchain_groq` installed,
    so we provide a tiny LangChain-core compatible surface: `.ainvoke(messages)`.

    Provider-specific code lives only in this module.
    """
    provider_norm = _normalize_provider(provider)
    model_norm = _normalize_model(model)

    try:
        if provider_norm == "openai":
            # Uses OPENAI_API_KEY from environment/config (already in project)
            client = AsyncOpenAI()
            return _ChatLike(_client=client, _model=model_norm)

        if provider_norm == "groq":
            client = AsyncOpenAI(
                api_key=None,  # let openai pick up env var
                base_url="https://api.groq.com/openai/v1",
            )
            return _ChatLike(_client=client, _model=model_norm)

        if provider_norm == "openrouter":
            client = AsyncOpenAI(
                api_key=None,
                base_url="https://openrouter.ai/api/v1",
            )
            return _ChatLike(_client=client, _model=model_norm)

        raise ValueError(f"Unknown LLM provider: {provider_norm}")

    except Exception as e:
        # Required error handling:
        # - log the error
        # - fall back to default OpenAI model
        # - do not crash chatbot
        print(
            f"[LLM] init failed provider={provider_norm} model={model_norm} err={e!r}; falling back to OpenAI."
        )
        try:
            client = AsyncOpenAI()
            return _ChatLike(_client=client, _model=DEFAULT_MODEL_FALLBACK)
        except Exception as e2:
            # If fallback also fails: propagate meaningful error
            raise RuntimeError(f"LLM fallback to OpenAI failed: {e2!r}") from e2
