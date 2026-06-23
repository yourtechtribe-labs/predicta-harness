"""A scripted Provider: yields pre-baked AssistantTurns by call index.

Lets us drive the real Agent loop (real tools, real sandbox) deterministically, with NO
live model — so the integration test asserts the write→run→answer flow offline.
"""

from __future__ import annotations

from typing import Any

from predicta_harness.providers.base import Provider
from predicta_harness.types import AssistantTurn, ToolCall, Usage


class ScriptedProvider(Provider):
    """`turns` is a list of specs, consumed one per `complete()` call:
    ("tool", id, name, input_dict)  → a tool_use turn
    ("text", final_text)            → an end_turn (final answer)
    """

    def __init__(self, turns: list[tuple]) -> None:
        self._turns = turns
        self.calls = 0

    def complete(self, *, model_id: str, system: str, messages: list, tools: list,
                 max_tokens: int = 2048, **kwargs: Any) -> AssistantTurn:
        spec = self._turns[min(self.calls, len(self._turns) - 1)]
        self.calls += 1
        usage = Usage(model=model_id, calls=1, input_tokens=1, output_tokens=1)
        if spec[0] == "tool":
            _, tid, name, inp = spec[:4]
            parse_error = spec[4] if len(spec) > 4 else None  # optional 5th element
            return AssistantTurn(
                text="",
                tool_calls=[ToolCall(id=tid, name=name, input=inp, parse_error=parse_error)],
                content_blocks=[{"type": "tool_use", "id": tid, "name": name, "input": inp}],
                usage=usage,
                stop_reason="tool_use",
            )
        _, text = spec
        return AssistantTurn(
            text=text, tool_calls=[],
            content_blocks=[{"type": "text", "text": text}],
            usage=usage, stop_reason="end_turn",
        )
