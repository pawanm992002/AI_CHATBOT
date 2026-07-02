import json
import os
from fastapi import APIRouter, HTTPException
from typing import Any

router = APIRouter(tags=["providers"])

_MODELS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "models.json")


def _load_models() -> list[dict[str, Any]]:
    try:
        with open(_MODELS_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load models.json at {_MODELS_PATH}: {e!r}") from e


@router.get("/providers")
async def list_providers() -> list[str]:
    models = _load_models()
    providers = sorted({str(m.get("provider")) for m in models if m.get("provider")})
    return [p.title() if p.lower() != "openrouter" else "OpenRouter" for p in providers]


@router.get("/providers/{provider}/models")
async def list_provider_models(provider: str) -> list[dict[str, Any]]:
    provider_norm = (provider or "").strip().lower()
    if not provider_norm:
        raise HTTPException(status_code=400, detail="provider is required")

    models = _load_models()
    filtered = [
        {
            "id": m["id"],
            "name": m.get("name", m["id"]),
            "input_price": m.get("input_price"),
            "output_price": m.get("output_price"),
        }
        for m in models
        if (m.get("provider") or "").strip().lower() == provider_norm
    ]

    if not filtered:
        raise HTTPException(status_code=404, detail=f"No models for provider={provider}")

    return filtered
