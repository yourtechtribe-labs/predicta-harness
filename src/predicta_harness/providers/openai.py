"""
openai.py — Provider for OpenAI and ANY OpenAI-compatible endpoint.

This is the one that makes the harness "provider-agnostic": by pointing `base_url`
at an OpenAI-compatible server (Ollama, vLLM, LM Studio, DeepSeek, OpenRouter...),
the same Agent runs against local or third-party models.

    from predicta_harness import register_provider
    from predicta_harness.providers.openai import OpenAIProvider
    register_provider("local", OpenAIProvider(
        base_url="http://localhost:11434/v1", api_key="ollama"))
    # then: Agent(model="local/llama3.1:8b", ...)

Translates between the canonical format (Anthropic-like, with tool_use/tool_result
blocks) and OpenAI's Chat Completions format (tool_calls on the assistant message,
role="tool" messages for the results).
"""

from __future__ import annotations

import json
from typing import Any

from ..tool import Tool
from ..types import AssistantTurn, Message, ToolCall, Usage
from ..usage import cost_for
from .base import Provider


class OpenAIProvider(Provider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None, **client_kwargs: Any):
        import openai  # lazy import
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key or "x", **client_kwargs)

    def complete(
        self, *, model_id, system, messages, tools, max_tokens=2048, **kwargs
    ) -> AssistantTurn:
        oai_messages = self._to_openai_messages(system, messages)
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name, "description": t.description, "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

        resp = self._client.chat.completions.create(
            model=model_id,
            max_tokens=max_tokens,
            messages=oai_messages,
            tools=oai_tools or None,
            **kwargs,
        )
        choice = resp.choices[0].message

        # Rebuild the assistant content in CANONICAL (Anthropic-like) format, so the
        # history is homogeneous regardless of the provider.
        content_blocks: list[dict] = []
        text = choice.content or ""
        if text:
            content_blocks.append({"type": "text", "text": text})

        tool_calls: list[ToolCall] = []
        for tc in (choice.tool_calls or []):
            args = json.loads(tc.function.arguments or "{}")
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))
            content_blocks.append(
                {"type": "tool_use", "id": tc.id, "name": tc.function.name, "input": args}
            )

        u = resp.usage
        inp = getattr(u, "prompt_tokens", 0) or 0
        out = getattr(u, "completion_tokens", 0) or 0
        usage = Usage(
            model=model_id, calls=1, input_tokens=inp, output_tokens=out,
            cost_usd=cost_for(model_id, inp, out, 0, 0),
        )

        stop = "tool_use" if tool_calls else "end_turn"
        return AssistantTurn(
            text=text, tool_calls=tool_calls, content_blocks=content_blocks,
            usage=usage, stop_reason=stop,
        )

    @staticmethod
    def tool_result_block(call: ToolCall, output: str, is_error: bool = False) -> dict:
        """Canonical format (Anthropic-like). The translation to role='tool' happens in _to_openai_messages."""
        block = {"type": "tool_result", "tool_use_id": call.id, "content": output}
        if is_error:
            block["is_error"] = True
        return block

    # --- canonical -> OpenAI Chat Completions translation -------------------

    def _to_openai_messages(self, system: str, messages: list[Message]) -> list[dict]:
        out: list[dict] = []
        if system:
            out.append({"role": "system", "content": system})

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            # Shorthand: content as a plain string
            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue

            if role == "assistant":
                text_parts = [b["text"] for b in content if b.get("type") == "text"]
                tool_uses = [b for b in content if b.get("type") == "tool_use"]
                m: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts) or None}
                if tool_uses:
                    m["tool_calls"] = [
                        {
                            "id": b["id"],
                            "type": "function",
                            "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})},
                        }
                        for b in tool_uses
                    ]
                out.append(m)

            elif role == "user":
                # A user message may carry tool_results (which in OpenAI are role="tool"
                # messages) and/or normal text.
                tool_results = [b for b in content if b.get("type") == "tool_result"]
                texts = [b["text"] for b in content if b.get("type") == "text"]
                if tool_results:
                    for b in tool_results:
                        out.append({
                            "role": "tool",
                            "tool_call_id": b["tool_use_id"],
                            "content": b.get("content", ""),
                        })
                if texts:
                    out.append({"role": "user", "content": "".join(texts)})
        return out
