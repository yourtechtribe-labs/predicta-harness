"""
quickstart.py — The SAME agent and the SAME tool running over Claude (Anthropic)
and over a local model (Ollama, OpenAI-compatible). Only the model string changes.
That is the harness differentiator: provider-agnostic.

Run:
    ANTHROPIC_API_KEY=sk-... PYTHONPATH=src python examples/quickstart.py
    # optional, to also try a local model:
    #   ollama serve   (and `ollama pull llama3.1:8b`), then set RUN_LOCAL=1
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows console (cp1252) -> utf-8

from predicta_harness import Agent, tool, register_provider
from predicta_harness.providers.openai import OpenAIProvider


@tool
def get_balance(account: str) -> str:
    """Returns the current balance of an account by name (SAVINGS or CHECKING)."""
    balances = {"SAVINGS": "12,450.30 EUR", "CHECKING": "2,103.75 EUR"}
    return balances.get(account.upper(), f"account '{account}' not found")


SYSTEM = (
    "You are a banking assistant. When asked about a balance, call the get_balance "
    "tool to fetch the real value; never make up figures."
)


def run_agent(model: str) -> None:
    agent = Agent(
        model=model,
        system=SYSTEM,
        tools=[get_balance],
        on_tool=lambda n, i, o: print(f"   [tool] {n}({i}) -> {o}"),
    )
    result = agent.run("How much do I currently have in my savings account?")
    print(f"   ANSWER: {result.text}")
    print(f"   USAGE:  {result.usage}  ({result.steps} steps)")


if __name__ == "__main__":
    print("== Anthropic (claude-sonnet-4-6) ==")
    run_agent("anthropic/claude-sonnet-4-6")

    # Same agent, local model. Point an OpenAI-compatible provider at any endpoint
    # (Ollama, vLLM, LM Studio, DeepSeek, OpenRouter...). Set LOCAL_LLM_BASE_URL to try it.
    local_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    local_model = os.environ.get("LOCAL_LLM_MODEL", "llama3.1:8b")
    if os.environ.get("RUN_LOCAL"):
        register_provider("local", OpenAIProvider(base_url=local_url, api_key="ollama"))
        print(f"\n== Local ({local_model} @ {local_url}) ==")
        run_agent(f"local/{local_model}")
