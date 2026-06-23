"""sandbox — persistent file Workspace + pluggable code-execution Sandbox.

The substrate that lets an agent work on a codebase: a `Workspace` (its persistent,
traversal-safe files) and a `Sandbox` (executes code, with swappable isolation). It plugs
into an Agent purely via `sandbox_tools(workspace, sandbox)` — zero changes to the core loop.

    from predicta_harness import Agent
    from predicta_harness.sandbox import Workspace, LocalSandbox, sandbox_tools

    ws = Workspace("/srv/agent-ws/alice")
    agent = Agent(model="local/qwen", tools=sandbox_tools(ws, LocalSandbox(ws)))

`BubblewrapSandbox` gives real OS isolation (Linux); on a host without `bwrap` its
constructor raises SandboxError, so import it freely and pick the backend at runtime.
"""

from .base import Sandbox
from .bubblewrap import BubblewrapSandbox
from .local import LocalSandbox
from .tools import sandbox_tools
from .types import ExecResult, SandboxError
from .workspace import Workspace

__all__ = [
    "Sandbox", "LocalSandbox", "BubblewrapSandbox", "Workspace",
    "ExecResult", "SandboxError", "sandbox_tools",
]
