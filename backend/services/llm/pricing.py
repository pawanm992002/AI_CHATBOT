"""Centralized LLM pricing table and cost calculation.

Pricing is per 1M tokens. Update the PRICING table when adding new models.
"""

from __future__ import annotations

# (prompt_cost_per_1m, completion_cost_per_1m) in USD
PRICING: dict[tuple[str, str], tuple[float, float]] = {
    # OpenAI
    ("openai", "gpt-4o"): (2.50, 10.00),
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
    ("openai", "gpt-4o-turbo"): (10.00, 30.00),
    ("openai", "gpt-3.5-turbo"): (0.50, 1.50),
    # Groq
    ("groq", "llama-3.1-8b-instant"): (0.05, 0.08),
    ("groq", "llama-3.1-70b-versatile"): (0.59, 0.79),
    ("groq", "mixtral-8x7b-32768"): (0.24, 0.24),
    # OpenRouter (approximate, varies)
    ("openrouter", "anthropic/claude-3-haiku"): (0.25, 1.25),
    ("openrouter", "meta-llama/llama-3.1-8b-instant"): (0.05, 0.08),
    ("openrouter", "google/gemini-2.0-flash-001"): (0.10, 0.40),
}

# Fallback pricing when model is unknown
DEFAULT_PRICING: tuple[float, float] = (0.15, 0.60)


def calculate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Calculate estimated cost in USD for a single LLM call.

    Returns 0.0 if both token counts are zero or negative.
    """
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0

    key = (provider.strip().lower(), model.strip().lower())
    prompt_price, completion_price = PRICING.get(key, DEFAULT_PRICING)

    cost = (prompt_tokens * prompt_price + completion_tokens * completion_price) / 1_000_000
    return round(cost, 6)
