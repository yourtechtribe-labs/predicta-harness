"""
anthropic.py — Provider for the Anthropic API (Claude).

The harness canonical format is already Anthropic-like, so the translation is almost
an identity. We only serialize the SDK's Pydantic blocks to dicts.
"""

from __future__ import annotations

from typing import Any

from ..tool import Tool
from ..types import AssistantTurn, Message, ToolCall, Usage
from .base import Provider


class AnthropicProvider(Provider):
    def __init__(self, api_key: str | None = None, **client_kwargs: Any):
        import anthropic  # lazy import: only if this provider is used
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
            tools=tool_specs or [],  # Anthropic accepts an empty list
            messages=messages,
            **kwargs,
        )

        # Serialize the SDK's Pydantic blocks to JSON-able dicts (for the history).
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
        usage = Usage.for_call(
            model_id,
            getattr(u, "input_tokens", 0) or 0,
            getattr(u, "output_tokens", 0) or 0,
            cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
            cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
        )

        return AssistantTurn(
            text=text, tool_calls=tool_calls, content_blocks=content_blocks,
            usage=usage, stop_reason=resp.stop_reason or "end_turn",
        )
