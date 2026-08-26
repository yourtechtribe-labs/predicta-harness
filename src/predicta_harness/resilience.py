"""A hard timeout and exponential backoff around `Agent.run()`.

`Agent.run()` is synchronous — it is dispatched to a thread (`asyncio.to_thread`) so the
caller's event loop keeps running while a model call is in flight. If the provider hangs,
that thread can stay alive in the background, but this coroutine never waits past
`timeout_s` on any single attempt.
"""

import asyncio
import logging

logger = logging.getLogger("predicta_harness.resilience")


async def run_with_resilience(agent, message, history, *, timeout_s: float = 25, max_retries: int = 3):
    """Run `agent.run()` with a hard per-attempt timeout and exponential backoff.

    Backoff between retries: 1s, 2s, 4s, ... (`2**attempt`). The last attempt does not
    wait — if it also times out, the exception is re-raised as-is.

    Logs a `WARNING` on each timeout that triggers a retry, and an `ERROR` when retries
    are exhausted — nothing is logged on a call that succeeds.
    """
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(agent.run, message, history=history),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            if attempt == max_retries - 1:
                logger.error("run_with_resilience: exhausted %d attempts, re-raising the timeout", max_retries)
                raise
            backoff_s = 2**attempt
            logger.warning(
                "run_with_resilience: timeout on attempt %d/%d, retrying in %ds",
                attempt + 1,
                max_retries,
                backoff_s,
            )
            await asyncio.sleep(backoff_s)
