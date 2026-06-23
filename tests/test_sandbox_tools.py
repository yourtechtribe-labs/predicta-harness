"""RED-first tests for the sandbox_tools factory (the 4 tools bound to ws+sandbox)."""

from __future__ import annotations

from predicta_harness.sandbox.local import LocalSandbox
from predicta_harness.sandbox.tools import sandbox_tools
from predicta_harness.sandbox.workspace import Workspace


def _tools(tmp_path):
    ws = Workspace(tmp_path / "ws")
    return ws, {t.name: t for t in sandbox_tools(ws, LocalSandbox(ws))}


def test_four_tools_with_expected_names(tmp_path):
    _, tools = _tools(tmp_path)
    assert set(tools) == {"read_file", "write_file", "list_files", "run_code"}


def test_schemas_inferred(tmp_path):
    _, tools = _tools(tmp_path)
    assert tools["read_file"].input_schema["required"] == ["path"]
    wf = tools["write_file"].input_schema
    assert set(wf["properties"]) == {"path", "content"}
    rc = tools["run_code"].input_schema
    assert "code" in rc["properties"]
    assert "timeout" not in rc.get("required", [])  # timeout has a default → optional


def test_write_then_read_through_tools(tmp_path):
    ws, tools = _tools(tmp_path)
    out = tools["write_file"].run({"path": "a.txt", "content": "hola"})
    assert "wrote 4 bytes to a.txt" in out
    assert ws.read_file("a.txt") == "hola"
    assert tools["read_file"].run({"path": "a.txt"}) == "hola"


def test_list_files_tool(tmp_path):
    ws, tools = _tools(tmp_path)
    assert tools["list_files"].run({}) == "(empty)"
    ws.write_file("a.txt", "1")
    assert "a.txt" in tools["list_files"].run({})


def test_run_code_tool_formats_output(tmp_path):
    _, tools = _tools(tmp_path)
    out = tools["run_code"].run({"code": "print(1 + 1)"})
    assert "exit=0" in out and "2" in out
    assert "stdout" in out


def test_run_code_output_truncated(tmp_path):
    _, tools = _tools(tmp_path)
    out = tools["run_code"].run({"code": "print('x' * 50000)"})
    assert "truncated" in out
    assert len(out) < 30000  # bounded, not the full 50k
