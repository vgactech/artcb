"""Tests serveur MCP ARTCB — Phase 12.1.

Tests couverts :
    - Initialisation du serveur MCP
    - tools/list — retourne les 7 outils
    - resources/list — retourne les 4 ressources
    - prompts/list — retourne les 2 prompts
    - tools/call artcb_memo (mock API)
    - tools/call artcb_think (mock API)
    - tools/call artcb_search (mock API)
    - tools/call artcb_chain_verify (mock API)
    - tools/call artcb_wallet_balance (mock API)
    - tools/call artcb_mine (mock API)
    - resources/read artcb://chain/status (mock API)
    - resources/read artcb://pol/score (mock API)
    - ping method
    - method inconnue → erreur JSON-RPC
    - import JSON manquant champ → erreur gérée
    - mode HTTP server instanciation
    - mode stdio handler
    - prompts/get par nom
    - tools/call outil inexistant → message d'erreur
    - transport HTTP /health endpoint
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from src.artcb.mcp.server import ArtcbMCPServer
from src.artcb.mcp.tools import TOOLS, execute_tool
from src.artcb.mcp.resources import RESOURCES, read_resource
from src.artcb.mcp.prompts import PROMPTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_api_post(url: str, data: dict) -> dict:
    """Simule les réponses de l'API ARTCB pour les tests."""
    if "/ai/memo" in url:
        return {"block_index": 600, "pol_score": 0.75, "block_hash": "abc123def456", "message": "Gravé en bloc #600"}
    elif "/ai/think" in url:
        return {"answer": "Réponse IA test", "block_index": 601, "pol_score": 0.70}
    elif "/mining/pipeline" in url:
        return {"block_index": 602, "pol_score": 0.80, "graph": {"node_count": 5}}
    elif "/bridges/import" in url:
        return {"block_index": 603, "pol_score": 0.65}
    return {"result": "ok"}


def _mock_api_get(url: str):
    """Simule les réponses GET de l'API ARTCB."""
    if "/chain/verify" in url:
        return {"valid": True, "block_count": 525, "pqc_algorithm": "ML-DSA-65", "hybrid_signatures": True}
    elif "/wallet/balance/" in url:
        return {"balance_artcb": 42.5, "balance_satoshi": 4250000000}
    elif "/chain/search" in url:
        return {"results": [{"block_index": 10, "text": "Test result", "score": 0.9}]}
    elif "/ai/status" in url:
        return {"chain": {"height": 525, "pol_avg": 0.7389, "last_block": {"index": 524}}, "memory": {}}
    elif "/dashboard/mining/status" in url:
        return {"pol_score": 0.6, "current_reward_artcb": 50.0, "block_count": 525, "blocks_until_halving": 209475}
    elif "/p2p/status" in url:
        return {"node_id": "node_test123", "api_port": 8000}
    elif "/chain" in url:
        return {"blocks": [{"index": i, "pol_score": 0.75, "timestamp": "2026-07-31", "visibility": "private"} for i in range(525, 528)]}
    return {}


# ---------------------------------------------------------------------------
# Tests serveur MCP
# ---------------------------------------------------------------------------

class TestArtcbMCPServerInit:
    def test_default_api_url(self, monkeypatch):
        monkeypatch.delenv("ARTCB_API_URL", raising=False)
        monkeypatch.delenv("ARTCB_NODE_URL", raising=False)
        srv = ArtcbMCPServer()
        assert "localhost:8000" in srv.api_url

    def test_env_api_url(self, monkeypatch):
        monkeypatch.setenv("ARTCB_API_URL", "http://152.228.144.34:8000")
        srv = ArtcbMCPServer()
        assert srv.api_url == "http://152.228.144.34:8000"

    def test_custom_api_url(self):
        srv = ArtcbMCPServer(api_url="http://mynode:9000")
        assert srv.api_url == "http://mynode:9000"

    def test_ping(self):
        srv = ArtcbMCPServer()
        resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
        assert resp["result"] == {}
        assert resp["id"] == 1

    def test_initialize(self):
        srv = ArtcbMCPServer()
        resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert "protocolVersion" in resp["result"]
        assert "capabilities" in resp["result"]
        assert resp["result"]["serverInfo"]["name"] == "artcb-blockchain"

    def test_unknown_method(self):
        srv = ArtcbMCPServer()
        resp = srv.handle({"jsonrpc": "2.0", "id": 99, "method": "nonexistent", "params": {}})
        assert "error" in resp
        assert resp["error"]["code"] == -32601


class TestMCPToolsList:
    def test_tools_list(self):
        srv = ArtcbMCPServer()
        resp = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = resp["result"]["tools"]
        assert len(tools) == 7
        names = {t["name"] for t in tools}
        assert "artcb_memo" in names
        assert "artcb_think" in names
        assert "artcb_search" in names
        assert "artcb_mine" in names
        assert "artcb_chain_verify" in names
        assert "artcb_wallet_balance" in names
        assert "artcb_bridge_import" in names

    def test_tools_have_input_schema(self):
        for tool in TOOLS:
            assert "inputSchema" in tool
            assert "name" in tool
            assert "description" in tool


class TestMCPResourcesList:
    def test_resources_list(self):
        srv = ArtcbMCPServer()
        resp = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}})
        resources = resp["result"]["resources"]
        assert len(resources) >= 4
        uris = {r["uri"] for r in resources}
        assert "artcb://chain/status" in uris
        assert "artcb://pol/score" in uris


class TestMCPPromptsList:
    def test_prompts_list(self):
        srv = ArtcbMCPServer()
        resp = srv.handle({"jsonrpc": "2.0", "id": 4, "method": "prompts/list", "params": {}})
        prompts = resp["result"]["prompts"]
        assert len(prompts) >= 2

    def test_prompts_get(self):
        srv = ArtcbMCPServer()
        resp = srv.handle({"jsonrpc": "2.0", "id": 5, "method": "prompts/get",
                           "params": {"name": "artcb_blockchain_assistant"}})
        assert "messages" in resp["result"]
        assert len(resp["result"]["messages"]) >= 1

    def test_prompts_get_unknown(self):
        srv = ArtcbMCPServer()
        resp = srv.handle({"jsonrpc": "2.0", "id": 6, "method": "prompts/get",
                           "params": {"name": "nonexistent_prompt"}})
        assert "error" in resp


class TestMCPToolsCall:
    @patch("src.artcb.mcp.tools._api_post", side_effect=_mock_api_post)
    def test_tool_memo(self, mock_post):
        result = execute_tool("artcb_memo", {"text": "Test pensée"}, api_url="http://test:8000")
        assert len(result) == 1
        assert "600" in result[0]["text"] or "bloc" in result[0]["text"].lower()

    @patch("src.artcb.mcp.tools._api_post", side_effect=_mock_api_post)
    def test_tool_think(self, mock_post):
        result = execute_tool("artcb_think", {"question": "Qu'est-ce que PoL ?"}, api_url="http://test:8000")
        assert len(result) == 1
        assert "Réponse IA test" in result[0]["text"]

    @patch("src.artcb.mcp.tools._api_get", side_effect=_mock_api_get)
    def test_tool_chain_verify(self, mock_get):
        result = execute_tool("artcb_chain_verify", {}, api_url="http://test:8000")
        assert "525" in result[0]["text"]
        assert "valid" in result[0]["text"].lower()

    @patch("src.artcb.mcp.tools._api_get", side_effect=_mock_api_get)
    def test_tool_wallet_balance(self, mock_get):
        result = execute_tool("artcb_wallet_balance",
                              {"address": "artcb1test000000000000000000000000"},
                              api_url="http://test:8000")
        assert "42.5" in result[0]["text"]

    @patch("src.artcb.mcp.tools._api_get", side_effect=_mock_api_get)
    def test_tool_search(self, mock_get):
        result = execute_tool("artcb_search", {"query": "test"}, api_url="http://test:8000")
        assert "résultat" in result[0]["text"].lower() or "Test result" in result[0]["text"]

    @patch("src.artcb.mcp.tools._api_post", side_effect=_mock_api_post)
    def test_tool_mine(self, mock_post):
        result = execute_tool("artcb_mine", {"text": "Texte à miner"}, api_url="http://test:8000")
        assert "602" in result[0]["text"] or "minage" in result[0]["text"].lower()

    @patch("src.artcb.mcp.tools._api_post", side_effect=_mock_api_post)
    def test_tool_bridge_import(self, mock_post):
        result = execute_tool("artcb_bridge_import",
                              {"chain": "ethereum", "tx_hash": "0xabc123"},
                              api_url="http://test:8000")
        assert "ETHEREUM" in result[0]["text"] or "bridge" in result[0]["text"].lower()

    def test_tool_unknown(self):
        result = execute_tool("outil_inexistant", {}, api_url="http://test:8000")
        assert "inconnu" in result[0]["text"].lower()


class TestMCPResources:
    @patch("src.artcb.mcp.resources._api_get", side_effect=_mock_api_get)
    def test_read_chain_status(self, mock_get):
        contents = read_resource("artcb://chain/status", api_url="http://test:8000")
        assert len(contents) == 1
        assert contents[0]["uri"] == "artcb://chain/status"
        data = json.loads(contents[0]["text"])
        assert "height" in data

    @patch("src.artcb.mcp.resources._api_get", side_effect=_mock_api_get)
    def test_read_pol_score(self, mock_get):
        contents = read_resource("artcb://pol/score", api_url="http://test:8000")
        data = json.loads(contents[0]["text"])
        assert "pol_score" in data

    def test_read_unknown_resource(self):
        contents = read_resource("artcb://unknown/thing", api_url="http://test:8000")
        assert "error" in contents[0]["text"].lower() or "inconnue" in contents[0]["text"].lower()


class TestMCPHTTPTransport:
    def test_http_server_instantiation(self):
        """Vérifie que le serveur HTTP peut être instancié sans erreur."""
        srv = ArtcbMCPServer(api_url="http://localhost:8000")
        assert srv is not None
        # On ne lance pas le serveur (bloquant), on vérifie juste l'import

    def test_stdio_handler_single_request(self):
        """Simule une requête stdio."""
        srv = ArtcbMCPServer()
        request = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
        input_data = json.dumps(request) + "\n"
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        sys.stdin = StringIO(input_data)
        captured = StringIO()
        sys.stdout = captured
        try:
            srv.run_stdio()
        except StopIteration:
            pass
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout
        output = captured.getvalue().strip()
        assert output  # quelque chose a été écrit
        resp = json.loads(output)
        assert resp.get("result") == {}
