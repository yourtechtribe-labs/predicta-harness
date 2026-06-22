"""service — a tiny HTTP daemon that runs ONE work turn as a sandboxed ReAct loop.

`POST /work {agentKey, goal, workspace, model}` → builds an Agent with sandbox_tools over
the given workspace, runs the loop, and streams each executed tool as an SSE `event: tool`,
then a final `event: done {summary, files}`. This is the bridge a TS office (swarm-office)
calls to make its agents DO real work, not just talk. No new runtime deps (stdlib http.server).
"""

from .app import WorkHandler

__all__ = ["WorkHandler"]
