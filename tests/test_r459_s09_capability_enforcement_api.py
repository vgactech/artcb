"""Tests R459 — S09 enforcement : capability tokens sur routes API P2P réelles.

Prouve que la protection n'est pas seulement disponible (R456/R458-integ)
mais effectivement impossible à contourner sur le chemin critique API.

Matrice :
  E01 — Santé du store : /p2p/cap-tokens/health répond 200
  E02 — Issue sans auth opérateur → 401
  E03 — Issue avec mauvaise capability → 422
  E04 — Issue avec mauvais rôle → 422
  E05 — Issue valide → token_id retourné
  E06 — Redeem sans token header → 403 capability_token_missing
  E07 — Redeem token valide → 200 authorized=True
  E08 — Redeem même token une 2e fois → 403 already_consumed
  E09 — Redeem token inconnu → 403 unknown_token
  E10 — Redeem avec mauvais node_id → 403 node_mismatch
  E11 — Redeem avec mauvais domain_id → 403 domain_mismatch
  E12 — Redeem token CAP_PRODUCE sur route CAP_REPLICATE → 403 capability_mismatch
  E13 — Audit trail sans auth opérateur → 401
  E14 — Audit trail avec auth → enregistrement de la rédemption présent
  E15 — Appels parallèles avec même token → un seul 200
  E16 — Token expiré → 403 token_expired
  E17 — Sans token : l'opération sensible est IMPOSSIBLE à déclencher
  E18 — Issue + redeem replicate → 200 authorized=True
"""

from __future__ import annotations

import threading
import pytest
from fastapi.testclient import TestClient

from src.artcb.authz.capability_token import CapabilityTokenStore, issue_token
from src.artcb.authz.capability_token_middleware import (
    HEADER_CAPABILITY_TOKEN,
    HEADER_DOMAIN_ID,
    HEADER_NODE_ID,
)
from src.artcb.authz.node_roles import CAP_PRODUCE, CAP_REPLICATE, CAP_VALIDATE

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

NODE_A = "ovh-node-2"
DOMAIN = "artcb-mainnet-1"
FUTURE = "2099-01-01T00:00:00Z"
PAST = "2000-01-01T00:00:00Z"
OPERATOR_BEARER = "Bearer artcb-operator-test-token"


# ──────────────────────────────────────────────────────────────────────────────
# App factory — injects a fresh store per test
# ──────────────────────────────────────────────────────────────────────────────

def _make_test_app():
    """Create the cap-token router app with a fresh isolated store."""
    from fastapi import FastAPI
    from src.api.capability_token_routes import router, _get_store
    from src.artcb.authz.capability_token_middleware import (
        require_capability_token, reset_store
    )

    fresh_store = CapabilityTokenStore()
    app = FastAPI()

    # Override the store dependency
    app.dependency_overrides[_get_store] = lambda: fresh_store
    app.include_router(router)

    return app, TestClient(app, raise_server_exceptions=False), fresh_store


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _issue(client, *, capability=CAP_PRODUCE, role="CONSENSUS",
           node_id=NODE_A, domain_id=DOMAIN, valid_until=FUTURE):
    return client.post(
        "/p2p/cap-tokens/issue",
        headers={"Authorization": OPERATOR_BEARER},
        json={
            "node_id": node_id,
            "domain_id": domain_id,
            "capability": capability,
            "role": role,
            "valid_until": valid_until,
        },
    )


def _redeem_produce(client, token_id: str, node_id=NODE_A, domain_id=DOMAIN):
    return client.post(
        "/p2p/cap-tokens/redeem/produce-block",
        headers={
            HEADER_CAPABILITY_TOKEN: token_id,
            HEADER_NODE_ID: node_id,
            HEADER_DOMAIN_ID: domain_id,
        },
        json={"operation_context": {"test": True}},
    )


def _redeem_replicate(client, token_id: str, node_id=NODE_A, domain_id=DOMAIN):
    return client.post(
        "/p2p/cap-tokens/redeem/replicate",
        headers={
            HEADER_CAPABILITY_TOKEN: token_id,
            HEADER_NODE_ID: node_id,
            HEADER_DOMAIN_ID: domain_id,
        },
        json={"operation_context": {}},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_e01_health_200():
    app, client, _ = _make_test_app()
    resp = client.get("/p2p/cap-tokens/health")
    assert resp.status_code == 200
    assert resp.json()["store_operational"] is True
    assert resp.json()["certified_100"] is False


def test_e02_issue_no_auth_401():
    app, client, _ = _make_test_app()
    resp = client.post(
        "/p2p/cap-tokens/issue",
        json={"node_id": NODE_A, "domain_id": DOMAIN,
              "capability": CAP_PRODUCE, "role": "CONSENSUS"},
    )
    assert resp.status_code == 401


def test_e03_issue_bad_capability_422():
    app, client, _ = _make_test_app()
    resp = client.post(
        "/p2p/cap-tokens/issue",
        headers={"Authorization": OPERATOR_BEARER},
        json={"node_id": NODE_A, "domain_id": DOMAIN,
              "capability": "HACKER_CAP", "role": "CONSENSUS"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "capability_not_allowed"


def test_e04_issue_bad_role_422():
    app, client, _ = _make_test_app()
    resp = client.post(
        "/p2p/cap-tokens/issue",
        headers={"Authorization": OPERATOR_BEARER},
        json={"node_id": NODE_A, "domain_id": DOMAIN,
              "capability": CAP_PRODUCE, "role": "SUPERADMIN"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "role_not_allowed"


def test_e05_issue_valid_returns_token_id():
    app, client, _ = _make_test_app()
    resp = _issue(client)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["token_id"]) == 64
    assert data["node_id"] == NODE_A
    assert data["capability"] == CAP_PRODUCE


def test_e06_redeem_without_token_header_403():
    app, client, _ = _make_test_app()
    resp = client.post(
        "/p2p/cap-tokens/redeem/produce-block",
        headers={HEADER_NODE_ID: NODE_A, HEADER_DOMAIN_ID: DOMAIN},
        json={"operation_context": {}},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "capability_token_missing"


def test_e07_valid_redeem_200():
    app, client, _ = _make_test_app()
    tok_resp = _issue(client)
    token_id = tok_resp.json()["token_id"]

    resp = _redeem_produce(client, token_id)
    assert resp.status_code == 200
    data = resp.json()
    assert data["authorized"] is True
    assert data["capability"] == CAP_PRODUCE


def test_e08_double_redeem_second_denied():
    app, client, _ = _make_test_app()
    token_id = _issue(client).json()["token_id"]

    r1 = _redeem_produce(client, token_id)
    assert r1.status_code == 200

    r2 = _redeem_produce(client, token_id)
    assert r2.status_code == 403
    assert r2.json()["detail"]["reason"] == "already_consumed"


def test_e09_unknown_token_denied():
    app, client, _ = _make_test_app()
    resp = _redeem_produce(client, "ff" * 32)
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "unknown_token"


def test_e10_wrong_node_id_denied():
    app, client, _ = _make_test_app()
    token_id = _issue(client, node_id=NODE_A).json()["token_id"]
    resp = _redeem_produce(client, token_id, node_id="ovh-node-4")
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "node_mismatch"


def test_e11_wrong_domain_id_denied():
    app, client, _ = _make_test_app()
    token_id = _issue(client, domain_id=DOMAIN).json()["token_id"]
    resp = _redeem_produce(client, token_id, domain_id="artcb-devnet-1")
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "domain_mismatch"


def test_e12_capability_mismatch_denied():
    """CAP_PRODUCE token cannot be used on the CAP_REPLICATE route."""
    app, client, _ = _make_test_app()
    token_id = _issue(client, capability=CAP_PRODUCE).json()["token_id"]
    # Try to use it on the /redeem/replicate route which requires CAP_REPLICATE
    resp = _redeem_replicate(client, token_id)
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "capability_mismatch"


def test_e13_audit_no_auth_401():
    app, client, _ = _make_test_app()
    resp = client.get("/p2p/cap-tokens/audit")
    assert resp.status_code == 401


def test_e14_audit_records_redemption():
    app, client, store = _make_test_app()
    token_id = _issue(client).json()["token_id"]
    _redeem_produce(client, token_id)

    resp = client.get(
        "/p2p/cap-tokens/audit",
        headers={"Authorization": OPERATOR_BEARER},
    )
    assert resp.status_code == 200
    trail = resp.json()["audit_trail"]
    assert len(trail) >= 1
    assert any(e["outcome"] == "CONSUMED" for e in trail)


def test_e15_parallel_same_token_one_winner():
    """20 concurrent requests with the same token → exactly 1 success."""
    app, client, _ = _make_test_app()
    token_id = _issue(client).json()["token_id"]

    results: list[int] = []
    errors: list[Exception] = []

    def try_redeem():
        try:
            r = _redeem_produce(client, token_id)
            results.append(r.status_code)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=try_redeem) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert results.count(200) == 1
    assert results.count(403) == 19


def test_e16_expired_token_denied():
    app, client, _ = _make_test_app()
    token_id = _issue(client, valid_until=PAST).json()["token_id"]
    resp = _redeem_produce(client, token_id)
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "token_expired"


def test_e17_no_token_operation_impossible():
    """
    S09 enforcement proof: without a valid token, the sensitive operation
    is completely impossible — not just difficult.
    """
    app, client, _ = _make_test_app()
    # Attempt to produce a block without any token
    resp = client.post(
        "/p2p/cap-tokens/redeem/produce-block",
        headers={HEADER_NODE_ID: NODE_A, HEADER_DOMAIN_ID: DOMAIN},
        json={"operation_context": {"bypass_attempt": True}},
    )
    # Must be 403, never 200
    assert resp.status_code == 403
    assert "token" in resp.json()["detail"]["error"]


def test_e18_replicate_token_works():
    app, client, _ = _make_test_app()
    token_id = _issue(client, capability=CAP_REPLICATE, role="REPLICA").json()["token_id"]
    resp = _redeem_replicate(client, token_id)
    assert resp.status_code == 200
    assert resp.json()["authorized"] is True
    assert resp.json()["capability"] == CAP_REPLICATE
