"""Tests intégration pool — private / public / group bout en bout (nœud unique)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")
    return TestClient(create_app())


def _wallet(client: TestClient, name: str = "pool_wallet") -> dict:
    # Wallet système — password requis depuis rapport 107 (chiffrement clé privée)
    r = client.post("/api/v1/wallet/create", json={"name": name, "password": "test_pwd_123"})
    assert r.status_code == 200, r.text
    return r.json()


def _run_local_pool_finalize(client: TestClient, visibility: str, group_id: str | None = None) -> dict:
    w = _wallet(client)
    text = (
        "Intégration pool ARTCB. Texte suffisamment long pour découpage en morceaux "
        "chiffrés ML-KEM et validation finalize avec bloc PoL gravé localement."
    )
    body = {
        "text": text,
        "use_distributed_pool": True,
        "encrypt_transport": True,
        "visibility": visibility,
        "actor_address": w["address"],
        "wallet_name": "pool_wallet",
        "wallet_password": "test_pwd_123",
        "auto_finalize": True,
        "chunk_chars": 120,
    }
    if group_id:
        body["group_id"] = group_id
    r = client.post("/api/v1/pool/run", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "distributed_pool"
    assert data["encrypted_transport"] is True
    assert data["job_status"] == "completed"
    assert data["block_index"] is not None
    return data


def test_pool_run_local_private(client: TestClient) -> None:
    out = _run_local_pool_finalize(client, "private")
    assert out["visibility"] == "private"


def test_pool_run_local_public(client: TestClient) -> None:
    out = _run_local_pool_finalize(client, "public")
    assert out["visibility"] == "public"
    blocks = client.get("/api/v1/p2p/blocks/public").json()["blocks"]
    assert any(b.get("visibility") == "public" for b in blocks)


def test_pool_run_local_group(client: TestClient) -> None:
    w = _wallet(client, "founder_wallet")
    login = client.post("/api/v1/auth/login", json={"name": "founder_wallet", "password": "test_pwd_123"})
    assert login.status_code == 200, login.text
    g = client.post(
        "/api/v1/groups",
        json={"name": "Pool Group", "founder_address": w["address"]},
        headers={"Authorization": f"Bearer {login.json()['session_token']}"},
    )
    assert g.status_code == 200, g.text
    group_id = g.json()["group_id"]
    text = (
        "Intégration pool groupe ARTCB. Texte long pour chunks chiffrés "
        "et finalize bloc groupe avec membre fondateur."
    )
    r = client.post(
        "/api/v1/pool/run",
        json={
            "text": text,
            "use_distributed_pool": True,
            "encrypt_transport": True,
            "visibility": "group",
            "group_id": group_id,
            "actor_address": w["address"],
            "wallet_name": "founder_wallet",
            "wallet_password": "test_pwd_123",
            "auto_finalize": True,
            "chunk_chars": 120,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["job_status"] == "completed"
    assert data["group_id"] == group_id


def test_pool_run_local_mode_no_network(client: TestClient) -> None:
    w = _wallet(client, "local_wallet")
    r = client.post(
        "/api/v1/pool/run",
        json={
            "text": "Calcul local sans pool distribué — reste sur machine.",
            "use_distributed_pool": False,
            "visibility": "private",
            "actor_address": w["address"],
            "wallet_name": "local_wallet",
            "wallet_password": "test_pwd_123",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "local"
    assert data["encrypted_transport"] is False
    assert data["block_index"] is not None


def test_pool_rejects_unencrypted_distributed(client: TestClient) -> None:
    r = client.post(
        "/api/v1/pool/run",
        json={
            "text": "Tentative distribué sans chiffrement.",
            "use_distributed_pool": True,
            "encrypt_transport": False,
            "visibility": "private",
        },
    )
    assert r.status_code == 400
    assert "chiffrement" in r.json()["detail"].lower()


def test_pool_preferences_roundtrip(client: TestClient) -> None:
    r = client.put(
        "/api/v1/pool/preferences",
        json={"use_distributed_pool": True, "encrypt_transport": True, "default_visibility": "public"},
    )
    assert r.status_code == 200, r.text
    prefs = client.get("/api/v1/pool/preferences").json()["preferences"]
    assert prefs["use_distributed_pool"] is True
    assert prefs["default_visibility"] == "public"


def test_mining_pipeline_distributed_flag(client: TestClient) -> None:
    w = _wallet(client, "pipe_wallet")
    r = client.post(
        "/api/v1/mining/pipeline",
        json={
            "text": "Pipeline mining avec flag pool distribué chiffré ML-KEM intégré.",
            "use_distributed_pool": True,
            "encrypt_transport": True,
            "visibility": "private",
            "actor_address": w["address"],
            "wallet_name": "pipe_wallet",
            "wallet_password": "test_pwd_123",
            "auto_finalize": True,
            "chunk_chars": 150,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "distributed_pool"
