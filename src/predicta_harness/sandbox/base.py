"""
base.py — the Sandbox interface (the pluggable isolation boundary).

Only ONE operation crosses the isolation boundary: running code. The file tools are
plain workspace ops (see workspace.py); `run` is where untrusted, model-generated code
actually executes, so it is the thing we make swappable. Today: `local` (no isolation,
to learn the loop) and `bubblewrap` (real, lightweight). Tomorrow a `daytona`/`modal`
backend is just another subclass — nothing else in the harness changes. That pluggability
is the whole point (the same shape Hermes uses with its local/Docker/SSH/Daytona/Modal
backends).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import ExecResult
from .workspace import Workspace


class Sandbox(ABC):
    """Executes code with the workspace as its working directory.

    Implementations differ ONLY in isolation strength; the contract is identical, so an
    Agent (and the `run_code` tool) never needs to know which backend it has.
    """

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    @abstractmethod
    def run(self, code: str, *, lang: str = "python", timeout: float = 30.0) -> ExecResult:
        """Run ``code`` (CWD = the workspace root) and return its ``ExecResult``.

        Contract:
        - A non-zero exit / stderr is NORMAL output, returned in the ExecResult — never
          raised (the agent reads it to debug).
        - On timeout: kill the process, return ``ExecResult(timed_out=True, exit_code=124)``.
        - Raise ``SandboxError`` ONLY on infrastructure failure (e.g. missing `bwrap`).
        - ``lang`` other than the supported one raises ``ValueError``.
        """
        raise NotImplementedError


def as_text(buf: object) -> str:
    """TimeoutExpired carries partial output as str (text mode) or bytes; normalize.

    Shared by the subprocess-based backends (local, bubblewrap) so the normalization
    lives in one place."""
    if buf is None:
        return ""
    if isinstance(buf, bytes):
        return buf.decode("utf-8", "replace")
    return str(buf)
