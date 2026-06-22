"""RED-first tests for LocalSandbox (subprocess executor, no isolation)."""

from __future__ import annotations

import pytest

from predicta_harness.sandbox.local import LocalSandbox
from predicta_harness.sandbox.workspace import Workspace


def _sb(tmp_path):
    return LocalSandbox(Workspace(tmp_path / "ws"))


def test_stdout_captured(tmp_path):
    r = _sb(tmp_path).run("print('hi')")
    assert r.exit_code == 0
    assert r.stdout.strip() == "hi"
    assert r.timed_out is False


def test_nonzero_exit_is_returned_not_raised(tmp_path):
    r = _sb(tmp_path).run("import sys; sys.exit(3)")
    assert r.exit_code == 3  # normal output, no exception


def test_traceback_on_stderr(tmp_path):
    r = _sb(tmp_path).run("raise ValueError('boom')")
    assert r.exit_code != 0
    assert "ValueError" in r.stderr and "boom" in r.stderr


def test_cwd_is_workspace(tmp_path):
    ws = Workspace(tmp_path / "ws")
    ws.write_file("data.txt", "3\n5\n8\n")
    r = LocalSandbox(ws).run(
        "print(sum(int(x) for x in open('data.txt')))"
    )
    assert r.stdout.strip() == "16"  # the file written via Workspace is visible to run()


def test_timeout(tmp_path):
    r = _sb(tmp_path).run("while True: pass", timeout=1.0)
    assert r.timed_out is True
    assert r.exit_code == 124


def test_unsupported_lang_raises(tmp_path):
    with pytest.raises(ValueError):
        _sb(tmp_path).run("echo hi", lang="bash")
