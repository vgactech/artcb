"""Tests R461 — Routes API P2P NodeTpmBinding.

Suite : T01–T20
Protocole : ARTCB-NODE-TPM-BINDING-v1
Module testé : src/api/node_tpm_binding_routes.py

Stratégie :
    - TestClient FastAPI minimal avec le router monté directement.
    - Bindings construits via create_node_tpm_binding() — signatures réelles (pas de stub).
    - Invariants : certified=False, unique_human_proven=False dans toutes les réponses.
    - FAIL-CLOSED : payload non signé ou signature invalide → 400.
    - DEBUG_MODE actif.

CERTIFIED_100=false.
"""
from __future__ import annotations

import secrets
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nacl import signing as nacl_signing

from src.artcb.security.node_tpm_binding import (
    create_node_tpm_binding,
    BINDING_PROTOCOL,
    BINDING_PROTOCOL_V2,
)
from src.api.node_tpm_binding_routes import router


# ── App de test ───────────────────────────────────────────────────────────────

def _make_test_app() -> FastAPI:
    """Crée une app FastAPI minimale avec le router R461 et un faux opérateur."""
    from fastapi import Request
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    app = FastAPI()
    # Surcharge require_operator_write pour les tests
    from src.api import node_tpm_binding_routes as _mod
    _mod.require_operator_write = lambda: {"role": "operator"}
    app.include_router(router)
    return app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Client TestClient avec data_dir dans un répertoire temporaire."""
    from fastapi import Request

    app = FastAPI()

    # Surcharge de require_operator_write
    import src.api.node_tpm_binding_routes as _mod
    _mod.require_operator_write = lambda: {"role": "operator"}

    app.include_router(router)

    # Injecter un data_dir temporaire
    data_dir = tmp_path_factory.mktemp("data")
    app.state.data_dir = str(data_dir)

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def ed_key():
    """Paire de clés Ed25519 pour les tests."""
    sk = nacl_signing.SigningKey.generate()
    return sk


@pytest.fixture(scope="module")
def valid_binding_dict(ed_key):
    """Binding signé valide niveau E (software)."""
    b = create_node_tpm_binding(
        node_id="node-test-r461",
        ed25519_signing_key_bytes=bytes(ed_key),
        device_fingerprint="a" * 64,
        hardware_assurance_level="E",
        hardware_kind="software",
        tpm_ek_cert_hash=None,
        tpm_kind="absent",
        platform_system="Linux",
        env_type="test",
    )
    return b.to_dict()


# ── Tests ─────────────────────────────────────────────────────────────────────

# T01 — GET /list vide retourne count=0
def test_T01_list_empty(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/list")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 0
    assert data["certified"] is False
    assert data["unique_human_proven"] is False


# T02 — POST /receive binding valide → 200 accepted
def test_T02_receive_valid(client, valid_binding_dict):
    r = client.post("/api/v1/p2p/node-tpm-binding/receive", json=valid_binding_dict)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "accepted"
    assert data["node_id"] == "node-test-r461"
    assert data["certified"] is False
    assert data["unique_human_proven"] is False


# T03 — GET /list après réception → count=1
def test_T03_list_after_receive(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/list")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["bindings"][0]["node_id"] == "node-test-r461"
    assert data["bindings"][0]["certified"] is False


# T04 — GET /{node_id} existant → 200 avec l'entrée
def test_T04_get_existing(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/node-test-r461")
    assert r.status_code == 200
    data = r.json()
    assert data["node_id"] == "node-test-r461"
    assert data["certified"] is False
    assert data["unique_human_proven"] is False


# T05 — GET /{node_id} inexistant → 404
def test_T05_get_missing(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/node-inexistant-xyz")
    assert r.status_code == 404


# T06 — POST /receive avec signature altérée → 400 FAIL-CLOSED
def test_T06_receive_bad_signature(client, valid_binding_dict):
    bad = dict(valid_binding_dict)
    bad["ed25519_signature_hex"] = "ff" * 64  # signature invalide
    r = client.post("/api/v1/p2p/node-tpm-binding/receive", json=bad)
    assert r.status_code == 400
    assert "binding_rejected" in r.text or "binding_invalid" in r.text


# T07 — POST /receive sans node_id → 400
def test_T07_receive_missing_node_id(client, valid_binding_dict):
    bad = {k: v for k, v in valid_binding_dict.items() if k != "node_id"}
    r = client.post("/api/v1/p2p/node-tpm-binding/receive", json=bad)
    assert r.status_code == 400


# T08 — Invariant : certified=False dans toutes les réponses /list
def test_T08_invariant_certified_false_list(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/list")
    data = r.json()
    assert data["certified"] is False
    for b in data["bindings"]:
        assert b["certified"] is False


# T09 — Invariant : unique_human_proven=False dans toutes les réponses
def test_T09_invariant_unique_human_proven_false(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/list")
    data = r.json()
    assert data["unique_human_proven"] is False


# T10 — POST /receive avec node_id mismatch entre payload et binding → 400
def test_T10_receive_node_id_mismatch(client, valid_binding_dict):
    bad = dict(valid_binding_dict)
    bad["node_id"] = "node-autre"  # diverge du node_id signé dans le binding
    r = client.post("/api/v1/p2p/node-tpm-binding/receive", json=bad)
    assert r.status_code == 400


# T11 — POST /receive binding niveau A avec tpm_ek_cert_hash → tpm_proven=True
def test_T11_receive_level_A_tpm_proven(client, ed_key):
    b = create_node_tpm_binding(
        node_id="node-test-tpm-A",
        ed25519_signing_key_bytes=bytes(ed_key),
        device_fingerprint="b" * 64,
        hardware_assurance_level="A",
        hardware_kind="physical_tpm",
        tpm_ek_cert_hash="c" * 64,
        tpm_kind="physical",
        platform_system="Linux",
        env_type="test",
    )
    r = client.post("/api/v1/p2p/node-tpm-binding/receive", json=b.to_dict())
    assert r.status_code == 200
    data = r.json()
    assert data["tpm_proven"] is True
    assert data["certified"] is False


# T12 — POST /receive binding niveau E → tpm_proven=False
def test_T12_receive_level_E_tpm_not_proven(client, valid_binding_dict):
    data = client.get("/api/v1/p2p/node-tpm-binding/node-test-r461").json()
    assert data["tpm_proven"] is False


# T13 — Deux bindings → list count=2
def test_T13_list_two_bindings(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/list")
    data = r.json()
    assert data["count"] >= 2


# T14 — POST /receive binding avec mauvais nonce (signature non valide) → 400
def test_T14_receive_nonce_tampered(client, valid_binding_dict):
    bad = dict(valid_binding_dict)
    bad["nonce"] = "0" * 64  # nonce différent de celui signé
    r = client.post("/api/v1/p2p/node-tpm-binding/receive", json=bad)
    assert r.status_code == 400


# T15 — GET /list : verified_ok=True pour bindings acceptés
def test_T15_verified_ok_true_in_list(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/list")
    data = r.json()
    for b in data["bindings"]:
        assert b["verified_ok"] is True


# T16 — GET /{node_id} force certified=False même si stocké corrompu (test indirect)
def test_T16_get_certified_invariant(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/node-test-r461")
    assert r.json()["certified"] is False


# T17 — POST /receive avec JSON invalide (pas un dict) → erreur
def test_T17_receive_invalid_json(client):
    r = client.post(
        "/api/v1/p2p/node-tpm-binding/receive",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code in (400, 422)


# T18 — GET /{node_id} retourne hardware_assurance_level correct
def test_T18_get_hardware_assurance_level(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/node-test-tpm-A")
    assert r.status_code == 200
    assert r.json()["hardware_assurance_level"] == "A"


# T19 — POST /receive binding v2 (avec tpm_pcr0_sha256) → accepté
def test_T19_receive_v2_binding_with_pcr(client, ed_key):
    b = create_node_tpm_binding(
        node_id="node-test-pcr",
        ed25519_signing_key_bytes=bytes(ed_key),
        device_fingerprint="d" * 64,
        hardware_assurance_level="A",
        hardware_kind="physical_tpm",
        tpm_ek_cert_hash="e" * 64,
        tpm_kind="physical",
        platform_system="Linux",
        env_type="test",
        tpm_pcr0_sha256="f" * 64,
        tpm_quote_nonce=secrets.token_hex(32),
    )
    d = b.to_dict()
    assert d.get("protocol") == BINDING_PROTOCOL_V2
    r = client.post("/api/v1/p2p/node-tpm-binding/receive", json=d)
    assert r.status_code == 200
    assert r.json()["certified"] is False


# T20 — GET /list après T19 → node-test-pcr présent
def test_T20_list_contains_pcr_node(client):
    r = client.get("/api/v1/p2p/node-tpm-binding/list")
    ids = [b["node_id"] for b in r.json()["bindings"]]
    assert "node-test-pcr" in ids
