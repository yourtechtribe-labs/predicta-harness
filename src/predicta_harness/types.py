"""
types.py — Normalized harness types, independent of the provider.

The canonical message format is deliberately *Anthropic-like* (`text` / `tool_use`
/ `tool_result` blocks), because it is the cleanest. Each Provider translates
to/from its own API from this format. That way the Agent and the loop never know
which provider they are talking to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from .usage import cost_for

# A canonical message: role + content. content may be a plain string (shorthand
# for text) or a list of blocks (dicts) like Anthropic's.
Role = Literal["user", "assistant"]
Message = dict[str, Any]  # {"role": Role, "content": str | list[Block]}
Block = dict[str, Any]    # {"type": "text"|"tool_use"|"tool_result", ...}


@dataclass
class ToolCall:
    """A model request to run a tool (still just text)."""
    id: str
    name: str
    input: dict[str, Any]
    # Set by a provider when the model's tool-call arguments could NOT be parsed (e.g. a
    # JSON string truncated at the token limit). The agent loop then feeds this actionable
    # message back to the model instead of calling the tool with empty args (which would
    # raise a cryptic "missing required argument"). None = parsed fine.
    parse_error: str | None = None


@dataclass
class Usage:
    """Token and cost accounting for a run (accumulable)."""
    model: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    unpriced_calls: int = 0
    """Calls whose model has no entry in the pricing table.

    `cost_usd` is therefore a LOWER BOUND whenever this is non-zero, and a total
    that quietly omitted them would be indistinguishable from a complete one.
    Counting them instead of poisoning the total to None keeps the part that IS
    known usable: "$0.42 across 99 calls, 1 unpriced" is actionable, a bare None
    across a hundred calls is not.
    """

    @classmethod
    def for_call(
        cls, model_id: str, input_tokens: int, output_tokens: int,
        cache_write: int = 0, cache_read: int = 0,
        *, on: date | None = None,
    ) -> "Usage":
        """Build the Usage for a single model call (calls=1) and compute its cost.

        `on` is passed through to the rate lookup so a test can pin the date a
        promotional price is evaluated against; None means now, which is the
        right answer for a call actually being made.
        """
        cost = cost_for(model_id, input_tokens, output_tokens, cache_write, cache_read, on=on)
        return cls(
            model=model_id, calls=1,
            input_tokens=input_tokens, output_tokens=output_tokens,
            cache_write_tokens=cache_write, cache_read_tokens=cache_read,
            cost_usd=0.0 if cost is None else cost,
            unpriced_calls=1 if cost is None else 0,
        )

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.cost_usd += other.cost_usd
        self.unpriced_calls += other.unpriced_calls

    def __str__(self) -> str:
        tin = self.input_tokens + self.cache_read_tokens + self.cache_write_tokens
        cost = f"${self.cost_usd:.4f}"
        if self.unpriced_calls:
            # The figure is a floor, and it says so where anyone reading it looks.
            cost = f">={cost} ({self.unpriced_calls} unpriced)"
        return f"{tin}->{self.output_tokens} tok · {cost} · {self.calls} call(s)"


@dataclass
class AssistantTurn:
    """
    Normalized result of ONE model call (one assistant turn). Returned by every
    Provider.complete(); the Agent never touches the raw API.
    """
    text: str
    tool_calls: list[ToolCall]
    content_blocks: list[Block]   # assistant content in canonical format (for the history)
    usage: Usage
    stop_reason: str              # "end_turn" | "tool_use" | other


def tool_result_block(tool_use_id: str, output: str, is_error: bool = False) -> Block:
    """Build a canonical tool_result block (provider-independent)."""
    block: Block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": output}
    if is_error:
        block["is_error"] = True
    return block


@dataclass
class RunResult:
    """What Agent.run() returns: final text + telemetry + the full message history."""
    text: str
    usage: Usage
    messages: list[Message] = field(default_factory=list)
    steps: int = 0                # how many loop iterations (model calls) it took
    data: Any = None              # validated object, if result_schema was passed (structured output)
    # STRUCTURED termination signal (the authoritative way to know why the loop ended —
    # natural-language text is ambiguous, per the Claude Agent SDK stop-reason guidance):
    #   "end_turn"  → the model finished on its own (or submitted structured output)
    #   "max_steps" → the iteration cap (a safety net) was hit before the model finished
    stop_reason: str = "end_turn"
