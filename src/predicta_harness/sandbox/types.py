"""
types.py — value types shared across the sandbox package.

`ExecResult` is the outcome of running code: it is DATA the agent reads, not an
exception. A program that exits non-zero or prints to stderr is normal — the model
inspects stdout/stderr/exit_code and reasons about it. `SandboxError` is reserved for
*infrastructure* failure (e.g. the `bwrap` binary is missing) — that is not the agent's
fault and should surface as a real error, not be fed back as program output.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecResult:
    """The result of executing code in a sandbox.

    A non-zero ``exit_code`` or text on ``stderr`` is NOT an error here — it is the
    program's own output, which the agent reads to debug. ``timed_out`` is set (with
    ``exit_code == 124``, the conventional SIGKILL-by-timeout code) when the wall-clock
    limit was hit and the process was killed.
    """

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    duration_ms: int = 0


class SandboxError(RuntimeError):
    """Raised only on sandbox INFRASTRUCTURE failure (not on program errors).

    Examples: the `bwrap` binary is not installed, or the interpreter path is invalid.
    Program-level failures (exceptions, non-zero exit) are returned as an ``ExecResult``,
    never raised — so the agent loop can read them and retry.
    """
