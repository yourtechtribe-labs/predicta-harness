"""
predicta-harness — A provider-agnostic agent harness for Python.

The Claude Code / Flue pattern (agent loop + tools + sessions), but in Python and
not tied to a single model provider. The same agent runs over Claude, OpenAI or a
local LLM (any OpenAI-compatible endpoint).

    from predicta_harness import Agent, tool

    @tool
    def add(a: int, b: int) -> str:
        "Add two numbers."
        return str(a + b)

    agent = Agent(model="anthropic/claude-sonnet-4-6", tools=[add],
                  system="You are a calculation assistant.")
    print(agent.run("what is 21 + 21?").text)
"""

from .agent import Agent
from .tool import Tool, tool
from .providers.base import Provider, register_provider, resolve
from .types import RunResult, Usage, ToolCall
from .sandbox import (
    Sandbox, LocalSandbox, Workspace, ExecResult, SandboxError, sandbox_tools,
)

__version__ = "0.1.0"
__all__ = [
    "Agent", "tool", "Tool",
    "Provider", "register_provider", "resolve",
    "RunResult", "Usage", "ToolCall",
    # sandbox substrate (code execution + persistent files)
    "Sandbox", "LocalSandbox", "Workspace", "ExecResult", "SandboxError", "sandbox_tools",
]
