from unittest.mock import MagicMock

from predicta_harness.agent import Agent
from predicta_harness.escalation import make_escalation_interceptor
from predicta_harness.providers.base import register_provider
from predicta_harness.tool import Tool

from _mock_provider import ScriptedProvider


# --- unit tests: the interceptor factory on its own ---


def test_intercepts_the_configured_tool_and_never_lets_it_execute():
    notify_human = MagicMock()
    interceptor = make_escalation_interceptor(notify_human, tool_name="escalate_to_human")

    result = interceptor("escalate_to_human", {"reason": "asks for a concrete number"})

    assert result is not None
    assert result == "Escalated. A human will review this case."


def test_calls_notify_human_with_reason_and_context_id():
    notify_human = MagicMock()
    interceptor = make_escalation_interceptor(notify_human, tool_name="escalate_to_human")

    interceptor("escalate_to_human", {"reason": "pricing question", "context_id": "conv-123"})

    notify_human.assert_called_once_with("pricing question", "conv-123")


def test_a_different_tool_passes_through_without_intercepting():
    notify_human = MagicMock()
    interceptor = make_escalation_interceptor(notify_human, tool_name="escalate_to_human")

    result = interceptor("send_message", {"text": "hi"})

    assert result is None
    notify_human.assert_not_called()


def test_logs_an_info_event_when_it_intercepts(caplog):
    notify_human = MagicMock()
    interceptor = make_escalation_interceptor(notify_human, tool_name="escalate_to_human")

    with caplog.at_level("INFO", logger="predicta_harness.escalation"):
        interceptor("escalate_to_human", {"reason": "pricing question", "context_id": "conv-123"})

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "INFO"
    assert "conv-123" in caplog.records[0].message


# --- integration: a real Agent, driven by a scripted provider, actually calling the tool ---


def test_a_real_agent_never_executes_the_tool_when_the_model_calls_it():
    tool_ran = MagicMock()

    def escalate_to_human(reason: str) -> str:
        """Escalate this conversation to a human."""
        tool_ran()
        return "should never run"

    notify_human = MagicMock()
    interceptor = make_escalation_interceptor(notify_human, tool_name="escalate_to_human")

    register_provider("escalation-scripted-1", ScriptedProvider([
        ("tool", "call-1", "escalate_to_human", {"reason": "asks for a discount"}),
        ("text", "handled"),
    ]))
    agent = Agent(
        model="escalation-scripted-1/test-model",
        tools=[Tool.from_function(escalate_to_human)],
        tool_interceptor=interceptor,
    )

    result = agent.run("can I get 20% off?")

    tool_ran.assert_not_called()
    notify_human.assert_called_once_with("asks for a discount", None)
    assert result.text == "handled"
