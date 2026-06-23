"""F6 — read-only /files and /file endpoints over a workspace (no LLM, no bwrap)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from predicta_harness.sandbox import Workspace
from predicta_harness.service.app import WorkHandler


def _serve() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _get(port: int, path: str) -> str:
    return urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5).read().decode()


def _q(p) -> str:
    return urllib.parse.quote(str(p))


def test_files_lists_and_file_reads(tmp_path):
    ws = Workspace(tmp_path / "zone")
    ws.write_file("a.md", "# hola")
    ws.write_file("sub/b.py", "print(1)")
    server = _serve()
    port = server.server_address[1]
    try:
        listed = json.loads(_get(port, f"/files?workspace={_q(ws.root)}"))
        assert set(listed["files"]) == {"a.md", "sub/b.py"}  # POSIX, sorted
        one = json.loads(_get(port, f"/file?workspace={_q(ws.root)}&path=a.md"))
        assert one["content"] == "# hola"
        assert one["truncated"] is False
    finally:
        server.shutdown()


def test_file_missing_returns_404(tmp_path):
    ws = Workspace(tmp_path / "zone")
    ws.write_file("a.md", "x")
    server = _serve()
    port = server.server_address[1]
    try:
        try:
            _get(port, f"/file?workspace={_q(ws.root)}&path=missing.md")
            raise AssertionError("expected HTTPError 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
            assert "error" in json.loads(e.read().decode())
    finally:
        server.shutdown()


def test_file_traversal_returns_400(tmp_path):
    ws = Workspace(tmp_path / "zone")
    ws.write_file("a.md", "x")
    server = _serve()
    port = server.server_address[1]
    try:
        try:
            _get(port, f"/file?workspace={_q(ws.root)}&path=../../etc/passwd")
            raise AssertionError("expected HTTPError 400 (traversal rejected)")
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        server.shutdown()


def test_file_clips_large_content(tmp_path):
    ws = Workspace(tmp_path / "zone")
    ws.write_file("big.txt", "x" * 200_000)
    server = _serve()
    port = server.server_address[1]
    try:
        one = json.loads(_get(port, f"/file?workspace={_q(ws.root)}&path=big.txt"))
        assert one["truncated"] is True
        assert len(one["content"]) == 100_000  # WS_VIEW_MAX
    finally:
        server.shutdown()
