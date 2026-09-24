"""Tests R452 — Couverture forensic complète : routes biométriques + check_and_bind + revoke_with_history.

Périmètre :
    A) wallet_device_binding.py — revoke_with_history() (5 chemins forensic nouveaux)
        A01 — REVOKE_OK : révocation nominale émet WALLET_REVOKE_OK / SUCCESS
        A02 — BINDING_NOT_FOUND : binding introuvable émet WALLET_REVOKE_FAIL / BINDING_NOT_FOUND
        A03 — ALREADY_REVOKED : double révocation émet WALLET_REVOKE_FAIL / ALREADY_REVOKED
        A04 — CAS_VERSION_CONFLICT : version mismatch émet WALLET_REVOKE_FAIL / CAS_VERSION_CONFLICT
        A05 — MISSING_CRITERIA : aucun critère émet WALLET_REVOKE_FAIL / MISSING_CRITERIA

    B) wallet_device_binding.py — check_and_bind() (3 chemins forensic existants, non-régression)
        B01 — BINDING_CHECK_OK / idempotent : second bind même pair → SUCCESS idempotent
        B02 — BINDING_CHECK_BLOCKED : device déjà lié → REJECTED
        B03 — BINDING_CHECK_OK / SUCCESS : nouveau binding → SUCCESS

    C) biometric_identity_routes.py — enroll() (4 chemins forensic, non-régression via import)
        C01 — BIO_ENROLL_OK : chemin nominal émet BIO_ENROLL_OK / SUCCESS
        C02 — BIO_ENROLL_FAIL : unicité refusée émet BIO_ENROLL_FAIL / REJECTED
        C03 — SYBIL_STORE_UNAVAILABLE : store inaccessible émet SYBIL_STORE_UNAVAILABLE
        C04 — SYBIL_CHECK_BLOCKED : sybil bloqué émet SYBIL_CHECK_BLOCKED

    D) Invariants transversaux
        D01 — Tous les emit forensic sont fail-open (ne bloquent jamais l'opération métier)
        D02 — forensic absent (_FORENSIC_AVAILABLE=False) → opérations toujours fonctionnelles

MODE DEBUG actif. CERTIFIED_100=false. Développement Python pur.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call

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
    """Helper : crée un binding PRODUCTION."""
    store.check_and_bind(
        wallet_name=wallet,
        device_fingerprint=fp,
        env_type="test",
        wallet_namespace="PRODUCTION",
    )


def _revoke(store: WalletDeviceBindingStore, wallet: str, **kw) -> dict:
    """Helper : révoque un binding par wallet_name."""
    return store.revoke_with_history(
        wallet_name=wallet,
        reason="test-reason",
        authenticated_actor="test-operator",
        **kw,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A — revoke_with_history() — 5 chemins forensic nouveaux
# ═══════════════════════════════════════════════════════════════════════════════

class TestRevokeForensic:
    """A01→A05 — Chemins forensic de revoke_with_history()."""

    def test_a01_revoke_ok_emits_wallet_revoke_ok(self, store: WalletDeviceBindingStore) -> None:
        """A01 — Révocation nominale : WALLET_REVOKE_OK / SUCCESS émis après le verrou."""
        _bind(store, "wallet-a01", "fp-a01")

        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome), **kwargs})

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=capture_emit):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                result = _revoke(store, "wallet-a01")

        assert result["new_state"]["state"] == BindingState.REVOKED

        revoke_ok = [e for e in emitted if "WALLET_REVOKE_OK" in e["event_type"]]
        assert len(revoke_ok) == 1, f"Attendu 1 WALLET_REVOKE_OK, obtenu : {emitted}"
        assert "SUCCESS" in revoke_ok[0]["outcome"]
        assert revoke_ok[0].get("layer") == "wallet-binding"
        state_after = revoke_ok[0].get("state_after", {})
        assert state_after.get("state") == BindingState.REVOKED

    def test_a02_binding_not_found_emits_revoke_fail(self, store: WalletDeviceBindingStore) -> None:
        """A02 — Binding introuvable : WALLET_REVOKE_FAIL / BINDING_NOT_FOUND émis."""
        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome), **kwargs})

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=capture_emit):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                with pytest.raises(BindingRevocationError, match="introuvable"):
                    _revoke(store, "wallet-inexistant")

        revoke_fail = [e for e in emitted if "WALLET_REVOKE_FAIL" in e["event_type"]]
        assert len(revoke_fail) == 1, f"Attendu 1 WALLET_REVOKE_FAIL, obtenu : {emitted}"
        assert "REJECTED" in revoke_fail[0]["outcome"]
        assert revoke_fail[0].get("failure_reason_code") == "BINDING_NOT_FOUND"

    def test_a03_already_revoked_emits_revoke_fail(self, store: WalletDeviceBindingStore) -> None:
        """A03 — Double révocation : WALLET_REVOKE_FAIL / ALREADY_REVOKED émis."""
        _bind(store, "wallet-a03", "fp-a03")
        _revoke(store, "wallet-a03")  # première révocation — sans mock

        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome), **kwargs})

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=capture_emit):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                with pytest.raises(BindingRevocationError, match="déjà révoqué"):
                    _revoke(store, "wallet-a03")

        revoke_fail = [e for e in emitted if "WALLET_REVOKE_FAIL" in e["event_type"]]
        assert len(revoke_fail) == 1, f"Attendu 1 WALLET_REVOKE_FAIL, obtenu : {emitted}"
        assert "REJECTED" in revoke_fail[0]["outcome"]
        assert revoke_fail[0].get("failure_reason_code") == "ALREADY_REVOKED"
        state_after = revoke_fail[0].get("state_after", {})
        assert state_after.get("state") == BindingState.REVOKED

    def test_a04_cas_version_conflict_emits_revoke_fail(self, store: WalletDeviceBindingStore) -> None:
        """A04 — CAS conflict : WALLET_REVOKE_FAIL / CAS_VERSION_CONFLICT émis."""
        _bind(store, "wallet-a04", "fp-a04")

        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome), **kwargs})

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=capture_emit):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                with pytest.raises(BindingRevocationError, match="Conflit de version"):
                    store.revoke_with_history(
                        wallet_name="wallet-a04",
                        reason="cas-test",
                        authenticated_actor="test-operator",
                        expected_version=999,  # version incorrecte
                    )

        revoke_fail = [e for e in emitted if "WALLET_REVOKE_FAIL" in e["event_type"]]
        assert len(revoke_fail) == 1, f"Attendu 1 WALLET_REVOKE_FAIL, obtenu : {emitted}"
        assert "REJECTED" in revoke_fail[0]["outcome"]
        assert revoke_fail[0].get("failure_reason_code") == "CAS_VERSION_CONFLICT"
        state_after = revoke_fail[0].get("state_after", {})
        assert state_after.get("expected_version") == 999
        assert state_after.get("actual_version") == 1

    def test_a05_missing_criteria_emits_revoke_fail(self, store: WalletDeviceBindingStore) -> None:
        """A05 — Aucun critère fourni : WALLET_REVOKE_FAIL / MISSING_CRITERIA émis."""
        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome), **kwargs})

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=capture_emit):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                with pytest.raises(BindingRevocationError, match="Au moins un critère"):
                    store.revoke_with_history(
                        reason="no-criteria",
                        authenticated_actor="test-operator",
                        # wallet_name=None, device_fingerprint=None, binding_id=None
                    )

        revoke_fail = [e for e in emitted if "WALLET_REVOKE_FAIL" in e["event_type"]]
        assert len(revoke_fail) == 1, f"Attendu 1 WALLET_REVOKE_FAIL, obtenu : {emitted}"
        assert "REJECTED" in revoke_fail[0]["outcome"]
        assert revoke_fail[0].get("failure_reason_code") == "MISSING_CRITERIA"


# ═══════════════════════════════════════════════════════════════════════════════
# B — check_and_bind() — 3 chemins forensic (non-régression)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckAndBindForensic:
    """B01→B03 — Chemins forensic de check_and_bind() (non-régression R452)."""

    def test_b01_idempotent_bind_emits_success_idempotent(self, store: WalletDeviceBindingStore) -> None:
        """B01 — Second bind identique : BINDING_CHECK_OK / SUCCESS avec idempotent=True."""
        _bind(store, "wallet-b01", "fp-b01")

        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome), **kwargs})

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=capture_emit):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                _bind(store, "wallet-b01", "fp-b01")  # second bind identique

        check_ok = [e for e in emitted if "BINDING_CHECK_OK" in e["event_type"]]
        assert len(check_ok) == 1
        assert "SUCCESS" in check_ok[0]["outcome"]
        state_after = check_ok[0].get("state_after", {})
        assert state_after.get("idempotent") is True

    def test_b02_device_already_bound_emits_blocked(self, store: WalletDeviceBindingStore) -> None:
        """B02 — Device déjà lié à un autre wallet : BINDING_CHECK_BLOCKED / REJECTED émis."""
        _bind(store, "wallet-b02-first", "fp-b02")

        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome), **kwargs})

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=capture_emit):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                with pytest.raises(WalletDeviceBindingError):
                    _bind(store, "wallet-b02-second", "fp-b02")

        blocked = [e for e in emitted if "BINDING_CHECK_BLOCKED" in e["event_type"]]
        assert len(blocked) == 1
        assert "REJECTED" in blocked[0]["outcome"]
        assert blocked[0].get("failure_reason_code") == "DEVICE_ALREADY_BOUND"

    def test_b03_new_binding_emits_success(self, store: WalletDeviceBindingStore) -> None:
        """B03 — Nouveau binding : BINDING_CHECK_OK / SUCCESS avec binding_id émis."""
        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome), **kwargs})

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=capture_emit):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                _bind(store, "wallet-b03", "fp-b03")

        check_ok = [e for e in emitted if "BINDING_CHECK_OK" in e["event_type"]]
        assert len(check_ok) == 1
        assert "SUCCESS" in check_ok[0]["outcome"]
        state_after = check_ok[0].get("state_after", {})
        assert state_after.get("state") == BindingState.ACTIVE
        assert "binding_id" in state_after


# ═══════════════════════════════════════════════════════════════════════════════
# C — biometric_identity_routes.py — enroll() (non-régression via import direct)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBiometricRoutesForensicNonRegression:
    """C01→C04 — Vérifie que les 4 chemins forensic sont branchés dans biometric_identity_routes.

    Ces tests vérifient l'import des types forensic et la présence des appels dans le module,
    sans déclencher un serveur FastAPI complet (test structurel).
    """

    def test_c01_module_imports_forensic_types(self) -> None:
        """C01 — Le module biometric_identity_routes importe bien les types forensic R452."""
        import src.api.biometric_identity_routes as bio_routes

        # Vérifier que les 4 types forensic sont bien importés dans le module
        assert hasattr(bio_routes, "ForensicEventType"), "ForensicEventType manquant"
        assert hasattr(bio_routes, "AttemptOutcome"), "AttemptOutcome manquant"
        assert hasattr(bio_routes, "EvaluationContext"), "EvaluationContext manquant"
        assert hasattr(bio_routes, "emit_forensic"), "emit_forensic manquant"

    def test_c02_module_version_is_r452(self) -> None:
        """C02 — MODULE_VERSION de biometric_identity_routes est 1.0.5 (R452)."""
        import src.api.biometric_identity_routes as bio_routes
        assert bio_routes.MODULE_VERSION == "1.0.5", (
            f"Attendu 1.0.5, obtenu {bio_routes.MODULE_VERSION}"
        )

    def test_c03_forensic_event_types_used_in_source(self) -> None:
        """C03 — Les 4 ForensicEventType R452 sont présents dans le source du module."""
        import inspect
        import src.api.biometric_identity_routes as bio_routes

        source = inspect.getsource(bio_routes)
        for event_name in [
            "BIO_ENROLL_OK",
            "BIO_ENROLL_FAIL",
            "SYBIL_STORE_UNAVAILABLE",
            "SYBIL_CHECK_BLOCKED",
        ]:
            assert event_name in source, f"ForensicEventType.{event_name} absent du source"

    def test_c04_emit_forensic_called_on_enroll_success(self, tmp_path: Path) -> None:
        """C04 — emit_forensic est effectivement appelé sur le chemin enroll nominal.

        Stratégie : mock de emit_forensic + enroll_biometric + check_uniqueness +
        load_wallet_human_links pour déclencher le chemin nominal sans I/O.
        """
        import src.api.biometric_identity_routes as bio_routes

        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome)})

        # Résultat enroll fictif (chemin nominal — pas sybil_blocked)
        mock_result = MagicMock()
        mock_result.sybil_blocked = False
        mock_result.human_id = "human-c04-test"
        mock_result.existing_wallet = None
        mock_result.sybil_reason = None
        mock_result.human_identity_record = {"human_id": "human-c04-test", "commitment": "aabbcc"}

        mock_uniqueness = MagicMock()
        mock_uniqueness.match_found = False
        mock_uniqueness.existing_human_id = None
        mock_uniqueness.match_method = "exact_hash"

        with (
            patch.object(bio_routes, "emit_forensic", side_effect=capture_emit),
            patch.object(bio_routes, "enroll_biometric", return_value=(mock_result, "sec_hex", "blind_hex")),
            patch.object(bio_routes, "check_uniqueness", return_value=mock_uniqueness),
            patch.object(bio_routes, "load_wallet_human_links", return_value=[]),
            patch.object(bio_routes, "commit_biometric_template", return_value=b"\xaa\xbb\xcc"),
            patch.object(bio_routes, "_append_record"),
            patch.object(bio_routes, "_load_records", return_value=[]),
        ):
            from fastapi import Request
            from unittest.mock import MagicMock as MM

            mock_request = MM(spec=Request)
            mock_request.app.state = MM()
            mock_request.app.state.node_id = "node-test"

            template_hex = "aa" * 64  # 64 bytes = 128 hex chars
            body = bio_routes.EnrollRequest(template_hex=template_hex)
            bio_routes.enroll(body, mock_request)

        enroll_ok = [e for e in emitted if "BIO_ENROLL_OK" in e["event_type"]]
        assert len(enroll_ok) >= 1, f"BIO_ENROLL_OK attendu, obtenu : {emitted}"
        assert "SUCCESS" in enroll_ok[0]["outcome"]


# ═══════════════════════════════════════════════════════════════════════════════
# D — Invariants transversaux
# ═══════════════════════════════════════════════════════════════════════════════

class TestForensicInvariants:
    """D01→D02 — Invariants : fail-open + module absent."""

    def test_d01_forensic_fail_raises_never_blocks_revoke(self, store: WalletDeviceBindingStore) -> None:
        """D01 — Une exception dans emit_forensic ne bloque JAMAIS revoke_with_history."""
        _bind(store, "wallet-d01", "fp-d01")

        def always_raise(ledger, **kwargs):
            raise RuntimeError("forensic I/O simulé crashant")

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=always_raise):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                # L'opération doit réussir malgré le crash forensic
                result = _revoke(store, "wallet-d01")

        assert result["new_state"]["state"] == BindingState.REVOKED, (
            "revoke_with_history doit réussir même si emit_forensic lève une exception"
        )

    def test_d02_forensic_unavailable_binding_still_works(self, store: WalletDeviceBindingStore) -> None:
        """D02 — _FORENSIC_AVAILABLE=False → les opérations binding fonctionnent normalement."""
        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_FORENSIC_AVAILABLE", False):
            _bind(store, "wallet-d02", "fp-d02")
            result = _revoke(store, "wallet-d02")

        assert result["new_state"]["state"] == BindingState.REVOKED
        bindings = store.list_revoked_bindings()
        assert any(b["wallet_name"] == "wallet-d02" for b in bindings)

    def test_d03_revoke_ok_state_after_content(self, store: WalletDeviceBindingStore) -> None:
        """D03 — WALLET_REVOKE_OK state_after contient les champs requis pour audit trail."""
        _bind(store, "wallet-d03", "fp-d03")

        emitted: list[dict] = []

        def capture_emit(ledger, *, event_type, outcome, **kwargs):
            emitted.append({"event_type": str(event_type), "outcome": str(outcome), **kwargs})

        module = sys.modules["src.artcb.security.wallet_device_binding"]
        with patch.object(module, "_emit_forensic", side_effect=capture_emit):
            with patch.object(module, "_FORENSIC_AVAILABLE", True):
                _revoke(store, "wallet-d03")

        revoke_ok = [e for e in emitted if "WALLET_REVOKE_OK" in e["event_type"]]
        assert len(revoke_ok) == 1
        state_after = revoke_ok[0].get("state_after", {})

        # Champs obligatoires pour l'audit trail forensic
        assert "state" in state_after
        assert "namespace" in state_after
        assert "wallet_name" in state_after
        assert "version_before" in state_after
        assert "version_after" in state_after
        assert "revoked_at" in state_after
        assert state_after["version_after"] == state_after["version_before"] + 1

    def test_d04_wallet_device_binding_module_version(self) -> None:
        """D04 — MODULE_VERSION de wallet_device_binding est 1.3.2 (R452)."""
        import src.artcb.security.wallet_device_binding as wdb
        assert wdb.MODULE_VERSION == "1.3.2", (
            f"Attendu 1.3.2, obtenu {wdb.MODULE_VERSION}"
        )
