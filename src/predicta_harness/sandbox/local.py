"""
local.py — LocalSandbox: run code in a plain subprocess. NO ISOLATION.

This is the simplest backend: `subprocess.run` with the workspace as the working dir.
It is cross-platform and needs zero OS setup, which makes it ideal for (a) learning the
agent loop and (b) running the test suite anywhere. But it is NOT a security boundary —
the executed code runs as your user, with your network and your whole filesystem. Use it
only for code you trust (yourself, a dev box). For untrusted/model-generated code, use
`BubblewrapSandbox`. The two are interchangeable behind the `Sandbox` interface.
"""

from __future__ import annotations

import subprocess
import sys
import time

from .base import Sandbox, as_text
from .types import ExecResult
from .workspace import Workspace


class LocalSandbox(Sandbox):
    def __init__(self, workspace: Workspace, *, python: str = sys.executable) -> None:
        super().__init__(workspace)
        self._python = python

    def run(self, code: str, *, lang: str = "python", timeout: float = 30.0) -> ExecResult:
        if lang != "python":
            raise ValueError(f"LocalSandbox supports lang='python' only, got {lang!r}")
        # -I = isolated mode: ignore env vars and the user site-packages, so the snippet
        # runs in a clean interpreter (closer to what the jailed backend gives).
        argv = [self._python, "-I", "-c", code]
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                cwd=self.workspace.root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ExecResult(
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                exit_code=proc.returncode,
                timed_out=False,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except subprocess.TimeoutExpired as e:
            # The process was killed at the wall-clock limit. Return what it printed so
            # far + the conventional 124 exit code; the agent reads `timed_out` and fixes.
            return ExecResult(
                stdout=as_text(e.stdout),
                stderr=as_text(e.stderr),
                exit_code=124,
                timed_out=True,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
