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


def _register_providers() -> str | None:
    """Register an OpenAI-compatible provider from env so the office can drive work with a
    REAL model (e.g. the vLLM). Mirrors the example's OPENAI_COMPAT_* config; the provider
    id (default 'vllm') is the prefix the office's WORK_MODEL uses ("vllm/<model>"). Returns
    the registered id, or None if no endpoint is configured (then only built-in providers
    or a per-request-registered one work)."""
    base = os.environ.get("OPENAI_COMPAT_BASE_URL")
    if not base:
        return None
    import httpx

    from ..providers.base import register_provider
    from ..providers.openai import OpenAIProvider

    ckw = {}
    if os.environ.get("OPENAI_COMPAT_INSECURE_TLS", "").lower() == "true":
        ckw["http_client"] = httpx.Client(verify=False)
    pid = os.environ.get("OPENAI_COMPAT_PROVIDER_ID", "vllm")
    register_provider(pid, OpenAIProvider(
        base_url=base, api_key=os.environ.get("OPENAI_COMPAT_API_KEY", "x"), **ckw,
    ))
    return pid


def main() -> None:
    ap = argparse.ArgumentParser(prog="predicta_harness.service")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    args = ap.parse_args()

    provider = _register_providers()
    backend = os.environ.get("PREDICTA_SANDBOX", "local")
    if provider:
        print(f"[predicta-harness] registered model provider '{provider}/*'")
    server = ThreadingHTTPServer((args.host, args.port), WorkHandler)
    print(f"[predicta-harness] work service on http://{args.host}:{args.port}  (sandbox={backend})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[predicta-harness] shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
