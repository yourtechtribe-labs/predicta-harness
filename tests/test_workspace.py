"""RED-first tests for the Workspace (the persistent, traversal-safe agent filesystem)."""

from __future__ import annotations

import os

import pytest

from predicta_harness.sandbox.workspace import Workspace


def test_write_then_read_roundtrip(tmp_path):
    ws = Workspace(tmp_path / "ws")
    n = ws.write_file("notes.txt", "hola")
    assert n == 4  # 4 UTF-8 bytes
    assert ws.read_file("notes.txt") == "hola"


def test_list_files_empty_then_sorted(tmp_path):
    ws = Workspace(tmp_path / "ws")
    assert ws.list_files() == []
    ws.write_file("b.txt", "1")
    ws.write_file("a/c.txt", "2")
    ws.write_file("a.txt", "3")
    # relative paths, sorted, including the nested one
    assert ws.list_files() == ["a.txt", "a/c.txt", "b.txt"]


def test_nested_write_creates_parent_dirs(tmp_path):
    ws = Workspace(tmp_path / "ws")
    ws.write_file("deep/nested/dir/file.txt", "x")
    assert ws.read_file("deep/nested/dir/file.txt") == "x"


def test_reject_parent_traversal(tmp_path):
    ws = Workspace(tmp_path / "ws")
    with pytest.raises(ValueError):
        ws.read_file("../secret")
    with pytest.raises(ValueError):
        ws.write_file("../../escape.txt", "nope")


def test_reject_absolute_path(tmp_path):
    ws = Workspace(tmp_path / "ws")
    abs_path = os.path.abspath(os.sep + "etc")  # platform-correct absolute path
    with pytest.raises(ValueError):
        ws.read_file(abs_path)


def test_read_missing_file_raises_filenotfound(tmp_path):
    ws = Workspace(tmp_path / "ws")
    with pytest.raises(FileNotFoundError):
        ws.read_file("nope.txt")


def test_root_is_created_and_exposed(tmp_path):
    target = tmp_path / "fresh"
    assert not target.exists()
    ws = Workspace(target)
    assert ws.root.is_dir()
    assert ws.root == target.resolve()


@pytest.mark.skipif(
    not hasattr(os, "symlink"), reason="symlinks unavailable"
)
def test_reject_symlink_escape(tmp_path):
    ws = Workspace(tmp_path / "ws")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = ws.root / "link.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlink in this environment")
    with pytest.raises(ValueError):
        ws.read_file("link.txt")  # resolves outside root -> rejected
