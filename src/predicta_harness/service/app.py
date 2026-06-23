"""
app.py — the /work request handler (SSE).

Runs ONE work turn: build a sandboxed agent over the requested workspace, run the ReAct
loop, and STREAM each executed sandbox tool as it happens (`on_tool` → SSE), so the caller
(the office) can show live progress in its server-log. The sandbox backend is chosen by env
(`PREDICTA_SANDBOX=local|bubblewrap`) — `local` anywhere (dev/tests), `bubblewrap` on the VM
for real isolation. The agent runs untrusted, model-generated code, but only ever inside the
sandbox; the HTTP layer just marshals goal → loop → events.
"""

from __future__ import annotations

import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler

from ..agent import Agent
from ..sandbox import BubblewrapSandbox, LocalSandbox, Sandbox, Workspace, sandbox_tools

WORK_SYSTEM = (
    "You are a coding teammate working in a shared sandbox workspace. Use write_file to "
    "create files and run_code to execute Python. Accomplish the goal with real, tested "
    "code — never invent results; run code to verify them. Keep going until the goal is done."
)
# Per-tool output is hard-clipped to this many chars on the SSE wire: it's a live PROGRESS
# preview, not the full result (the model already saw the full output inside its loop).
_SSE_PREVIEW = 2000


def _make_sandbox(ws: Workspace) -> Sandbox:
    """local anywhere; bubblewrap (real isolation) when PREDICTA_SANDBOX=bubblewrap (the VM)."""
    if os.environ.get("PREDICTA_SANDBOX", "local").lower() == "bubblewrap":
        return BubblewrapSandbox(ws)
    return LocalSandbox(ws)


class WorkHandler(BaseHTTPRequestHandler):
    # Quiet: the office logs the work; we don't need stderr access logs.
    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/healthz":
            try:
                # Constructing the configured sandbox confirms readiness (e.g. bwrap present).
                _make_sandbox(Workspace(os.path.join(tempfile.gettempdir(), "predicta-healthz")))
                self._text(200, "ok")
            except Exception as e:  # pragma: no cover - infra
                self._text(503, f"sandbox not ready: {e}")
        else:
            self._text(404, "not found")

    def do_POST(self) -> None:
        if self.path != "/work":
            self._text(404, "not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")

        # Open the SSE stream up front, then push events as the loop runs.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        try:
            ws = Workspace(body["workspace"])
            agent = Agent(
                model=body["model"],
                system=WORK_SYSTEM,
                tools=sandbox_tools(ws, _make_sandbox(ws)),
                max_steps=int(body.get("maxSteps", 12)),
                # Work writes CODE into tool-call arguments (a JSON string). 2048 truncates a
                # real file → unterminated JSON → the provider can't parse it. Give it room.
                max_tokens=int(os.environ.get("WORK_MAX_TOKENS", "8192")),
                # Fires inside the ReAct loop → each executed sandbox tool streams live.
                on_tool=lambda n, i, o: self._sse("tool", {"name": n, "input": i, "output": o[:_SSE_PREVIEW]}),
            )
            result = agent.run(
                body["goal"],
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},  # vLLM/Qwen: no CoT
            )
            self._sse("done", {
                "summary": result.text,
                "files": ws.list_files(),
                "steps": result.steps,
                "usage": str(result.usage),
            })
        except Exception as e:
            self._sse("error", {"message": f"{type(e).__name__}: {e}"})

    def _sse(self, event: str, data: dict) -> None:
        try:
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            # The client (office) hung up mid-stream. The work still ran server-side; we
            # just can't stream the rest. Swallow it instead of a noisy traceback.
            pass

    def _text(self, code: int, msg: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(msg.encode("utf-8"))
