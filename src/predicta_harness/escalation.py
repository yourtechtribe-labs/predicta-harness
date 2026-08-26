"""A structural escalation gate: intercept a tool before it runs, instead of trusting the
model to "decide correctly" on every turn."""

import logging
from collections.abc import Callable

logger = logging.getLogger("predicta_harness.escalation")


def make_escalation_interceptor(
    notify_human: Callable[[str, str | None], None],
    tool_name: str = "escalate_to_human",
) -> Callable[[str, dict], str | None]:
    """Build a `tool_interceptor` (see `Agent.__init__`) that captures `tool_name` before
    it ever runs.

    The intercepted tool never actually executes: the interceptor calls `notify_human` and
    returns a confirmation string in its place. Any other tool passes through untouched
    (returns `None`) and logs nothing.
    """

    def interceptor(name: str, tool_input: dict) -> str | None:
        if name != tool_name:
            return None
        context_id = tool_input.get("context_id")
        logger.info("escalation_interceptor: intercepted tool=%s context_id=%s", name, context_id)
        notify_human(tool_input["reason"], context_id)
        return "Escalated. A human will review this case."

    return interceptor
