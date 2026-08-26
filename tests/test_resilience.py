import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from predicta_harness.agent import Agent
from predicta_harness.providers.base import Provider, register_provider
from predicta_harness.resilience import run_with_resilience
from predicta_harness.types import AssistantTurn, Usage


class SlowProvider(Provider):
    """A real `Provider` that actually blocks — the case that matters for a timeout test
    is a hang, not a mock that answers fast."""

    def __init__(self, hang_seconds: float):
        self.hang_seconds = hang_seconds
        self.calls = 0

    def complete(self, *, model_id: str, system: str, messages: list, tools: list,
                 max_tokens: int = 2048, **kwargs: Any) -> AssistantTurn:
        self.calls += 1
        time.sleep(self.hang_seconds)
        return AssistantTurn(
            text="should never get here", tool_calls=[], content_blocks=[],
            usage=Usage(model=model_id), stop_reason="end_turn",
        )


class FlakyProvider(Provider):
    """Hangs on the first call, answers fast on the second."""

    def __init__(self, hang_seconds: float):
        self.hang_seconds = hang_seconds
        self.calls = 0

    def complete(self, *, model_id: str, system: str, messages: list, tools: list,
                 max_tokens: int = 2048, **kwargs: Any) -> AssistantTurn:
        self.calls += 1
        if self.calls == 1:
            time.sleep(self.hang_seconds)
        return AssistantTurn(
            text="ok", tool_calls=[], content_blocks=[],
            usage=Usage(model=model_id), stop_reason="end_turn",
        )


def _agent(provider_id: str, provider: Provider) -> Agent:
    register_provider(provider_id, provider)
    return Agent(model=f"{provider_id}/test-model")


def test_never_hangs_beyond_the_configured_timeout():
    agent = _agent("resilience-slow-1", SlowProvider(hang_seconds=0.3))

    start = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run_with_resilience(agent, "hi", history=[], timeout_s=0.05, max_retries=1))
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"took {elapsed}s: hung past the timeout"


def test_backoff_sequence_is_1_2_4_seconds():
    agent = _agent("resilience-slow-2", SlowProvider(hang_seconds=0.3))

    with patch("predicta_harness.resilience.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(run_with_resilience(agent, "hi", history=[], timeout_s=0.01, max_retries=4))

    sleep_calls = [call.args[0] for call in mock_sleep.await_args_list]
    assert sleep_calls == [1, 2, 4]


def test_succeeds_after_a_transient_timeout_without_exhausting_retries():
    agent = _agent("resilience-flaky-1", FlakyProvider(hang_seconds=0.3))

    with patch("predicta_harness.resilience.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = asyncio.run(run_with_resilience(agent, "hi", history=[], timeout_s=0.05, max_retries=3))

    assert result.text == "ok"
    assert agent.provider.calls == 2
    assert mock_sleep.await_count == 1


def test_the_last_attempt_raises_instead_of_retrying():
    agent = _agent("resilience-slow-3", SlowProvider(hang_seconds=0.3))

    with patch("predicta_harness.resilience.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(run_with_resilience(agent, "hi", history=[], timeout_s=0.01, max_retries=1))

    mock_sleep.assert_not_awaited()
    assert agent.provider.calls == 1
