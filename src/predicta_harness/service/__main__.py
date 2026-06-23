"""Run the work service as a daemon:

    python -m predicta_harness.service --host 127.0.0.1 --port 8088

Sandbox backend via env: PREDICTA_SANDBOX=local (default) | bubblewrap (the VM, real
isolation). The vLLM/model creds are read by the provider from the service's own env
(same OpenAI-compatible config as the examples) — never sent by the caller.
"""

from __future__ import annotations

import argparse
import os
from http.server import ThreadingHTTPServer

from .app import WorkHandler


def main() -> None:
    ap = argparse.ArgumentParser(prog="predicta_harness.service")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    args = ap.parse_args()

    backend = os.environ.get("PREDICTA_SANDBOX", "local")
    server = ThreadingHTTPServer((args.host, args.port), WorkHandler)
    print(f"[predicta-harness] work service on http://{args.host}:{args.port}  (sandbox={backend})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[predicta-harness] shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
