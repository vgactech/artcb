"""Tests hardware identity + wallet device binding (anti-fraude)."""

from __future__ import annotations

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.security.hardware_identity import (
    compute_device_fingerprint,
    collect_device_identity,
    DeviceIdentityStore,
    _detect_env_type,
    _read_machine_id,
)
from artcb.security.wallet_device_binding import (
    WalletDeviceBindingStore,
    WalletDeviceBindingError,
)


# ── Tests hardware_identity ──────────────────────────────────────────────────

def test_compute_fingerprint_deterministic():
    """Le même jeu d'entrées produit toujours le même fingerprint."""
    fp1 = compute_device_fingerprint(
        machine_id="test-machine-id",
        hostname="test-host",
        platform_system="Linux",
        tpm_ek_cert_hash=None,
        env_type="local",
    )
    fp2 = compute_device_fingerprint(
        machine_id="test-machine-id",
        hostname="test-host",
        platform_system="Linux",
        tpm_ek_cert_hash=None,
        env_type="local",
    )
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


def test_compute_fingerprint_different_inputs():
    """Des entrées différentes produisent des fingerprints différents."""
    fp1 = compute_device_fingerprint(
        machine_id="machine-A",
        hostname="host-A",
        platform_system="Linux",
        tpm_ek_cert_hash=None,
        env_type="local",
    )
    fp2 = compute_device_fingerprint(
        machine_id="machine-B",
        hostname="host-B",
        platform_system="Linux",
        tpm_ek_cert_hash=None,
        env_type="local",
    )
    assert fp1 != fp2


def test_tpm_in_fingerprint_changes_hash():
    """Un fingerprint avec TPM est différent d'un sans TPM."""
    fp_no_tpm = compute_device_fingerprint(
        machine_id="mid", hostname="h", platform_system="Linux",
        tpm_ek_cert_hash=None, env_type="local",
    )
    fp_with_tpm = compute_device_fingerprint(
        machine_id="mid", hostname="h", platform_system="Linux",
        tpm_ek_cert_hash="a" * 64, env_type="local",
    )
    assert fp_no_tpm != fp_with_tpm


def test_collect_device_identity_runs():
    """collect_device_identity() ne lève pas d'exception."""
    identity = collect_device_identity()
    assert identity.device_fingerprint
    assert len(identity.device_fingerprint) == 64
    assert identity.env_type in ("local", "replit", "docker", "github_actions", "linux_headless", "unknown")
    assert identity.platform_system in ("Linux", "Windows", "Darwin", "")


def test_device_identity_store_persist(tmp_path: Path):
    """DeviceIdentityStore persiste et recharge l'identité."""
    store = DeviceIdentityStore(tmp_path)
    identity1 = store.load_or_create()
    identity2 = store.load_or_create()
    # Même fingerprint après rechargement
    assert identity1.device_fingerprint == identity2.device_fingerprint
    # Fichier créé avec perms 600
    path = tmp_path / "node_device.json"
    assert path.is_file()
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_read_machine_id_returns_string_or_none():
    """_read_machine_id() retourne une chaîne ou None sans lever d'exception."""
    result = _read_machine_id()
    assert result is None or isinstance(result, str)
    if result:
        assert len(result) > 0


def test_detect_env_type_local():
    """En dehors de Replit/Docker/CI, l'env est local ou linux_headless."""
    env = _detect_env_type()
    assert env in ("local", "linux_headless", "github_actions", "replit", "docker")


# ── Tests wallet_device_binding ──────────────────────────────────────────────

def test_binding_first_wallet_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Le premier wallet est toujours accepté."""
    monkeypatch.delenv("ARTCB_ALLOW_MULTI_WALLET", raising=False)
    monkeypatch.delenv("ARTCB_BOOTSTRAP_NODE", raising=False)
    store = WalletDeviceBindingStore(tmp_path)
    # Ne doit pas lever d'exception
    store.check_and_bind(
        wallet_name="alice",
        device_fingerprint="a" * 64,
        env_type="local",
    )
    bindings = store.list_bindings()
    assert len(bindings) == 1
    assert bindings[0]["wallet_name"] == "alice"


def test_binding_second_wallet_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Le deuxième wallet sur le même appareil est rejeté."""
    monkeypatch.delenv("ARTCB_ALLOW_MULTI_WALLET", raising=False)
    monkeypatch.delenv("ARTCB_BOOTSTRAP_NODE", raising=False)
    store = WalletDeviceBindingStore(tmp_path)
    store.check_and_bind(wallet_name="alice", device_fingerprint="b" * 64, env_type="local")
    with pytest.raises(WalletDeviceBindingError, match="alice"):
        store.check_and_bind(wallet_name="bob", device_fingerprint="b" * 64, env_type="local")


def test_binding_different_devices_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Deux wallets sur des appareils différents sont acceptés."""
    monkeypatch.delenv("ARTCB_ALLOW_MULTI_WALLET", raising=False)
    monkeypatch.delenv("ARTCB_BOOTSTRAP_NODE", raising=False)
    store = WalletDeviceBindingStore(tmp_path)
    store.check_and_bind(wallet_name="alice", device_fingerprint="c" * 64, env_type="local")
    store.check_and_bind(wallet_name="bob", device_fingerprint="d" * 64, env_type="local")
    assert len(store.list_bindings()) == 2


def test_binding_disabled_by_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """ARTCB_ALLOW_MULTI_WALLET=true désactive le check (dev/tests)."""
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    monkeypatch.delenv("ARTCB_BOOTSTRAP_NODE", raising=False)
    store = WalletDeviceBindingStore(tmp_path)
    store.check_and_bind(wallet_name="alice", device_fingerprint="e" * 64, env_type="local")
    # Pas d'exception — multi-wallet autorisé
    store.check_and_bind(wallet_name="bob", device_fingerprint="e" * 64, env_type="local")


def test_binding_disabled_by_bootstrap_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """ARTCB_BOOTSTRAP_NODE=true exemptémise le check (nœud bootstrap)."""
    monkeypatch.delenv("ARTCB_ALLOW_MULTI_WALLET", raising=False)
    monkeypatch.setenv("ARTCB_BOOTSTRAP_NODE", "true")
    store = WalletDeviceBindingStore(tmp_path)
    store.check_and_bind(wallet_name="n1_wallet", device_fingerprint="f" * 64, env_type="replit")
    store.check_and_bind(wallet_name="n2_wallet", device_fingerprint="f" * 64, env_type="replit")


def test_binding_get_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """get_binding() retrouve le record existant."""
    monkeypatch.delenv("ARTCB_ALLOW_MULTI_WALLET", raising=False)
    monkeypatch.delenv("ARTCB_BOOTSTRAP_NODE", raising=False)
    store = WalletDeviceBindingStore(tmp_path)
    store.check_and_bind(wallet_name="alice", device_fingerprint="g" * 64, env_type="local")
    record = store.get_binding("g" * 64)
    assert record is not None
    assert record["wallet_name"] == "alice"
    assert store.get_binding("z" * 64) is None


# ── Tests API wallet/create avec device binding ──────────────────────────────

@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    # Désactivé en test (chaque test a son propre tmp_path)
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    return TestClient(create_app())


def test_wallet_create_returns_device_info(client: TestClient):
    """POST /wallet/create retourne les informations normales (mode multi-wallet activé)."""
    r = client.post("/api/v1/wallet/create", json={"name": "hw_test", "password": "test_pwd_123"})
    assert r.status_code in (200, 409), r.text
    if r.status_code == 200:
        assert "address" in r.json()
        assert "seed_hex" in r.json()


def test_p2p_register_public_valid(client: TestClient):
    """POST /api/v1/p2p/register-public enregistre un nœud avec une URL valide."""
    r = client.post("/api/v1/p2p/register-public", json={
        "node_public_url": "https://demo-app--someuser.replit.app",
        "node_label": "Test Node",
        "device_fingerprint": "a" * 64,
        "github_repository": "testuser/test-repo",
        "network_id": "artcb-mainnet-1",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["registered"] is True
    assert data["peer_id"].startswith("peer_")


def test_p2p_register_public_invalid_url(client: TestClient):
    """POST /api/v1/p2p/register-public rejette une URL invalide."""
    r = client.post("/api/v1/p2p/register-public", json={
        "node_public_url": "ftp://invalid",
        "device_fingerprint": "b" * 64,
        "network_id": "artcb-mainnet-1",
    })
    assert r.status_code == 400


def test_p2p_register_public_wrong_network(client: TestClient):
    """POST /api/v1/p2p/register-public rejette un réseau inconnu."""
    r = client.post("/api/v1/p2p/register-public", json={
        "node_public_url": "https://node.example.com",
        "device_fingerprint": "c" * 64,
        "network_id": "bitcoin-mainnet",
    })
    assert r.status_code == 400
