"""Isolation tests for BubblewrapSandbox. Skipped where `bwrap` is absent (e.g. Windows);
run on Linux (dev-instance) to verify the jail for real."""

from __future__ import annotations

import shutil

import pytest

from predicta_harness.sandbox.bubblewrap import BubblewrapSandbox
from predicta_harness.sandbox.types import SandboxError
from predicta_harness.sandbox.workspace import Workspace

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None, reason="bubblewrap not installed (Linux-only jail)"
)


def _sb(tmp_path):
    return BubblewrapSandbox(Workspace(tmp_path / "ws"))


def test_runs_and_reads_workspace_file(tmp_path):
    ws = Workspace(tmp_path / "ws")
    ws.write_file("data.txt", "3\n5\n8\n")
    r = BubblewrapSandbox(ws).run("print(sum(int(x) for x in open('data.txt')))")
    assert r.exit_code == 0
    assert r.stdout.strip() == "16"


def test_no_network(tmp_path):
    code = (
        "import socket\n"
        "try: socket.create_connection(('8.8.8.8', 53), 2); print('OPEN')\n"
        "except Exception: print('BLOCKED')"
    )
    assert "BLOCKED" in _sb(tmp_path).run(code).stdout


def test_no_host_filesystem(tmp_path):
    code = (
        "try: open('/etc/passwd'); print('OPEN')\n"
        "except Exception: print('BLOCKED')"
    )
    assert "BLOCKED" in _sb(tmp_path).run(code).stdout


def test_writes_persist_to_workspace(tmp_path):
    ws = Workspace(tmp_path / "ws")
    BubblewrapSandbox(ws).run("open('out.txt', 'w').write('hi')")
    assert ws.read_file("out.txt") == "hi"  # write inside the jail reached the host workspace


def test_timeout(tmp_path):
    r = _sb(tmp_path).run("while True: pass", timeout=1.0)
    assert r.timed_out is True
    assert r.exit_code == 124


def test_missing_bwrap_raises(tmp_path):
    with pytest.raises(SandboxError):
        BubblewrapSandbox(Workspace(tmp_path / "ws"), bwrap="definitely-not-bwrap-xyz")
