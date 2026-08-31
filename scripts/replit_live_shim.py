#!/usr/bin/env python3
"""Tiny HTTP server so Replit Autoscale healthcheck gets 200 before uvicorn exists.

Serves only / , /live , /ready , /health as JSON 200.
Does not load FastAPI, liboqs, or the chain. Kill it before binding uvicorn.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class LiveHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _ok(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = (self.path or "/").split("?", 1)[0]
        if path in {"/", "/live"}:
            self._ok(
                {
                    "status": "alive",
                    "phase": "replit_shim",
                    "message": "Process alive; FastAPI not bound yet. This is /live, not blockchain ready.",
                }
            )
            return
        if path == "/ready":
            body = {
                "status": "not_ready",
                "phase": "replit_shim",
                "reason": "fastapi_not_bound",
                "message": "/ready is false until uvicorn replaces this shim.",
            }
            raw = json.dumps(body).encode("utf-8")
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if path in {"/health", "/api/v1/health"}:
            self._ok(
                {
                    "status": "starting",
                    "phase": "replit_shim",
                    "git_sha": None,
                    "git_branch": None,
                    "bootstrap_mode": None,
                    "pqc": {"available": False, "availability_is_not_enforcement": True},
                    "message": "Shim only — not FastAPI /health. Do not treat this as PQC proof.",
                }
            )
            return
        self.send_response(404)
        self.end_headers()


def main() -> None:
    import os

    port = int(os.environ.get("ARTCB_PORT", "5000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), LiveHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
