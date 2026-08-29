"""ARTCB MCP Server — transport stdio + HTTP/SSE.

Zéro dépendance à ngrok. Le MCP tourne en local (stdio) ou via HTTP direct
(port configurable), sans tunnel externe requis.

Architecture :
    IDE (Cursor/Bob/VSCode) ←→ [MCP stdio] ←→ ArtcbMCPServer ←→ ARTCB API :8000
    Replit Agent             ←→ [MCP HTTP]  ←→ ArtcbMCPServer ←→ ARTCB API :8000
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

from src.artcb.mcp.tools import TOOLS, execute_tool
from src.artcb.mcp.resources import RESOURCES, read_resource
from src.artcb.mcp.prompts import PROMPTS

logger = logging.getLogger("artcb.mcp.server")

MCP_VERSION = "2024-11-05"
SERVER_NAME = "artcb-blockchain"
SERVER_VERSION = "0.1.0"


class ArtcbMCPServer:
    """Serveur MCP ARTCB — implémente le protocole JSON-RPC MCP v1."""

    def __init__(self, api_url: str | None = None) -> None:
        self.api_url = api_url or os.getenv("ARTCB_API_URL") or os.getenv("ARTCB_NODE_URL") or "http://localhost:8000"

    # ------------------------------------------------------------------
    # Handlers JSON-RPC
    # ------------------------------------------------------------------

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        """Dispatch une requête MCP et retourne la réponse."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "tools/list":
                result = self._handle_tools_list()
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            elif method == "resources/list":
                result = self._handle_resources_list()
            elif method == "resources/read":
                result = self._handle_resources_read(params)
            elif method == "prompts/list":
                result = self._handle_prompts_list()
            elif method == "prompts/get":
                result = self._handle_prompts_get(params)
            elif method == "ping":
                result = {}
            else:
                return self._error(req_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            logger.exception("MCP handler error method=%s", method)
            return self._error(req_id, -32603, str(exc))

        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": MCP_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "Serveur MCP ARTCB — blockchain post-quantique avec Proof of Learning. "
                "Utilisez artcb_memo pour graver des idées, artcb_think pour raisonner "
                "avec l'IA, artcb_search pour chercher dans la mémoire collective."
            ),
        }

    def _handle_tools_list(self) -> dict[str, Any]:
        return {"tools": TOOLS}

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        content = execute_tool(name, arguments, api_url=self.api_url)
        return {"content": content, "isError": False}

    def _handle_resources_list(self) -> dict[str, Any]:
        return {"resources": RESOURCES}

    def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri", "")
        contents = read_resource(uri, api_url=self.api_url)
        return {"contents": contents}

    def _handle_prompts_list(self) -> dict[str, Any]:
        return {"prompts": [{"name": p["name"], "description": p["description"]} for p in PROMPTS]}

    def _handle_prompts_get(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        for p in PROMPTS:
            if p["name"] == name:
                return p
        raise ValueError(f"Prompt not found: {name}")

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    # ------------------------------------------------------------------
    # Transport stdio (Cursor, Bob, VSCode)
    # ------------------------------------------------------------------

    def run_stdio(self) -> None:
        """Boucle stdio — lit du JSON-RPC sur stdin, écrit sur stdout."""
        logger.info("ARTCB MCP Server démarré (stdio) api_url=%s", self.api_url)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = self.handle(request)
            print(json.dumps(response), flush=True)

    # ------------------------------------------------------------------
    # Transport HTTP/SSE (Replit, Lovable, déploiements cloud)
    # ------------------------------------------------------------------

    def run_http(self, host: str = "0.0.0.0", port: int = 8001) -> None:
        """Serveur HTTP léger — aucune dépendance ngrok, écoute directement."""
        from http.server import BaseHTTPRequestHandler, HTTPServer

        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # type: ignore[override]
                logger.debug("MCP HTTP %s", fmt % args)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    request = json.loads(body)
                    response = server.handle(request)
                    payload = json.dumps(response).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception as exc:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(str(exc).encode())

            def do_GET(self):
                if self.path == "/health":
                    payload = b'{"status":"healthy","server":"artcb-mcp"}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    self.send_response(404)
                    self.end_headers()

        httpd = HTTPServer((host, port), Handler)
        logger.info("ARTCB MCP Server HTTP sur http://%s:%d — zéro ngrok requis", host, port)
        print(f"ARTCB MCP Server HTTP: http://{host}:{port}", flush=True)
        httpd.serve_forever()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    parser = argparse.ArgumentParser(description="ARTCB MCP Server")
    parser.add_argument("--http", type=int, default=None, metavar="PORT",
                        help="Lancer en mode HTTP sur PORT (sinon stdio)")
    parser.add_argument("--host", default="0.0.0.0", help="Host HTTP (défaut 0.0.0.0)")
    parser.add_argument("--api-url", default=None, help="URL API ARTCB (défaut http://localhost:8000)")
    args = parser.parse_args()

    srv = ArtcbMCPServer(api_url=args.api_url)
    if args.http:
        srv.run_http(host=args.host, port=args.http)
    else:
        srv.run_stdio()


if __name__ == "__main__":
    main()
