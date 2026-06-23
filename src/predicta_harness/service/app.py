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
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

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
# Max chars served by GET /file (the explorer viewer): bound the payload so a huge file
# can't freeze the UI / blow the wire. Over this, content is clipped + truncated=true (F6).
WS_VIEW_MAX = 100_000


def _today_madrid() -> str:
    """Real current date in Europe/Madrid (the team's timezone). LLMs invent dates from their
    training cutoff, so we inject the real one. zoneinfo needs OS tzdata (Linux has it); on a
    Windows dev box without it we fall back to the local clock (which is Madrid here)."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Madrid"))
    except Exception:
        now = datetime.now()
    return now.strftime("%Y-%m-%d (%A)")


def _work_system() -> str:
    """The work system prompt + the REAL current date, so documents are dated correctly."""
    return (
        f"{WORK_SYSTEM}\n\n"
        f"Contexto temporal: hoy es {_today_madrid()}, zona horaria Europe/Madrid. "
        f"Usa SIEMPRE esta fecha real en cualquier documento o versión; nunca inventes fechas."
    )


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
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            try:
                # Constructing the configured sandbox confirms readiness (e.g. bwrap present).
                _make_sandbox(Workspace(os.path.join(tempfile.gettempdir(), "predicta-healthz")))
                self._text(200, "ok")
            except Exception as e:  # pragma: no cover - infra
                self._text(503, f"sandbox not ready: {e}")
        elif parsed.path == "/files":
            self._files(parse_qs(parsed.query))
        elif parsed.path == "/file":
            self._file(parse_qs(parsed.query))
        else:
            self._text(404, "not found")

    # ── F6: read-only workspace browsing (the office proxies these for the explorer) ──
    def _files(self, qs: dict) -> None:
        """List the files in a workspace. Hides generated noise (__pycache__/*.pyc) from the
        explorer view — they're build artifacts, not the agents' work. Any failure → 400."""
        try:
            ws = Workspace(qs["workspace"][0])
            files = [f for f in ws.list_files() if "__pycache__" not in f and not f.endswith(".pyc")]
            self._json(200, {"files": files})
        except Exception as e:
            self._json(400, {"error": f"{type(e).__name__}: {e}"})

    def _file(self, qs: dict) -> None:
        """Read ONE file's text, clipped to WS_VIEW_MAX. Routes through Workspace, so a
        traversal/absolute path raises ValueError (→400) and a missing file raises
        FileNotFoundError (→404) — the agent's jail is reused as the endpoint's guard."""
        try:
            ws = Workspace(qs["workspace"][0])
            rel = qs["path"][0]
            text = ws.read_file(rel)
        except FileNotFoundError:
            self._json(404, {"error": f"not found: {qs.get('path', ['?'])[0]}"})
            return
        except Exception as e:  # ValueError (traversal), KeyError (missing param), UnicodeDecodeError…
            self._json(400, {"error": f"{type(e).__name__}: {e}"})
            return
        self._json(200, {"path": rel, "content": text[:WS_VIEW_MAX], "truncated": len(text) > WS_VIEW_MAX})

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
                system=_work_system(),  # WORK_SYSTEM + the real Madrid date (no invented dates)
                tools=sandbox_tools(ws, _make_sandbox(ws)),
                # Real work (e.g. drafting + editing a multi-section report) takes many
                # read/write/run iterations; 12 ran out mid-task. Env-tunable.
                max_steps=int(body.get("maxSteps") or os.environ.get("WORK_MAX_STEPS", "25")),
                # Work writes CODE/docs into tool-call arguments (a JSON string). Too low
                # truncates a real file → unparseable JSON. Generous default; env-tunable. If
                # it still truncates, the provider's parse_error tells the model to split it.
                max_tokens=int(os.environ.get("WORK_MAX_TOKENS", "16384")),
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
                "stop_reason": result.stop_reason,  # "end_turn" | "max_steps" (structured)
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
