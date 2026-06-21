"""
predicta-harness — A provider-agnostic agent harness for Python.

El patrón de Claude Code / Flue (agent loop + tools + sesiones), pero en Python
y sin atarte a un proveedor de modelo. Mismo agente sobre Claude, OpenAI o un
LLM local (OpenAI-compatible).

    from predicta_harness import Agent, tool

    @tool
    def add(a: int, b: int) -> str:
        "Suma dos números."
        return str(a + b)

    agent = Agent(model="anthropic/claude-sonnet-4-6", tools=[add],
                  system="Eres un asistente de cálculo.")
    print(agent.run("cuánto es 21 + 21?").text)
"""

from .agent import Agent
from .tool import Tool, tool
from .providers.base import Provider, register_provider, resolve
from .types import RunResult, Usage, ToolCall

__version__ = "0.1.0"
__all__ = [
    "Agent", "tool", "Tool",
    "Provider", "register_provider", "resolve",
    "RunResult", "Usage", "ToolCall",
]
