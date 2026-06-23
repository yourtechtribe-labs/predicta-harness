"""
tools.py — sandbox_tools(): the 4 tools an Agent gets, bound to a workspace + sandbox.

`@tool` only decorates module-level functions, but we need each tool to close over a
specific (workspace, sandbox) pair. So the factory defines inner functions and wraps each
with `Tool.from_function`, which infers the JSON Schema from the closure's type hints and
uses its docstring as the description — the same path `@tool` uses.

Error handling is deliberately absent here: the Workspace raises `ValueError` /
`FileNotFoundError`, and the Agent's `_dispatch` already wraps every `tool.run` in a
try/except that feeds the message back to the model. Duplicating that would just hide the
detail the model needs to recover.
"""

from __future__ import annotations

from ..tool import Tool
from .base import Sandbox
from .types import ExecResult
from .workspace import Workspace

# Per-stream cap (chars) on what run_code returns, so a noisy program can't blow the
# model's context / token budget (SPEC R4).
_MAX_STREAM = 10_000


def _trunc(s: str) -> str:
    if len(s) <= _MAX_STREAM:
        return s
    return s[:_MAX_STREAM] + f"\n…[truncated {len(s) - _MAX_STREAM} chars]"


def _format(r: ExecResult) -> str:
    flag = " (timed out)" if r.timed_out else ""
    return (
        f"exit={r.exit_code}{flag}\n"
        f"--- stdout ---\n{_trunc(r.stdout)}\n"
        f"--- stderr ---\n{_trunc(r.stderr)}"
    )


def sandbox_tools(workspace: Workspace, sandbox: Sandbox) -> list[Tool]:
    """Build the read_file/write_file/list_files/run_code tools for `Agent(tools=...)`."""

    def read_file(path: str) -> str:
        "Read a UTF-8 text file from the workspace. `path` is relative to the workspace root."
        return workspace.read_file(path)

    def write_file(path: str, content: str) -> str:
        "Create or overwrite a text file in the workspace (parent dirs are auto-created)."
        n = workspace.write_file(path, content)
        return f"wrote {n} bytes to {path}"

    def list_files(subdir: str = ".") -> str:
        "List the files in the workspace as relative paths."
        names = workspace.list_files(subdir)
        return "\n".join(names) if names else "(empty)"

    def edit_file(path: str, old: str, new: str) -> str:
        "Edit a file in place by replacing text: every occurrence of `old` becomes `new`. "
        "Prefer this over rewriting a whole file (and over writing throwaway scripts to patch "
        "it): to INSERT, replace an anchor line with itself + the new content. `old` must match "
        "exactly. Errors if the file is missing or `old` is not found, so you can adjust."
        content = workspace.read_file(path)
        if old not in content:
            return f"el texto a reemplazar no se encontró en {path} (debe coincidir EXACTAMENTE, incluidos espacios/saltos)"
        n = content.count(old)
        workspace.write_file(path, content.replace(old, new))
        return f"editado {path}: {n} reemplazo(s)"

    def run_code(code: str, timeout: float = 30.0) -> str:
        "Execute Python code in the sandbox, with the workspace as the working directory. "
        "Returns the exit code, stdout and stderr. Files you wrote with write_file are visible here."
        return _format(sandbox.run(code, lang="python", timeout=timeout))

    return [Tool.from_function(f) for f in (read_file, write_file, edit_file, list_files, run_code)]
