"""
sandbox_agent.py — an agent that works on a real codebase.

It writes a file, runs Python that reads it, and feeds the result back into its reasoning
— the "work on a project" substrate. By DEFAULT it runs OFFLINE with a tiny scripted model
(no API key needed), so the loop + the sandbox tools are visible deterministically. Set a
real model to let the LLM drive the same tools itself.

Run:
    PYTHONPATH=src python examples/sandbox_agent.py            # offline (scripted model)
    ANTHROPIC_API_KEY=sk-... PYTHONPATH=src python examples/sandbox_agent.py   # real LLM

On Linux, swap LocalSandbox -> BubblewrapSandbox(ws) below for REAL isolation (no network,
no host filesystem). LocalSandbox has no isolation — fine for trusted/demo use.
"""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")  # Windows console (cp1252) -> utf-8

from predicta_harness import Agent, LocalSandbox, Workspace, register_provider, sandbox_tools
from predicta_harness.providers.base import Provider
from predicta_harness.types import AssistantTurn, ToolCall, Usage

SUM_CODE = "print(sum(int(x) for x in open('data.txt')))"

SYSTEM = (
    "You are a coding teammate working in a sandbox workspace. Use write_file to create "
    "files and run_code to execute Python. Never invent results — run code to get them."
)


class _ScriptedModel(Provider):
    """A fake model that performs the write->run->answer flow, so the demo runs with no
    API key. A real provider would decide these tool calls on its own."""

    def __init__(self, turns: list[tuple]) -> None:
        self._turns = turns
        self.calls = 0

    def complete(self, *, model_id, system, messages, tools, max_tokens=2048, **kw):
        spec = self._turns[min(self.calls, len(self._turns) - 1)]
        self.calls += 1
        usage = Usage(model=model_id, calls=1)
        if spec[0] == "tool":
            _, tid, name, inp = spec
            return AssistantTurn(
                "", [ToolCall(tid, name, inp)],
                [{"type": "tool_use", "id": tid, "name": name, "input": inp}],
                usage, "tool_use",
            )
        return AssistantTurn(spec[1], [], [{"type": "text", "text": spec[1]}], usage, "end_turn")


def _short(x, n: int = 90) -> str:
    s = str(x).replace("\n", "\\n")
    return s if len(s) <= n else s[:n] + "…"


def main() -> None:
    ws = Workspace(os.path.join(tempfile.gettempdir(), "predicta-agent-ws"))
    sandbox = LocalSandbox(ws)                 # Linux: BubblewrapSandbox(ws) for real isolation
    tools = sandbox_tools(ws, sandbox)

    if os.environ.get("ANTHROPIC_API_KEY"):
        model = "anthropic/claude-sonnet-4-6"
    else:
        register_provider("demo", _ScriptedModel([
            ("tool", "t1", "write_file", {"path": "data.txt", "content": "3\n5\n8\n"}),
            ("tool", "t2", "run_code", {"code": SUM_CODE}),
            ("text", "The numbers in data.txt (3, 5, 8) sum to 16."),
        ]))
        model = "demo/scripted"
        print("(no ANTHROPIC_API_KEY -> scripted model; set the key to drive it with a real LLM)\n")

    agent = Agent(
        model=model, system=SYSTEM, tools=tools,
        on_tool=lambda n, i, o: print(f"   [tool] {n}({_short(i)}) -> {_short(o)}"),
    )
    result = agent.run(
        "Create data.txt with the numbers 3, 5 and 8 (one per line), then compute their sum with Python."
    )

    print(f"\n   ANSWER: {result.text}")
    print(f"   FILES:  {ws.list_files()}        (persisted in {ws.root})")
    print(f"   USAGE:  {result.usage} ({result.steps} steps)")


if __name__ == "__main__":
    main()
