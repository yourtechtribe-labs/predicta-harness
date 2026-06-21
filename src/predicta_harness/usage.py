"""
usage.py — Per-model cost calculation (USD per 1M tokens).

Minimal, editable table. If a model is missing, cost is 0 (never breaks the loop).
Keep in sync with each provider's public pricing.
"""

from __future__ import annotations

# Prices in USD per 1,000,000 tokens. Keys = model-id (without the provider/ prefix).
PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-opus-4-8":   {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
    # OpenAI (indicative)
    "gpt-4o":            {"input": 2.50, "output": 10.00, "cache_write": 0.0, "cache_read": 1.25},
    # Local models (Ollama, vLLM, LM Studio...): no API cost
    "llama3.1:8b":       {"input": 0.0, "output": 0.0, "cache_write": 0.0, "cache_read": 0.0},
}


def cost_for(model_id: str, input_tok: int, output_tok: int, cache_write: int, cache_read: int) -> float:
    p = PRICING.get(model_id)
    if p is None:
        return 0.0
    return (
        input_tok * p["input"]
        + output_tok * p["output"]
        + cache_write * p["cache_write"]
        + cache_read * p["cache_read"]
    ) / 1_000_000
