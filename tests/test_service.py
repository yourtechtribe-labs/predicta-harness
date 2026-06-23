"""HW1/HW2 — the harness /work HTTP service (SSE). Driven by a scripted provider +
LocalSandbox, so it runs anywhere with no live LLM and no bwrap."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from _mock_provider import ScriptedProvider

from predicta_harness.providers.base import register_provider
from predicta_harness.service.app import WorkHandler


def _parse_sse(raw: str) -> list[tuple[str | None, dict | None]]:
    events = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        ev = data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        events.append((ev, data))
    return events


def _serve() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _post(port: int, path: str, body: dict) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=15).read().decode()


def test_work_streams_tools_then_done_and_writes_file(tmp_path):
    register_provider("svc", ScriptedProvider([
        ("tool", "t1", "write_file", {"path": "out.txt", "content": "hi"}),
        ("tool", "t2", "run_code", {"code": "print(open('out.txt').read().strip())"}),
        ("text", "Created out.txt and verified it reads 'hi'."),
    ]))
    server = _serve()
    port = server.server_address[1]
    try:
        raw = _post(port, "/work", {
            "agentKey": "npc:seneca", "goal": "write hi to out.txt",
            "workspace": str(tmp_path / "zone"), "model": "svc/x",
        })
    finally:
        server.shutdown()

    events = _parse_sse(raw)
    kinds = [e[0] for e in events]
    assert "tool" in kinds, kinds
    assert kinds[-1] == "done", kinds
    # the tool events streamed the ACTUAL sandbox calls, in order
    assert [e[1]["name"] for e in events if e[0] == "tool"] == ["write_file", "run_code"]
    done = events[-1][1]
    assert "out.txt" in done["files"]          # the artifact persisted in the workspace
    assert "verified" in done["summary"].lower()


def test_healthz():
    server = _serve()
    port = server.server_address[1]
    try:
        code = urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5).getcode()
    finally:
        server.shutdown()
    assert code == 200
