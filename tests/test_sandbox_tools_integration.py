"""AC1 — the Agent loop drives the sandbox tools end-to-end (no live LLM).

Proves the substrate plugs into the real loop: a scripted model writes a file, then runs
code that reads it, and the executed code actually computes the sum. Also covers the two
hooks: on_tool (audit) and tool_interceptor (human gate blocking run_code).
"""

from __future__ import annotations

from _mock_provider import ScriptedProvider

from predicta_harness import Agent, register_provider
from predicta_harness.sandbox.local import LocalSandbox
from predicta_harness.sandbox.tools import sandbox_tools
from predicta_harness.sandbox.workspace import Workspace

SUM_CODE = "print(sum(int(x) for x in open('data.txt')))"


def test_ac1_write_then_run_reaches_the_sum(tmp_path):
    ws = Workspace(tmp_path / "ws")
    register_provider("mockac1", ScriptedProvider([
        ("tool", "t1", "write_file", {"path": "data.txt", "content": "3\n5\n8\n"}),
        ("tool", "t2", "run_code", {"code": SUM_CODE}),
        ("text", "The numbers sum to 16."),
    ]))
    seen: list[tuple[str, str]] = []
    agent = Agent(
        model="mockac1/x", system="", tools=sandbox_tools(ws, LocalSandbox(ws)),
        on_tool=lambda n, i, o: seen.append((n, o)),
    )
    r = agent.run("sum the numbers in data.txt")

    # the file was written (persists in the workspace) ...
    assert ws.read_file("data.txt").strip() == "3\n5\n8"
    # ... and the code that ran actually saw it and produced the sum (AC1) ...
    run_outputs = [o for n, o in seen if n == "run_code"]
    assert run_outputs and "16" in run_outputs[0]
    # ... and the loop ended with the model's final text.
    assert r.text == "The numbers sum to 16."
    assert r.steps == 3


def test_tool_interceptor_blocks_run_code(tmp_path):
    ws = Workspace(tmp_path / "ws")
    register_provider("mockgate", ScriptedProvider([
        ("tool", "t1", "run_code", {"code": "open('ran.flag', 'w').write('x')"}),
        ("text", "done"),
    ]))

    def gate(name: str, inputs: dict) -> str | None:
        return "[blocked: run_code needs human approval]" if name == "run_code" else None

    agent = Agent(
        model="mockgate/x", tools=sandbox_tools(ws, LocalSandbox(ws)), tool_interceptor=gate,
    )
    r = agent.run("write a flag file")

    # the interceptor returned a string → the tool NEVER executed → no side effect.
    assert not (ws.root / "ran.flag").exists()
    assert r.text == "done"
