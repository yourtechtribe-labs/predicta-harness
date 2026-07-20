"""The OpenAI provider must preserve WHY the model stopped.

Regression test for a real bug found on 2026-07-20 while evaluating an
OpenAI-compatible vendor (CompactifAI):

    stop = "tool_use" if tool_calls else "end_turn"   # <- dropped finish_reason

A reply truncated at `max_tokens` reached the caller as "end_turn", i.e. it was
indistinguishable from a complete one. Meanwhile the Anthropic provider already
forwarded its real `stop_reason`, so the SAME AssistantTurn meant different
things depending on the provider — while its docstring promises a *normalized*
result and states that "the Agent never touches the raw API". If the caller
cannot reach the raw response and the normalized field is wrong, the signal is
gone for good.

Why it bites in practice: models that emit a `reasoning` field spend output
tokens on it BEFORE writing `content`. On a tight budget the reasoning eats the
allowance and `content` comes back empty with finish_reason="length" (measured:
3 out of 4 calls at max_tokens=20). A caller seeing "end_turn" would treat that
empty answer as a legitimate reply from the model.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from predicta_harness.providers.openai import OpenAIProvider


def _resp(finish_reason, *, content="hi", tool_calls=None):
    """Minimal stand-in for an OpenAI ChatCompletion response."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    return SimpleNamespace(choices=[choice], usage=usage)


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [
        ("stop", "end_turn"),
        ("length", "max_tokens"),      # the one that was being lost
        ("tool_calls", "tool_use"),
        ("content_filter", "content_filter"),
        ("function_call", "tool_use"),
    ],
)
def test_finish_reason_maps_to_canonical_vocabulary(finish_reason, expected):
    assert OpenAIProvider._canonical_stop_reason(_resp(finish_reason)) == expected


def test_truncation_is_no_longer_reported_as_a_normal_end():
    """The actual bug: `length` must NOT arrive as "end_turn"."""
    assert OpenAIProvider._canonical_stop_reason(_resp("length")) != "end_turn"


def test_unknown_finish_reasons_pass_through_instead_of_being_collapsed():
    """A new value from the provider should surface, not be renamed silently."""
    assert OpenAIProvider._canonical_stop_reason(_resp("some_new_reason")) == "some_new_reason"


@pytest.mark.parametrize("broken", [SimpleNamespace(), SimpleNamespace(choices=[]), None])
def test_a_malformed_response_defaults_to_end_turn_without_crashing(broken):
    """Never break the loop over a missing field: that IS the right call here."""
    assert OpenAIProvider._canonical_stop_reason(broken) == "end_turn"


def test_missing_finish_reason_defaults_to_end_turn():
    assert OpenAIProvider._canonical_stop_reason(_resp(None)) == "end_turn"
