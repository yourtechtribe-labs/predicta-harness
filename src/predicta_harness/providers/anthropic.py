"""
anthropic.py — Provider para la API de Anthropic (Claude).

El formato canónico del harness ya es Anthropic-like, así que la traducción es
casi una identidad. Solo serializamos los bloques Pydantic del SDK a dicts.
"""

from __future__ import annotations

from typing import Any

from ..tool import Tool
from ..types import AssistantTurn, Message, ToolCall, Usage
from ..usage import cost_for
from .base import Provider


class AnthropicProvider(Provider):
    def __init__(self, api_key: str | None = None, **client_kwargs: Any):
        import anthropic  # import perezoso: solo si se usa este provider
        self._client = anthropic.Anthropic(api_key=api_key, **client_kwargs)

    def complete(
        self, *, model_id, system, messages, tools, max_tokens=2048, **kwargs
    ) -> AssistantTurn:
        tool_specs = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]

        resp = self._client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            system=system or None,
            tools=tool_specs or [],  # Anthropic acepta lista vacía
            messages=messages,
            **kwargs,
        )

        # Serializa los bloques Pydantic del SDK a dicts JSON-ables (para el historial).
        content_blocks = [
            b.model_dump() if hasattr(b, "model_dump") else b for b in resp.content
        ]

        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        tool_calls = [
            ToolCall(id=b["id"], name=b["name"], input=b.get("input") or {})
            for b in content_blocks
            if b.get("type") == "tool_use"
        ]

        u = resp.usage
        inp = getattr(u, "input_tokens", 0) or 0
        out = getattr(u, "output_tokens", 0) or 0
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        usage = Usage(
            model=model_id, calls=1,
            input_tokens=inp, output_tokens=out,
            cache_write_tokens=cw, cache_read_tokens=cr,
            cost_usd=cost_for(model_id, inp, out, cw, cr),
        )

        return AssistantTurn(
            text=text, tool_calls=tool_calls, content_blocks=content_blocks,
            usage=usage, stop_reason=resp.stop_reason or "end_turn",
        )

    @staticmethod
    def tool_result_block(call: ToolCall, output: str, is_error: bool = False) -> dict:
        """Construye el bloque tool_result en formato canónico (= Anthropic)."""
        block = {"type": "tool_result", "tool_use_id": call.id, "content": output}
        if is_error:
            block["is_error"] = True
        return block
