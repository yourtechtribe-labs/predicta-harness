"""
bubblewrap.py — BubblewrapSandbox: real OS isolation, lightweight, no root.

Runs the agent's code inside a `bwrap` jail (Linux namespaces). Unlike LocalSandbox this
IS a security boundary: the code gets no network, no host filesystem (only the workspace),
a clean environment, and is killed at a wall-clock timeout. `bwrap` is a ~50 KB binary
(the one Flatpak — and Anthropic's own sandbox runtime — use); it needs no daemon and runs
unprivileged, which is why it's far lighter than Docker for the same real isolation.

THE JAIL (argv validated empirically on the target before this was written):
  --unshare-all  → new net/pid/ipc/uts/cgroup/user namespaces ⇒ NO NETWORK.
  --ro-bind /usr (+ try /bin,/sbin,/lib,/lib64) → just enough to run a system python,
    read-only ⇒ the code cannot modify the host system.
  --bind <workspace> /workspace --chdir /workspace → the ONLY writable path; writes here
    persist to the host workspace dir (that's the agent's codebase).
  --clearenv → no host secrets leak into the child.
Anything NOT bound (e.g. /etc, /home) simply does not exist inside the jail, so reading a
host path fails with FileNotFoundError — proven by the no-host-fs probe in the tests.
"""

from __future__ import annotations

import shutil
import subprocess
import time

from .base import Sandbox, as_text
from .types import ExecResult, SandboxError
from .workspace import Workspace

# Mounted read-only so a system python can run; the code can read but never modify them.
_RO_BIND_TRY = ("/bin", "/sbin", "/lib", "/lib64")


class BubblewrapSandbox(Sandbox):
    def __init__(
        self, workspace: Workspace, *, python: str = "/usr/bin/python3", bwrap: str = "bwrap"
    ) -> None:
        super().__init__(workspace)
        resolved = shutil.which(bwrap)
        if resolved is None:
            raise SandboxError(
                f"bubblewrap binary not found ({bwrap!r}). Install it "
                f"(e.g. `apt-get install -y bubblewrap`) or use LocalSandbox."
            )
        self._bwrap = resolved
        self._python = python

    def _argv(self, code: str) -> list[str]:
        argv = [
            self._bwrap,
            "--unshare-all", "--die-with-parent", "--new-session",
            "--ro-bind", "/usr", "/usr",
        ]
        for path in _RO_BIND_TRY:
            argv += ["--ro-bind-try", path, path]
        argv += [
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--bind", str(self.workspace.root), "/workspace", "--chdir", "/workspace",
            "--clearenv", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/workspace",
            # Code is passed as an argv element (subprocess list form, no shell) → no quoting risk.
            self._python, "-I", "-c", code,
        ]
        return argv

    def run(self, code: str, *, lang: str = "python", timeout: float = 30.0) -> ExecResult:
        if lang != "python":
            raise ValueError(f"BubblewrapSandbox supports lang='python' only, got {lang!r}")
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                self._argv(code), capture_output=True, text=True, timeout=timeout
            )
            return ExecResult(
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                exit_code=proc.returncode,
                timed_out=False,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except subprocess.TimeoutExpired as e:
            # Killing the bwrap process tears down the whole jail (--die-with-parent).
            return ExecResult(
                stdout=as_text(e.stdout),
                stderr=as_text(e.stderr),
                exit_code=124,
                timed_out=True,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
