"""
usage.py — Cálculo de coste por modelo (USD por 1M tokens).

Tabla mínima y editable. Si un modelo no está, coste 0 (no rompe el loop).
Mantener sincronizado con las tarifas públicas de cada proveedor.
"""

from __future__ import annotations

# Precios USD por 1.000.000 de tokens. Claves = model-id (sin el prefijo provider/).
PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-opus-4-8":   {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
    # OpenAI (orientativo)
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
