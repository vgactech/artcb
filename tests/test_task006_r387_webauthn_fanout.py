"""R387 — TASK-006 : Tests de réplication identité WebAuthn entre nœuds.

Teste :
  T01-T05 : _safe_fanout_record() — filtrage des champs publics
  T06-T08 : _is_fanout_enabled() — variable d'environnement
  T09-T12 : receive_credential() — réception et stockage
  T13-T15 : Route POST /webauthn/identity/receive — endpoint HTTP

Tous les tests passent avec ARTCB_WEBAUTHN_FANOUT_DISABLED=1 (pas de vraies
connexions réseau). Les tests du fanout réseau sont des tests d'intégration live
(hors scope CI local).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def disable_fanout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Désactive le fanout réseau pour tous les tests unitaires."""
    monkeypatch.setenv("ARTCB_WEBAUTHN_FANOUT_DISABLED", "1")


@pytest.fixture()
def tmp_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirige les credentials WebAuthn vers un répertoire temporaire."""
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
    return tmp_path


SAMPLE_CREDENTIAL: dict[str, Any] = {
    "credential_id": "cred_abc123def456",
    "cose_b64": "pQECAyYgASFYII0GWyXVPr7HKY4v",  # clé publique fictive COSE
    "sign_count": 5,
    "wallet_name": "alice-wallet",
    "address": "artcb1abcdef",
    "modality": "fingerprint",
    "rp_id": "artcb.me",
    # Champs PRIVÉS — ne doivent jamais passer dans le fanout
    "_private_key": "SHOULD_NEVER_BE_SENT",
    "_secret": "ALSO_PRIVATE",
}


# ─── T01-T05 : _safe_fanout_record() ──────────────────────────────────────────

def test_T01_safe_fanout_keeps_public_fields() -> None:
    """T01 : _safe_fanout_record conserve credential_id, cose_b64, wallet_name."""
    from src.artcb.security.webauthn_store import _safe_fanout_record
    result = _safe_fanout_record(SAMPLE_CREDENTIAL)
    assert result["credential_id"] == "cred_abc123def456"
    assert result["cose_b64"] == "pQECAyYgASFYII0GWyXVPr7HKY4v"
    assert result["wallet_name"] == "alice-wallet"
    assert result["address"] == "artcb1abcdef"
    assert result["modality"] == "fingerprint"
    assert result["rp_id"] == "artcb.me"
    assert result["sign_count"] == 5


def test_T02_safe_fanout_removes_private_fields() -> None:
    """T02 : _safe_fanout_record supprime les champs privés."""
    from src.artcb.security.webauthn_store import _safe_fanout_record
    result = _safe_fanout_record(SAMPLE_CREDENTIAL)
    assert "_private_key" not in result
    assert "_secret" not in result


def test_T03_safe_fanout_empty_record() -> None:
    """T03 : _safe_fanout_record sur record vide retourne dict vide."""
    from src.artcb.security.webauthn_store import _safe_fanout_record
    assert _safe_fanout_record({}) == {}


def test_T04_safe_fanout_only_public_fields() -> None:
    """T04 : _safe_fanout_record avec seulement des champs autorisés — tous conservés."""
    from src.artcb.security.webauthn_store import _safe_fanout_record, _FANOUT_PUBLIC_FIELDS
    record = {k: f"val_{k}" for k in _FANOUT_PUBLIC_FIELDS}
    result = _safe_fanout_record(record)
    assert set(result.keys()) == _FANOUT_PUBLIC_FIELDS


def test_T05_safe_fanout_sign_count_integer() -> None:
    """T05 : sign_count est transmis comme entier (pas de coercition nécessaire)."""
    from src.artcb.security.webauthn_store import _safe_fanout_record
    rec = {"credential_id": "x", "cose_b64": "y", "wallet_name": "w", "sign_count": 42}
    result = _safe_fanout_record(rec)
    assert result["sign_count"] == 42
    assert isinstance(result["sign_count"], int)


# ─── T06-T08 : _is_fanout_enabled() ──────────────────────────────────────────

def test_T06_fanout_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """T06 : ARTCB_WEBAUTHN_FANOUT_DISABLED=1 désactive le fanout."""
    from src.artcb.security.webauthn_store import _is_fanout_enabled
    monkeypatch.setenv("ARTCB_WEBAUTHN_FANOUT_DISABLED", "1")
    assert _is_fanout_enabled() is False


def test_T07_fanout_disabled_by_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """T07 : ARTCB_WEBAUTHN_FANOUT_DISABLED=true désactive le fanout."""
    from src.artcb.security.webauthn_store import _is_fanout_enabled
    monkeypatch.setenv("ARTCB_WEBAUTHN_FANOUT_DISABLED", "true")
    assert _is_fanout_enabled() is False


def test_T08_fanout_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """T08 : Sans variable d'env, le fanout est activé."""
    from src.artcb.security.webauthn_store import _is_fanout_enabled
    monkeypatch.delenv("ARTCB_WEBAUTHN_FANOUT_DISABLED", raising=False)
    assert _is_fanout_enabled() is True


# ─── T09-T12 : receive_credential() ──────────────────────────────────────────

def test_T09_receive_valid_credential(tmp_data_dir: Path) -> None:
    """T09 : receive_credential() stocke un credential valide et retourne True."""
    from src.artcb.security.webauthn_store import receive_credential, load_credentials
    record = {
        "credential_id": "receive_test_001",
        "cose_b64": "pQECAyYgASFY",
        "wallet_name": "bob-wallet",
        "address": "artcb1bob",
        "modality": "fingerprint",
        "rp_id": "artcb.me",
        "sign_count": 0,
    }
    result = receive_credential(record)
    assert result is True
    stored = load_credentials()
    found = [c for c in stored if c.get("credential_id") == "receive_test_001"]
    assert len(found) == 1
    assert found[0]["wallet_name"] == "bob-wallet"


def test_T10_receive_missing_required_fields(tmp_data_dir: Path) -> None:
    """T10 : receive_credential() retourne False si credential_id manque."""
    from src.artcb.security.webauthn_store import receive_credential
    record = {
        "cose_b64": "pQECAyYgASFY",
        "wallet_name": "bob-wallet",
        # manque credential_id
    }
    result = receive_credential(record)
    assert result is False


def test_T11_receive_filters_private_fields(tmp_data_dir: Path) -> None:
    """T11 : receive_credential() filtre les champs privés avant stockage."""
    from src.artcb.security.webauthn_store import receive_credential, load_credentials
    record = {
        "credential_id": "receive_test_002",
        "cose_b64": "pQECAyYgASFY",
        "wallet_name": "carol-wallet",
        "_private_key": "NEVER_STORED",
        "_source_node_id": "ovh-node-4",  # champ fanout — pas dans PUBLIC_FIELDS
    }
    receive_credential(record)
    stored = [c for c in load_credentials() if c.get("credential_id") == "receive_test_002"]
    assert len(stored) == 1
    assert "_private_key" not in stored[0]
    assert "_source_node_id" not in stored[0]


def test_T12_receive_idempotent(tmp_data_dir: Path) -> None:
    """T12 : receive_credential() est idempotent — deux appels avec le même credential_id."""
    from src.artcb.security.webauthn_store import receive_credential, load_credentials
    record = {
        "credential_id": "receive_idempotent_001",
        "cose_b64": "pQECAyYgASFY",
        "wallet_name": "dave-wallet",
    }
    receive_credential(record)
    receive_credential(record)  # deuxième appel
    stored = [c for c in load_credentials() if c.get("credential_id") == "receive_idempotent_001"]
    # Un seul enregistrement — save_credential() déduplique par credential_id
    assert len(stored) == 1


# ─── T13-T15 : Route HTTP /webauthn/identity/receive ─────────────────────────

def test_T13_receive_route_ok(tmp_data_dir: Path) -> None:
    """T13 : POST /api/v1/auth/webauthn/identity/receive retourne 200 + stored=True."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from src.api.webauthn_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    payload = {
        "credential_id": "route_test_001",
        "cose_b64": "pQECAyYgASFYIIABC",
        "wallet_name": "eve-wallet",
        "address": "artcb1eve",
        "modality": "fingerprint",
        "rp_id": "artcb.me",
        "sign_count": 0,
    }
    resp = client.post(
        "/api/v1/auth/webauthn/identity/receive",
        json=payload,
        headers={"X-ARTCB-Fanout-Source": "ovh-node-2"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["stored"] is True
    assert data["wallet_name"] == "eve-wallet"
    assert data["source_node"] == "ovh-node-2"
    assert data["credential_id_prefix"] == "route_test_001"[:12]


def test_T14_receive_route_missing_field(tmp_data_dir: Path) -> None:
    """T14 : POST sans cose_b64 → 422 (validation Pydantic)."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from src.api.webauthn_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    payload = {
        "credential_id": "route_test_002",
        # cose_b64 manquant
        "wallet_name": "frank-wallet",
    }
    resp = client.post("/api/v1/auth/webauthn/identity/receive", json=payload)
    assert resp.status_code == 422  # Pydantic validation error


def test_T15_broadcast_disabled_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """T15 : broadcast_credential() retourne {} immédiatement si fanout désactivé."""
    monkeypatch.setenv("ARTCB_WEBAUTHN_FANOUT_DISABLED", "1")
    from src.artcb.security.webauthn_store import broadcast_credential
    result = broadcast_credential(SAMPLE_CREDENTIAL)
    assert result == {}
