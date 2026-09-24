"""Tests R458-integ — capability_token_middleware.py : intégration FastAPI.

Tests :
  M01 — Token manquant → HTTP 403 capability_token_missing
  M02 — Token valide → RedemptionResult.allowed=True
  M03 — Token déjà consommé → HTTP 403 capability_token_denied:already_consumed
  M04 — Token inconnu → HTTP 403 capability_token_denied:unknown_token
  M05 — Token expiré → HTTP 403 capability_token_denied:token_expired
  M06 — Capability mismatch → HTTP 403 (token pour PRODUCE, route veut VALIDATE)
  M07 — Node-Id header manquant → HTTP 400 node_id_missing
  M08 — Domain-Id header manquant → HTTP 400 domain_id_missing
  M09 — inject_test_store() isole le store de test
  M10 — reset_store() remet à zéro
  M11 — partial token_id dans réponse d'erreur (pas de fuite complète)
  M12 — get_node_id / get_domain_id custom callable
  M13 — store override dans require_capability_token()
  M14 — audit trail enregistré après redemption via middleware
  M15 — double appel avec même token → premier OK, deuxième 403
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from src.artcb.authz.capability_token import (
    CapabilityTokenStore,
    issue_token,
)
from src.artcb.authz.capability_token_middleware import (
    require_capability_token,
    inject_test_store,
    reset_store,
    HEADER_CAPABILITY_TOKEN,
    HEADER_NODE_ID,
    HEADER_DOMAIN_ID,
)
from src.artcb.authz.node_roles import CAP_PRODUCE, CAP_VALIDATE

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

NODE_A = "ovh-node-2"
DOMAIN = "artcb-mainnet-1"
FUTURE = "2099-01-01T00:00:00Z"
PAST = "2000-01-01T00:00:00Z"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_app(store: CapabilityTokenStore) -> tuple[FastAPI, TestClient]:
    """Create a minimal FastAPI app with one guarded route."""
    app = FastAPI()

    @app.post("/blocks")
    def produce_block(
        result=Depends(
            require_capability_token(
                capability=CAP_PRODUCE,
                store=store,
            )
        ),
    ):
        return {"ok": True, "token_id": result.token_id}

    @app.post("/validate")
    def validate_tx(
        result=Depends(
            require_capability_token(
                capability=CAP_VALIDATE,
                store=store,
            )
        ),
    ):
        return {"ok": True}

    return app, TestClient(app, raise_server_exceptions=False)


def _issue_and_register(store, *, capability=CAP_PRODUCE, valid_until=FUTURE):
    tok = issue_token(
        node_id=NODE_A,
        domain_id=DOMAIN,
        capability=capability,
        role="CONSENSUS",
        valid_until=valid_until,
    )
    store.register(tok)
    return tok


def _headers(token_id: str, node_id: str = NODE_A, domain_id: str = DOMAIN) -> dict:
    return {
        HEADER_CAPABILITY_TOKEN: token_id,
        HEADER_NODE_ID: node_id,
        HEADER_DOMAIN_ID: domain_id,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Fixture
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset():
    yield
    reset_store()


# ──────────────────────────────────────────────────────────────────────────────
# M01 — Token manquant → 403
# ──────────────────────────────────────────────────────────────────────────────

def test_m01_missing_token_403():
    store = CapabilityTokenStore()
    _, client = _make_app(store)
    resp = client.post("/blocks", headers={
        HEADER_NODE_ID: NODE_A,
        HEADER_DOMAIN_ID: DOMAIN,
    })
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "capability_token_missing"


# ──────────────────────────────────────────────────────────────────────────────
# M02 — Token valide → 200
# ──────────────────────────────────────────────────────────────────────────────

def test_m02_valid_token_200():
    store = CapabilityTokenStore()
    tok = _issue_and_register(store)
    _, client = _make_app(store)
    resp = client.post("/blocks", headers=_headers(tok.token_id))
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ──────────────────────────────────────────────────────────────────────────────
# M03 — Token déjà consommé → 403
# ──────────────────────────────────────────────────────────────────────────────

def test_m03_consumed_token_403():
    store = CapabilityTokenStore()
    tok = _issue_and_register(store)
    _, client = _make_app(store)
    # First call OK
    r1 = client.post("/blocks", headers=_headers(tok.token_id))
    assert r1.status_code == 200
    # Second call → denied
    r2 = client.post("/blocks", headers=_headers(tok.token_id))
    assert r2.status_code == 403
    assert r2.json()["detail"]["reason"] == "already_consumed"


# ──────────────────────────────────────────────────────────────────────────────
# M04 — Token inconnu → 403
# ──────────────────────────────────────────────────────────────────────────────

def test_m04_unknown_token_403():
    store = CapabilityTokenStore()
    _, client = _make_app(store)
    resp = client.post("/blocks", headers=_headers("deadbeef" * 8))
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "unknown_token"


# ──────────────────────────────────────────────────────────────────────────────
# M05 — Token expiré → 403
# ──────────────────────────────────────────────────────────────────────────────

def test_m05_expired_token_403():
    store = CapabilityTokenStore()
    tok = _issue_and_register(store, valid_until=PAST)
    _, client = _make_app(store)
    resp = client.post("/blocks", headers=_headers(tok.token_id))
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "token_expired"


# ──────────────────────────────────────────────────────────────────────────────
# M06 — Capability mismatch → 403
# ──────────────────────────────────────────────────────────────────────────────

def test_m06_capability_mismatch_403():
    store = CapabilityTokenStore()
    # Issue a PRODUCE token, but the /validate route requires VALIDATE
    tok = _issue_and_register(store, capability=CAP_PRODUCE)
    _, client = _make_app(store)
    resp = client.post("/validate", headers=_headers(tok.token_id))
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "capability_mismatch"


# ──────────────────────────────────────────────────────────────────────────────
# M07 — Node-Id header manquant → 400
# ──────────────────────────────────────────────────────────────────────────────

def test_m07_missing_node_id_400():
    store = CapabilityTokenStore()
    tok = _issue_and_register(store)
    _, client = _make_app(store)
    resp = client.post("/blocks", headers={
        HEADER_CAPABILITY_TOKEN: tok.token_id,
        HEADER_DOMAIN_ID: DOMAIN,
        # Missing HEADER_NODE_ID
    })
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "node_id_missing"


# ──────────────────────────────────────────────────────────────────────────────
# M08 — Domain-Id header manquant → 400
# ──────────────────────────────────────────────────────────────────────────────

def test_m08_missing_domain_id_400():
    store = CapabilityTokenStore()
    tok = _issue_and_register(store)
    _, client = _make_app(store)
    resp = client.post("/blocks", headers={
        HEADER_CAPABILITY_TOKEN: tok.token_id,
        HEADER_NODE_ID: NODE_A,
        # Missing HEADER_DOMAIN_ID
    })
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "domain_id_missing"


# ──────────────────────────────────────────────────────────────────────────────
# M09 — inject_test_store() isole le store global
# ──────────────────────────────────────────────────────────────────────────────

def test_m09_inject_test_store_isolates():
    import src.artcb.authz.capability_token_middleware as mw
    original_store = mw._GLOBAL_STORE
    fresh_store = CapabilityTokenStore()
    inject_test_store(fresh_store)
    assert mw._GLOBAL_STORE is fresh_store
    assert mw._GLOBAL_STORE is not original_store
    reset_store()
    assert mw._GLOBAL_STORE is not fresh_store


# ──────────────────────────────────────────────────────────────────────────────
# M10 — reset_store() remet à zéro le global store
# ──────────────────────────────────────────────────────────────────────────────

def test_m10_reset_store_clears():
    import src.artcb.authz.capability_token_middleware as mw
    inject_test_store(CapabilityTokenStore())
    reset_store()
    counts = mw._GLOBAL_STORE.count_by_state()
    assert counts["PENDING"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# M11 — Partial token_id dans réponse d'erreur (pas de fuite complète)
# ──────────────────────────────────────────────────────────────────────────────

def test_m11_partial_token_in_error():
    store = CapabilityTokenStore()
    _, client = _make_app(store)
    full_token = "a" * 64  # 64 hex chars
    resp = client.post("/blocks", headers=_headers(full_token))
    assert resp.status_code == 403
    returned_token = resp.json()["detail"]["token_id"]
    # Must be truncated (partial only)
    assert len(returned_token) < len(full_token)
    assert returned_token.endswith("...")


# ──────────────────────────────────────────────────────────────────────────────
# M12 — get_node_id / get_domain_id custom callable
# ──────────────────────────────────────────────────────────────────────────────

def test_m12_custom_get_node_domain_id():
    """Test get_node_id / get_domain_id callables via the dependency directly (unit level)."""
    from unittest.mock import MagicMock
    from src.artcb.authz.capability_token_middleware import require_capability_token

    store = CapabilityTokenStore()
    tok = _issue_and_register(store)

    # Build a mock request with custom headers
    mock_request = MagicMock()
    mock_request.headers.get = lambda k, default="": {
        HEADER_CAPABILITY_TOKEN: tok.token_id,
        "X-Custom-Node": NODE_A,
        "X-Custom-Domain": DOMAIN,
    }.get(k, default)
    mock_request.client = None
    mock_request.url.path = "/test"

    dep = require_capability_token(
        capability=CAP_PRODUCE,
        get_node_id=lambda req: req.headers.get("X-Custom-Node", ""),
        get_domain_id=lambda req: req.headers.get("X-Custom-Domain", ""),
        store=store,
    )
    result = dep(mock_request)
    assert result.allowed is True


# ──────────────────────────────────────────────────────────────────────────────
# M13 — store override dans require_capability_token()
# ──────────────────────────────────────────────────────────────────────────────

def test_m13_store_override_in_dependency():
    store_a = CapabilityTokenStore()
    store_b = CapabilityTokenStore()
    tok = _issue_and_register(store_a)

    _, client = _make_app(store_a)
    # Token registered in store_a — should work
    r1 = client.post("/blocks", headers=_headers(tok.token_id))
    assert r1.status_code == 200

    # A different app using store_b should not find the token
    _, client_b = _make_app(store_b)
    r2 = client_b.post("/blocks", headers=_headers(tok.token_id))
    assert r2.status_code == 403
    assert r2.json()["detail"]["reason"] == "unknown_token"


# ──────────────────────────────────────────────────────────────────────────────
# M14 — audit trail enregistré après redemption via middleware
# ──────────────────────────────────────────────────────────────────────────────

def test_m14_audit_trail_via_middleware():
    store = CapabilityTokenStore()
    tok = _issue_and_register(store)
    _, client = _make_app(store)
    client.post("/blocks", headers=_headers(tok.token_id))
    trail = store.get_audit_trail(tok.token_id)
    assert len(trail) == 1
    assert trail[0]["outcome"] == "CONSUMED"
    assert trail[0]["reason"] == "ok"


# ──────────────────────────────────────────────────────────────────────────────
# M15 — Double appel même token → 200 puis 403
# ──────────────────────────────────────────────────────────────────────────────

def test_m15_double_call_first_ok_second_denied():
    store = CapabilityTokenStore()
    tok = _issue_and_register(store)
    _, client = _make_app(store)

    r1 = client.post("/blocks", headers=_headers(tok.token_id))
    assert r1.status_code == 200

    r2 = client.post("/blocks", headers=_headers(tok.token_id))
    assert r2.status_code == 403
    assert r2.json()["detail"]["reason"] == "already_consumed"
