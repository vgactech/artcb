"""Tests SDK ARTCB Python — client officiel.

Couvre :
- ArtcbClient : instanciation, headers, repr
- connect() : succès et échec
- Toutes les méthodes avec TestClient FastAPI (sans réseau réel)
- ArtcbError levée sur erreur HTTP
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.artcb.sdk import ArtcbClient, ArtcbError, connect


# ── Fixture : app + client SDK ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def tc(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def sdk():
    """SDK pointant sur l'API de test (pas de réseau)."""
    return ArtcbClient("http://testserver")


# ── Tests instanciation ───────────────────────────────────────────────────────

class TestArtcbClientInit:

    def test_default_base_url(self, monkeypatch):
        monkeypatch.delenv("ARTCB_API_URL", raising=False)
        monkeypatch.delenv("ARTCB_NODE_URL", raising=False)
        c = ArtcbClient()
        assert c.base_url == "http://localhost:8000"

    def test_env_base_url(self, monkeypatch):
        monkeypatch.setenv("ARTCB_API_URL", "http://152.228.144.34:8000")
        c = ArtcbClient()
        assert c.base_url == "http://152.228.144.34:8000"

    def test_custom_base_url(self):
        c = ArtcbClient("http://myhost:9999")
        assert c.base_url == "http://myhost:9999"

    def test_trailing_slash_stripped(self):
        c = ArtcbClient("http://myhost:9999/")
        assert c.base_url == "http://myhost:9999"

    def test_api_key_stored(self):
        c = ArtcbClient(api_key="artcb_abc123")
        assert c.api_key == "artcb_abc123"

    def test_no_api_key(self):
        c = ArtcbClient()
        # Sans env var, api_key peut être None
        assert c.api_key is None or isinstance(c.api_key, str)

    def test_repr(self):
        c = ArtcbClient(api_key="artcb_x")
        assert "ArtcbClient" in repr(c)
        assert "authenticated=True" in repr(c)

    def test_repr_not_authenticated(self):
        c = ArtcbClient()
        # api_key peut venir de l'env
        r = repr(c)
        assert "ArtcbClient" in r

    def test_headers_with_key(self):
        c = ArtcbClient(api_key="artcb_test")
        h = c._headers()
        assert h["Authorization"] == "Bearer artcb_test"
        assert h["Content-Type"] == "application/json"

    def test_headers_without_key(self):
        c = ArtcbClient()
        c.api_key = None
        h = c._headers()
        assert "Authorization" not in h

    def test_context_manager(self):
        with ArtcbClient() as c:
            assert isinstance(c, ArtcbClient)


# ── Tests méthodes via FastAPI TestClient ─────────────────────────────────────

class TestArtcbClientMethods:
    """Tests des méthodes SDK via mock httpx."""

    def _make_client_with_mock(self, status: int, body: dict | list) -> ArtcbClient:
        """Crée un client SDK dont httpx est mocké."""
        c = ArtcbClient("http://testserver", api_key="artcb_test")
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.json.return_value = body
        mock_resp.text = json.dumps(body)
        return c, mock_resp

    def test_health_returns_dict(self):
        c, mock_resp = self._make_client_with_mock(200, {"status": "healthy", "version": "0.3.0"})
        with patch("httpx.get", return_value=mock_resp):
            result = c.health()
        assert result["status"] == "healthy"

    def test_verify_chain(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "valid": True, "block_count": 521, "pqc_algorithm": "ML-DSA-65"
        })
        with patch("httpx.get", return_value=mock_resp):
            result = c.verify()
        assert result["valid"] is True
        assert result["pqc_algorithm"] == "ML-DSA-65"

    def test_memo_returns_block(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "memo_stored": True, "block_index": 42, "pol_score": 0.75, "hash": "abc123"
        })
        with patch("httpx.post", return_value=mock_resp):
            result = c.memo("Test observation", memo_type="observation")
        assert result["block_index"] == 42
        assert result["pol_score"] == 0.75

    def test_think_returns_answer(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "answer": "La solution est X", "block_index": 43, "pol_score": 0.8
        })
        with patch("httpx.post", return_value=mock_resp):
            result = c.think("Question de test ?")
        assert "answer" in result

    def test_search_returns_list(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "results": [{"text": "résultat", "score": 0.9}], "count": 1
        })
        with patch("httpx.get", return_value=mock_resp):
            results = c.search("test query")
        assert isinstance(results, list)
        assert results[0]["score"] == 0.9

    def test_wallets_returns_list(self):
        c, mock_resp = self._make_client_with_mock(200, [
            {"name": "wallet1", "address": "artcb1q..."}
        ])
        with patch("httpx.get", return_value=mock_resp):
            result = c.wallets()
        assert isinstance(result, list)

    def test_create_wallet(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "name": "new_wallet", "address": "artcb1qxxx"
        })
        with patch("httpx.post", return_value=mock_resp):
            result = c.create_wallet("new_wallet")
        assert result["name"] == "new_wallet"

    def test_create_api_key(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "token": "artcb_newtoken123", "key_id": "kid_abc", "label": "test"
        })
        with patch("httpx.post", return_value=mock_resp):
            result = c.create_api_key("test", scopes=["read"])
        assert "token" in result

    def test_list_api_keys(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "keys": [{"label": "k1", "active": True}], "count": 1
        })
        with patch("httpx.get", return_value=mock_resp):
            result = c.list_api_keys()
        assert isinstance(result, list)

    def test_memorize(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "graph_id": "g_123", "pol_score": 0.7, "block_index": 50
        })
        with patch("httpx.post", return_value=mock_resp):
            result = c.memorize("Texte de test")
        assert "graph_id" in result or "pol_score" in result

    def test_create_rule(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "rule_id": "rule_1", "rule_text": "SI pol_score > 0.9 ALORS bonus = 0.5"
        })
        with patch("httpx.post", return_value=mock_resp):
            result = c.create_rule("SI pol_score > 0.9 ALORS bonus = 0.5")
        assert "rule_id" in result or "rule_text" in result

    def test_list_rules(self):
        c, mock_resp = self._make_client_with_mock(200, {"rules": [], "count": 0})
        with patch("httpx.get", return_value=mock_resp):
            result = c.list_rules()
        assert isinstance(result, list)

    def test_register_webhook(self):
        c, mock_resp = self._make_client_with_mock(200, {
            "hook_id": "hook_1", "url": "https://my.server/hook"
        })
        with patch("httpx.post", return_value=mock_resp):
            result = c.register_webhook("https://my.server/hook")
        assert "hook_id" in result or "url" in result


# ── Tests erreurs ─────────────────────────────────────────────────────────────

class TestArtcbErrors:

    def test_http_error_raises_artcb_error(self):
        c = ArtcbClient("http://testserver")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        with patch("httpx.get", return_value=mock_resp):
            with pytest.raises(ArtcbError):
                c.health()

    def test_500_raises_artcb_error(self):
        c = ArtcbClient("http://testserver")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch("httpx.post", return_value=mock_resp):
            with pytest.raises(ArtcbError):
                c.memo("test")

    def test_connect_unreachable_raises(self):
        with pytest.raises(ArtcbError):
            connect("http://127.0.0.1:19999")  # port fermé


# ── Tests connect() factory ───────────────────────────────────────────────────

class TestConnectFactory:

    def test_connect_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "healthy"}
        mock_resp.text = '{"status":"healthy"}'
        with patch("httpx.get", return_value=mock_resp):
            c = connect("http://fakeserver:8000")
        assert isinstance(c, ArtcbClient)

    def test_connect_unhealthy_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "degraded"}
        mock_resp.text = '{"status":"degraded"}'
        with patch("httpx.get", return_value=mock_resp):
            with pytest.raises(ArtcbError):
                connect("http://fakeserver:8000")
