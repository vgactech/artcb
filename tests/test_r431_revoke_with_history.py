"""Tests R431 — Révocation avec historique conservé (WalletDeviceBindingStore).

9 cas T01→T09 :
  T01 — Binding actif peut être révoqué (ACTIVE → REVOKED)
  T02 — Révocation autorisée : état = REVOKED après révocation
  T03 — Binding désormais REVOKED (l'enregistrement reste dans le registre)
  T04 — Binding REVOKED n'est plus utilisable comme ACTIVE pour créer un wallet
  T05 — Révocation sans critère → BindingRevocationError (pas de cible)
  T06 — Double révocation → BindingRevocationError (comportement déterministe)
  T07 — Audit trail conservé : binding_id, created_at, wallet_name, device_fingerprint intacts
  T08 — Révocation par binding_id (prioritaire) fonctionne
  T09 — Non-régression : les DELETE physiques R379 fonctionnent toujours

MODE DEBUG actif. Développement Python pur.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

from src.artcb.security.wallet_device_binding import (
    BindingRevocationError,
    BindingState,
    WalletDeviceBindingError,
    WalletDeviceBindingStore,
)


# ── Fixture : store isolé en répertoire temporaire ────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> WalletDeviceBindingStore:
    """Retourne un WalletDeviceBindingStore vierge dans un dossier temporaire."""
    return WalletDeviceBindingStore(tmp_path)


def _bind(store: WalletDeviceBindingStore, wallet: str, fp: str) -> None:
    """Helper : crée un binding PRODUCTION sans exceptions."""
    store.check_and_bind(
        wallet_name=wallet,
        device_fingerprint=fp,
        env_type="test",
        wallet_namespace="PRODUCTION",
    )


# ── T01 — Binding actif peut être révoqué ─────────────────────────────────────

def test_t01_active_binding_can_be_revoked(store: WalletDeviceBindingStore) -> None:
    """T01 — Un binding ACTIVE peut être révoqué sans exception."""
    _bind(store, "wallet-alpha", "fp-aaa")
    result = store.revoke_with_history(wallet_name="wallet-alpha", reason="test-T01", actor="test")
    assert result["previous_state"]["state"] == BindingState.ACTIVE
    assert result["new_state"]["state"] == BindingState.REVOKED


# ── T02 — État REVOKED après révocation ───────────────────────────────────────

def test_t02_state_is_revoked_after_revocation(store: WalletDeviceBindingStore) -> None:
    """T02 — L'état du binding est REVOKED après révocation."""
    _bind(store, "wallet-beta", "fp-bbb")
    store.revoke_with_history(wallet_name="wallet-beta", reason="T02", actor="test")
    # Vérification en relisant le registre
    all_records = store.list_bindings()
    target = next((r for r in all_records if r["wallet_name"] == "wallet-beta"), None)
    assert target is not None, "L'enregistrement doit rester dans le registre"
    assert target["state"] == BindingState.REVOKED
    assert target["revoked_at"] is not None
    assert target["revocation_actor"] == "test"
    assert target["revocation_reason"] == "T02"


# ── T03 — Enregistrement conservé (pas de suppression physique) ───────────────

def test_t03_record_stays_in_registry_after_revocation(store: WalletDeviceBindingStore) -> None:
    """T03 — Après révocation, l'enregistrement reste dans le registre (audit trail)."""
    _bind(store, "wallet-gamma", "fp-ccc")
    before_count = len(store.list_bindings())

    store.revoke_with_history(wallet_name="wallet-gamma", reason="T03", actor="test")
    after_count = len(store.list_bindings())

    assert after_count == before_count, (
        f"Le nombre d'enregistrements doit rester identique : {before_count} → {after_count}"
    )
    revoked_list = store.list_revoked_bindings()
    assert any(r["wallet_name"] == "wallet-gamma" for r in revoked_list)


# ── T04 — Binding REVOKED ne bloque plus la création d'un nouveau wallet ──────

def test_t04_revoked_binding_allows_new_wallet_creation(store: WalletDeviceBindingStore) -> None:
    """T04 — Après révocation, le même device peut créer un nouveau wallet."""
    _bind(store, "wallet-delta", "fp-ddd")
    store.revoke_with_history(wallet_name="wallet-delta", reason="T04", actor="test")

    # Sans révocation, la 2e liaison avec fp-ddd pour un autre wallet lèverait WalletDeviceBindingError
    # Après révocation, elle doit réussir
    _bind(store, "wallet-delta-v2", "fp-ddd")
    active = store.list_active_bindings()
    names = [r["wallet_name"] for r in active]
    assert "wallet-delta-v2" in names, "Le nouveau wallet doit être ACTIVE"
    assert "wallet-delta" not in names, "L'ancien wallet doit être REVOKED, absent des ACTIVE"


# ── T05 — Révocation sans critère → BindingRevocationError ───────────────────

def test_t05_revocation_without_criteria_raises_error(store: WalletDeviceBindingStore) -> None:
    """T05 — revoke_with_history() sans critère lève BindingRevocationError."""
    with pytest.raises(BindingRevocationError, match="Au moins un critère"):
        store.revoke_with_history()


# ── T06 — Double révocation → comportement déterministe ──────────────────────

def test_t06_double_revocation_raises_error(store: WalletDeviceBindingStore) -> None:
    """T06 — Révoquer un binding déjà REVOKED lève BindingRevocationError (409)."""
    _bind(store, "wallet-epsilon", "fp-eee")
    store.revoke_with_history(wallet_name="wallet-epsilon", reason="première", actor="test")

    with pytest.raises(BindingRevocationError, match="déjà révoqué"):
        store.revoke_with_history(wallet_name="wallet-epsilon", reason="deuxième", actor="test")


# ── T07 — Audit trail : champs critiques conservés intacts ───────────────────

def test_t07_audit_trail_fields_preserved(store: WalletDeviceBindingStore) -> None:
    """T07 — binding_id, wallet_name, device_fingerprint, created_at sont conservés après révocation."""
    _bind(store, "wallet-zeta", "fp-zzz")

    # Récupérer l'enregistrement avant révocation
    before = store.list_bindings()[0]
    binding_id_before = before["binding_id"]
    created_at_before = before["created_at"]

    result = store.revoke_with_history(wallet_name="wallet-zeta", reason="T07", actor="auditor")
    after = result["new_state"]

    assert after["binding_id"] == binding_id_before, "binding_id doit être conservé"
    assert after["wallet_name"] == "wallet-zeta", "wallet_name doit être conservé"
    assert after["device_fingerprint"] == "fp-zzz", "device_fingerprint doit être conservé"
    assert after["created_at"] == created_at_before, "created_at doit être conservé"
    assert after["revocation_actor"] == "auditor"
    assert after["revocation_reason"] == "T07"
    assert after["revoked_at"] is not None


# ── T08 — Révocation par binding_id ───────────────────────────────────────────

def test_t08_revoke_by_binding_id(store: WalletDeviceBindingStore) -> None:
    """T08 — La révocation par binding_id (UUID) sélectionne le bon enregistrement."""
    _bind(store, "wallet-eta", "fp-hhh")
    _bind(store, "wallet-theta", "fp-iii")  # 2e binding pour s'assurer du bon ciblage

    all_records = store.list_bindings()
    target_id = next(r["binding_id"] for r in all_records if r["wallet_name"] == "wallet-eta")

    result = store.revoke_with_history(binding_id=target_id, reason="T08", actor="test")

    assert result["binding_id"] == target_id
    assert result["new_state"]["wallet_name"] == "wallet-eta"
    assert result["new_state"]["state"] == BindingState.REVOKED

    # wallet-theta doit rester ACTIVE
    active = store.list_active_bindings()
    assert any(r["wallet_name"] == "wallet-theta" for r in active)


# ── T09 — Non-régression : DELETE physiques R379 fonctionnent toujours ────────

def test_t09_r379_physical_delete_still_works(store: WalletDeviceBindingStore) -> None:
    """T09 — Les méthodes admin_revoke_* R379 (suppression physique) fonctionnent toujours."""
    _bind(store, "wallet-iota", "fp-jjj")
    before_count = len(store.list_bindings())

    removed = store.admin_revoke_by_wallet("wallet-iota")

    assert removed is not None, "admin_revoke_by_wallet doit retourner l'enregistrement supprimé"
    assert removed["wallet_name"] == "wallet-iota"
    after_count = len(store.list_bindings())
    assert after_count == before_count - 1, "La suppression physique R379 doit réduire le registre"

    # Double appel → None (idempotence R379)
    assert store.admin_revoke_by_wallet("wallet-iota") is None
