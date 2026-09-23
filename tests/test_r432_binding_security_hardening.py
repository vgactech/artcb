"""Tests R432 — Durcissement sécurité WalletDeviceBindingStore.

Problèmes traités (audit R431) :
  P1 — actor spoofable : authenticated_actor provient du token serveur, pas du body
  P2 — chemins concurrents : séparation REVOKE / PURGE
  P3 — atomicité : _write_atomic (tmp + rename + flock)
  P4 — version/CAS : champ version + expected_version dans revoke_with_history

Cas de tests T01→T12 :
  T01 — authenticated_actor est bien écrit dans revocation_actor (pas requested_actor)
  T02 — requested_actor du body est enregistré séparément (champ distinct)
  T03 — _extract_authenticated_actor extrait le label du token correctement
  T04 — Champ version présent et vaut 1 à la création
  T05 — version incrémenté de 1 à 2 après révocation
  T06 — expected_version correct → révocation OK
  T07 — expected_version incorrect → BindingRevocationError (CAS)
  T08 — purge_binding sur REVOKED → succès + journal forensic
  T09 — purge_binding sur ACTIVE → BindingPurgeError
  T10 — purge_binding sans reason → BindingPurgeError
  T11 — purge_binding écrit le journal avant la suppression physique
  T12 — Non-régression : T01→T09 de R431 fonctionnent toujours

MODE DEBUG actif.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.api.admin_device_binding_routes import _extract_authenticated_actor
from src.artcb.security.wallet_device_binding import (
    BindingPurgeError,
    BindingRevocationError,
    BindingState,
    WalletDeviceBindingStore,
)


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> WalletDeviceBindingStore:
    return WalletDeviceBindingStore(tmp_path)


def _bind(store: WalletDeviceBindingStore, wallet: str, fp: str) -> None:
    store.check_and_bind(wallet_name=wallet, device_fingerprint=fp,
                         env_type="test", wallet_namespace="PRODUCTION")


# ── T01 — authenticated_actor → revocation_actor ────────────────────────────

def test_t01_authenticated_actor_stored_in_revocation_actor(store: WalletDeviceBindingStore) -> None:
    """T01 — revocation_actor doit être authenticated_actor (token serveur)."""
    _bind(store, "wallet-p1", "fp-p1")
    result = store.revoke_with_history(
        wallet_name="wallet-p1",
        authenticated_actor="operator-node-N2",
        requested_actor="alice",
        reason="T01",
    )
    assert result["new_state"]["revocation_actor"] == "operator-node-N2"


# ── T02 — requested_actor stocké séparément ───────────────────────────────────

def test_t02_requested_actor_stored_separately(store: WalletDeviceBindingStore) -> None:
    """T02 — requested_actor (body client) est dans un champ distinct."""
    _bind(store, "wallet-p2", "fp-p2")
    result = store.revoke_with_history(
        wallet_name="wallet-p2",
        authenticated_actor="server-key",
        requested_actor="charlie",
        reason="T02",
    )
    assert result["new_state"]["requested_actor"] == "charlie"
    assert result["new_state"]["revocation_actor"] == "server-key"
    # Les deux champs sont distincts — requested_actor ne peut pas masquer authenticated
    assert result["new_state"]["revocation_actor"] != result["new_state"]["requested_actor"]


# ── T03 — _extract_authenticated_actor ───────────────────────────────────────

def test_t03_extract_authenticated_actor_from_token_dict() -> None:
    """T03 — _extract_authenticated_actor extrait la bonne valeur du dict token."""
    # wallet_name prioritaire
    assert _extract_authenticated_actor({"wallet_name": "my-wallet", "label": "x"}) == "my-wallet"
    # label si pas de wallet_name
    assert _extract_authenticated_actor({"label": "op-label"}) == "op-label"
    # address si pas de wallet_name ni label
    assert _extract_authenticated_actor({"address": "addr-xyz"}) == "addr-xyz"
    # kind si rien d'autre
    assert _extract_authenticated_actor({"kind": "operator"}) == "operator"
    # fallback
    assert _extract_authenticated_actor({}) == "operator"
    # None → anonymous
    assert _extract_authenticated_actor(None) == "anonymous"


# ── T04 — version = 1 à la création ──────────────────────────────────────────

def test_t04_version_is_1_on_creation(store: WalletDeviceBindingStore) -> None:
    """T04 — Champ version présent et vaut 1 après création."""
    _bind(store, "wallet-v4", "fp-v4")
    record = store.list_bindings()[0]
    assert record.get("version") == 1, f"Attendu version=1, obtenu {record.get('version')}"


# ── T05 — version incrémenté après révocation ────────────────────────────────

def test_t05_version_incremented_after_revocation(store: WalletDeviceBindingStore) -> None:
    """T05 — version passe de 1 à 2 après révocation."""
    _bind(store, "wallet-v5", "fp-v5")
    result = store.revoke_with_history(
        wallet_name="wallet-v5",
        authenticated_actor="server",
        reason="T05",
    )
    assert result["version_before"] == 1
    assert result["version_after"] == 2
    assert result["new_state"]["version"] == 2


# ── T06 — CAS correct → révocation OK ────────────────────────────────────────

def test_t06_cas_correct_version_allows_revocation(store: WalletDeviceBindingStore) -> None:
    """T06 — expected_version=1 correct → révocation réussie."""
    _bind(store, "wallet-v6", "fp-v6")
    result = store.revoke_with_history(
        wallet_name="wallet-v6",
        authenticated_actor="server",
        reason="T06",
        expected_version=1,
    )
    assert result["new_state"]["state"] == BindingState.REVOKED
    assert result["version_after"] == 2


# ── T07 — CAS incorrect → BindingRevocationError ─────────────────────────────

def test_t07_cas_wrong_version_raises_error(store: WalletDeviceBindingStore) -> None:
    """T07 — expected_version=99 (mauvais) → BindingRevocationError (CAS)."""
    _bind(store, "wallet-v7", "fp-v7")
    with pytest.raises(BindingRevocationError, match="Conflit de version"):
        store.revoke_with_history(
            wallet_name="wallet-v7",
            authenticated_actor="server",
            reason="T07",
            expected_version=99,  # mauvais
        )


# ── T08 — purge_binding sur REVOKED → succès + journal ───────────────────────

def test_t08_purge_revoked_binding_succeeds_and_logs(store: WalletDeviceBindingStore) -> None:
    """T08 — purge_binding d'un binding REVOKED réussit et écrit le journal forensic."""
    _bind(store, "wallet-p8", "fp-p8")
    rev = store.revoke_with_history(
        wallet_name="wallet-p8",
        authenticated_actor="server",
        reason="pre-purge",
    )
    bid = rev["binding_id"]

    purge_result = store.purge_binding(
        binding_id=bid,
        authenticated_actor="server",
        purge_reason="GDPR deletion T08",
    )

    assert purge_result["binding_id"] == bid
    assert purge_result["purge_id"] is not None
    assert purge_result["authenticated_actor"] == "server"
    assert purge_result["purge_reason"] == "GDPR deletion T08"

    # Enregistrement physiquement absent après purge
    assert store.get_binding_by_id(bid) is None

    # Journal forensic présent
    log = store.list_purge_log()
    assert any(e["binding_id"] == bid for e in log)


# ── T09 — purge_binding sur ACTIVE → BindingPurgeError ───────────────────────

def test_t09_purge_active_binding_raises_error(store: WalletDeviceBindingStore) -> None:
    """T09 — purge_binding d'un binding ACTIVE est rejeté."""
    _bind(store, "wallet-p9", "fp-p9")
    bid = store.list_bindings()[0]["binding_id"]

    with pytest.raises(BindingPurgeError, match="REVOKED"):
        store.purge_binding(
            binding_id=bid,
            authenticated_actor="server",
            purge_reason="T09 test",
        )
    # Le binding est toujours ACTIVE après le refus
    assert store.get_binding_by_id(bid)["state"] == BindingState.ACTIVE


# ── T10 — purge_binding sans reason → BindingPurgeError ──────────────────────

def test_t10_purge_without_reason_raises_error(store: WalletDeviceBindingStore) -> None:
    """T10 — purge_binding avec purge_reason vide → BindingPurgeError."""
    _bind(store, "wallet-p10", "fp-p10")
    rev = store.revoke_with_history(wallet_name="wallet-p10", authenticated_actor="server")
    bid = rev["binding_id"]

    with pytest.raises(BindingPurgeError, match="obligatoire"):
        store.purge_binding(
            binding_id=bid,
            authenticated_actor="server",
            purge_reason="",  # vide → refus
        )


# ── T11 — journal forensic écrit AVANT la suppression physique ───────────────

def test_t11_purge_log_written_before_physical_delete(store: WalletDeviceBindingStore,
                                                       tmp_path: Path) -> None:
    """T11 — binding_purge_log.json contient le snapshot du binding avant suppression."""
    _bind(store, "wallet-p11", "fp-p11")
    rev = store.revoke_with_history(wallet_name="wallet-p11", authenticated_actor="server")
    bid = rev["binding_id"]

    store.purge_binding(binding_id=bid, authenticated_actor="server", purge_reason="T11")

    log = store.list_purge_log()
    entry = next((e for e in log if e["binding_id"] == bid), None)
    assert entry is not None, "L'entrée de purge doit être dans le journal"
    assert entry["snapshot"]["wallet_name"] == "wallet-p11"
    assert entry["snapshot"]["state"] == BindingState.REVOKED
    assert entry["snapshot"]["device_fingerprint"] == "fp-p11"
    assert "purged_at" in entry
    assert "purge_id" in entry


# ── T12 — Non-régression R431 (T01→T06 de l'ancienne suite) ─────────────────

def test_t12_r431_non_regression(store: WalletDeviceBindingStore) -> None:
    """T12 — Les invariants fondamentaux R431 sont maintenus après R432."""
    _bind(store, "wallet-nr", "fp-nr")

    # Révocation de base (T01 R431)
    result = store.revoke_with_history(
        wallet_name="wallet-nr",
        authenticated_actor="server",
        reason="nr-test",
    )
    assert result["new_state"]["state"] == BindingState.REVOKED

    # Enregistrement conservé (T03 R431)
    assert store.get_binding_by_id(result["binding_id"]) is not None

    # Après révocation, nouveau wallet possible sur le même device (T04 R431)
    _bind(store, "wallet-nr-v2", "fp-nr")
    active = store.list_active_bindings()
    assert any(r["wallet_name"] == "wallet-nr-v2" for r in active)

    # Double révocation refusée (T06 R431)
    with pytest.raises(BindingRevocationError, match="déjà révoqué"):
        store.revoke_with_history(wallet_name="wallet-nr", authenticated_actor="server")

    # Suppression physique R379 fonctionne toujours (T09 R431)
    store2 = WalletDeviceBindingStore(store.path.parent)
    store2.check_and_bind(wallet_name="wallet-r379", device_fingerprint="fp-r379",
                           env_type="test", wallet_namespace="PRODUCTION")
    before = len(store2.list_bindings())
    removed = store2.admin_revoke_by_wallet("wallet-r379")
    assert removed is not None
    assert len(store2.list_bindings()) == before - 1
