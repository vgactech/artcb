"""Tests TASK-001-BIOMETRIE-SUITE — Politique identité humaine multi-appareil (R373, 2026-09-18).

Couvre :
  S01 : UserVerificationMethod — UV=false → NONE
  S02 : UserVerificationMethod — UV=true + déclaré "biometric" → BIOMETRIC
  S03 : UserVerificationMethod — UV=true + déclaré "pin" → PIN
  S04 : UserVerificationMethod — UV=true + aucune info → UNKNOWN
  S05 : UserVerificationMethod — implies_unique_human() toujours False
  S06 : HumanIdentityStatus — assertion invalide → UNVERIFIED
  S07 : HumanIdentityStatus — assertion valide + UV=false → DEVICE_VERIFIED
  S08 : HumanIdentityStatus — assertion valide + UV=UNKNOWN → AUTHENTICATOR_VERIFIED
  S09 : HumanIdentityStatus — assertion valide + UV=BIOMETRIC → BIOMETRIC_CLAIMED
  S10 : wallet_per_human_limit — aucun wallet existant → autorisé
  S11 : wallet_per_human_limit — wallet actif existant → refusé CASE_3
  S12 : classify_device_scenario — CASE_1 même humain/même appareil
  S13 : classify_device_scenario — CASE_2 même humain/nouvel appareil (ADD_DEVICE)
  S14 : classify_device_scenario — CASE_3 même humain/tentative multi-wallet
  S15 : classify_device_scenario — CASE_4 autre humain/appareil connu
  S16 : classify_device_scenario — CASE_5 PIN seul
  S17 : evaluate_wallet_creation — aucun human_id → autorisé
  S18 : evaluate_wallet_creation — human_id + wallet existant → refusé
  S19 : evaluate_wallet_creation — uv_method=PIN → warning dans response
  S20 : wallet_human_link — save + load round-trip
  S21 : unique_human_proven toujours False dans tous les scénarios
  S22 : CASE_5 — PIN valide WebAuthn n'autorise pas création wallet économique (strict)
  S23 : matrice complète — 5 cas × wallet_action attendu
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artcb.identity.human_identity_policy import (
    UserVerificationMethod,
    HumanIdentityStatus,
    WalletCreationDecision,
    DeviceScenario,
    WalletCreationPolicy,
    check_wallet_per_human_limit,
    classify_device_scenario,
    evaluate_wallet_creation,
    load_wallet_human_links,
    save_wallet_human_link,
    WALLET_PER_HUMAN_LIMIT,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Répertoire data temporaire isolé pour chaque test."""
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
    return tmp_path


# ─── S01 : UV=false → NONE ────────────────────────────────────────────────────

def test_S01_uv_false_gives_none() -> None:
    """S01 : user_verified=False → UserVerificationMethod.NONE."""
    m = UserVerificationMethod.from_authenticator_flags(user_verified=False)
    assert m == UserVerificationMethod.NONE


# ─── S02 : UV=true + biometric déclaré → BIOMETRIC ───────────────────────────

def test_S02_uv_biometric_declared() -> None:
    """S02 : user_verified=True + declared biometric → BIOMETRIC."""
    for declared in ("biometric", "fingerprint", "face", "FaceID", "TouchID"):
        m = UserVerificationMethod.from_authenticator_flags(
            user_verified=True, declared_method=declared
        )
        assert m == UserVerificationMethod.BIOMETRIC, f"Échec pour declared={declared!r}"


# ─── S03 : UV=true + PIN déclaré → PIN ───────────────────────────────────────

def test_S03_uv_pin_declared() -> None:
    """S03 : user_verified=True + declared pin → PIN."""
    for declared in ("pin", "PIN", "password", "passcode", "pattern"):
        m = UserVerificationMethod.from_authenticator_flags(
            user_verified=True, declared_method=declared
        )
        assert m == UserVerificationMethod.PIN, f"Échec pour declared={declared!r}"


# ─── S04 : UV=true + aucune info → UNKNOWN ───────────────────────────────────

def test_S04_uv_true_no_info_gives_unknown() -> None:
    """S04 : user_verified=True, pas de déclaration → UNKNOWN (conservateur R372)."""
    m = UserVerificationMethod.from_authenticator_flags(user_verified=True)
    assert m == UserVerificationMethod.UNKNOWN


# ─── S05 : implies_unique_human() toujours False ─────────────────────────────

def test_S05_implies_unique_human_always_false() -> None:
    """S05 : aucune méthode UV n'implique unique_human prouvé (R372)."""
    for method in UserVerificationMethod:
        assert method.implies_unique_human() is False, (
            f"implies_unique_human() doit être False pour {method.value} — "
            "UV=BIOMETRIC ne prouve pas l'unicité humaine (R372, CERTIFIED_100=false)"
        )


# ─── S06 : assertion invalide → UNVERIFIED ───────────────────────────────────

def test_S06_assertion_invalid_gives_unverified() -> None:
    """S06 : assertion WebAuthn invalide → UNVERIFIED."""
    status = HumanIdentityStatus.from_webauthn_result(
        assertion_valid=False,
        user_verified=True,
        uv_method=UserVerificationMethod.BIOMETRIC,
    )
    assert status == HumanIdentityStatus.UNVERIFIED


# ─── S07 : assertion valide + UV=false → DEVICE_VERIFIED ─────────────────────

def test_S07_assertion_valid_uv_false_gives_device_verified() -> None:
    """S07 : assertion valide mais UV=false → DEVICE_VERIFIED."""
    status = HumanIdentityStatus.from_webauthn_result(
        assertion_valid=True,
        user_verified=False,
        uv_method=UserVerificationMethod.NONE,
    )
    assert status == HumanIdentityStatus.DEVICE_VERIFIED


# ─── S08 : assertion valide + UV=UNKNOWN → AUTHENTICATOR_VERIFIED ────────────

def test_S08_assertion_valid_uv_unknown_gives_authenticator_verified() -> None:
    """S08 : assertion valide + UV=UNKNOWN → AUTHENTICATOR_VERIFIED (pas BIOMETRIC)."""
    status = HumanIdentityStatus.from_webauthn_result(
        assertion_valid=True,
        user_verified=True,
        uv_method=UserVerificationMethod.UNKNOWN,
    )
    assert status == HumanIdentityStatus.AUTHENTICATOR_VERIFIED


# ─── S09 : assertion valide + UV=BIOMETRIC → BIOMETRIC_CLAIMED ───────────────

def test_S09_assertion_valid_uv_biometric_gives_biometric_claimed() -> None:
    """S09 : assertion valide + UV=BIOMETRIC → BIOMETRIC_CLAIMED (auto-déclaré, pas certifié)."""
    status = HumanIdentityStatus.from_webauthn_result(
        assertion_valid=True,
        user_verified=True,
        uv_method=UserVerificationMethod.BIOMETRIC,
    )
    assert status == HumanIdentityStatus.BIOMETRIC_CLAIMED
    # BIOMETRIC_CLAIMED ≠ HUMAN_VERIFIED ≠ UNIQUE_HUMAN_VERIFIED
    assert status != HumanIdentityStatus.HUMAN_VERIFIED
    assert status != HumanIdentityStatus.UNIQUE_HUMAN_VERIFIED


# ─── S10 : wallet_per_human_limit — aucun wallet → autorisé ──────────────────

def test_S10_wallet_limit_no_existing_wallet_allowed() -> None:
    """S10 : aucun wallet existant pour ce HumanID → création autorisée."""
    decision = check_wallet_per_human_limit("human_abc123", existing_wallet_links=[])
    assert decision.allowed is True
    assert "autorisée" in decision.reason or "authorized" in decision.reason.lower()


# ─── S11 : wallet_per_human_limit — wallet actif existant → refusé ───────────

def test_S11_wallet_limit_existing_wallet_blocked() -> None:
    """S11 : wallet actif existant → CASE_3 refusé (anti-Sybil)."""
    links = [
        {"human_id": "human_abc123", "wallet_address": "artcb1walletaaa", "revoked": False}
    ]
    decision = check_wallet_per_human_limit("human_abc123", existing_wallet_links=links)
    assert decision.allowed is False
    assert decision.case_number == 3
    assert "human_wallet_limit_reached" in decision.reason
    assert decision.existing_wallet == "artcb1walletaaa"


# ─── S11b : wallet révoqué → ne compte pas ────────────────────────────────────

def test_S11b_revoked_wallet_does_not_count() -> None:
    """S11b : wallet révoqué n'est pas compté dans la limite."""
    links = [
        {"human_id": "human_abc123", "wallet_address": "artcb1walletaaa", "revoked": True}
    ]
    decision = check_wallet_per_human_limit("human_abc123", existing_wallet_links=links)
    assert decision.allowed is True


# ─── S12 : CASE_1 — même humain / même appareil ──────────────────────────────

def test_S12_case1_same_human_same_device() -> None:
    """S12 : même humain / même appareil → CASE_1 / wallet_action=allow_login."""
    scenario = classify_device_scenario(
        credential_known=True,
        human_id_known=True,
        human_has_active_wallet=True,
        assertion_valid=True,
        user_verified=True,
        uv_method=UserVerificationMethod.BIOMETRIC,
        is_new_credential=False,
    )
    assert scenario.case_number == 1
    assert scenario.wallet_action == "allow_login"
    assert scenario.unique_human_proven is False
    assert scenario.certified_100 is False


# ─── S13 : CASE_2 — même humain / nouvel appareil (ADD_DEVICE) ───────────────

def test_S13_case2_same_human_new_device() -> None:
    """S13 : même humain / nouvel appareil → CASE_2 / wallet_action=allow_add_device."""
    scenario = classify_device_scenario(
        credential_known=False,
        human_id_known=True,
        human_has_active_wallet=True,
        assertion_valid=True,
        user_verified=True,
        uv_method=UserVerificationMethod.UNKNOWN,
        is_new_credential=True,
    )
    assert scenario.case_number == 2
    assert scenario.wallet_action == "allow_add_device"
    assert scenario.unique_human_proven is False


# ─── S14 : CASE_3 — même humain / tentative multi-wallet ─────────────────────

def test_S14_case3_same_human_multi_wallet_blocked() -> None:
    """S14 : même humain + wallet existant + pas ADD_DEVICE → CASE_3 block_new_wallet."""
    scenario = classify_device_scenario(
        credential_known=True,
        human_id_known=True,
        human_has_active_wallet=True,
        assertion_valid=True,
        user_verified=True,
        uv_method=UserVerificationMethod.BIOMETRIC,
        is_new_credential=False,
    )
    # CASE_5 est prioritaire si uv_method=PIN/UNKNOWN, mais ici BIOMETRIC → CASE_1
    # Pour forcer CASE_3, on prend BIOMETRIC mais en tant que classification scenario
    # Le classifieur vérifie CASE_5 en premier, puis CASE_1. Donc avec credential_known=True,
    # human_id_known=True, is_new_credential=False, BIOMETRIC → CASE_1 (login normal).
    # CASE_3 se manifeste si on a human_id_known=True ET human_has_active_wallet=True
    # ET l'appel est une création wallet (pas un login).
    # Test réaliste : credential non connue mais human_id connu et wallet actif :
    scenario2 = classify_device_scenario(
        credential_known=False,
        human_id_known=True,
        human_has_active_wallet=True,
        assertion_valid=True,
        user_verified=True,
        uv_method=UserVerificationMethod.BIOMETRIC,
        is_new_credential=False,
    )
    assert scenario2.case_number == 3
    assert scenario2.wallet_action == "block_new_wallet"
    assert scenario2.unique_human_proven is False


# ─── S15 : CASE_4 — autre humain / appareil connu d'un autre HumanID ─────────

def test_S15_case4_other_human_known_device() -> None:
    """S15 : credential connue mais HumanID non reconnu → CASE_4."""
    scenario = classify_device_scenario(
        credential_known=True,
        human_id_known=False,  # ce human_id n'existe pas
        human_has_active_wallet=False,
        assertion_valid=True,
        user_verified=True,
        uv_method=UserVerificationMethod.UNKNOWN,
        is_new_credential=False,
    )
    assert scenario.case_number == 4
    assert scenario.wallet_action == "allow_login"
    assert scenario.unique_human_proven is False


# ─── S16 : CASE_5 — PIN seul ─────────────────────────────────────────────────

def test_S16_case5_pin_only() -> None:
    """S16 : credential connue + UV=PIN → CASE_5 (PIN seul)."""
    scenario = classify_device_scenario(
        credential_known=True,
        human_id_known=True,
        human_has_active_wallet=False,
        assertion_valid=True,
        user_verified=True,
        uv_method=UserVerificationMethod.PIN,
        is_new_credential=False,
    )
    assert scenario.case_number == 5
    assert scenario.wallet_action == "allow_login"  # login OK mais pas wallet strict
    assert scenario.unique_human_proven is False


def test_S16b_case5_unknown_uv() -> None:
    """S16b : UV=UNKNOWN → CASE_5 (conservateur = PIN)."""
    scenario = classify_device_scenario(
        credential_known=True,
        human_id_known=True,
        human_has_active_wallet=False,
        assertion_valid=True,
        user_verified=True,
        uv_method=UserVerificationMethod.UNKNOWN,
        is_new_credential=False,
    )
    assert scenario.case_number == 5
    assert scenario.unique_human_proven is False


# ─── S17 : evaluate_wallet_creation — aucun human_id → autorisé ──────────────

def test_S17_wallet_creation_no_human_id_allowed() -> None:
    """S17 : aucun HumanID connu → nouvel humain possible, création autorisée."""
    policy = evaluate_wallet_creation(
        human_id=None,
        existing_wallet_links=[],
        uv_method=UserVerificationMethod.BIOMETRIC,
        assertion_valid=True,
    )
    assert policy.allowed is True
    assert policy.unique_human_proven is False


# ─── S18 : evaluate_wallet_creation — human_id + wallet existant → refusé ────

def test_S18_wallet_creation_existing_wallet_blocked() -> None:
    """S18 : HumanID + wallet actif existant → refusé CASE_3."""
    links = [
        {"human_id": "human_xyz789", "wallet_address": "artcb1existing", "revoked": False}
    ]
    policy = evaluate_wallet_creation(
        human_id="human_xyz789",
        existing_wallet_links=links,
        uv_method=UserVerificationMethod.BIOMETRIC,
        assertion_valid=True,
    )
    assert policy.allowed is False
    assert policy.case_number == 3
    assert policy.unique_human_proven is False
    assert policy.certified_100 is False


# ─── S19 : evaluate_wallet_creation — uv=PIN → warning ──────────────────────

def test_S19_wallet_creation_pin_uv_produces_warning() -> None:
    """S19 : UV=PIN → warning dans la policy (pas un blocage sauf si limit atteinte)."""
    policy = evaluate_wallet_creation(
        human_id=None,
        existing_wallet_links=[],
        uv_method=UserVerificationMethod.PIN,
        assertion_valid=True,
    )
    assert policy.allowed is True
    assert len(policy.warnings) > 0
    # Le warning mentionne R372 et unique_human_proven
    assert any("unique_human_proven" in w or "R372" in w or "PIN" in w for w in policy.warnings)


# ─── S20 : wallet_human_link — round-trip ────────────────────────────────────

def test_S20_wallet_human_link_roundtrip(tmp_data_dir: Path) -> None:
    """S20 : save_wallet_human_link + load_wallet_human_links round-trip."""
    link = save_wallet_human_link(
        "human_test123",
        "artcb1testwallet",
        uv_method=UserVerificationMethod.BIOMETRIC,
    )
    assert link["human_id"] == "human_test123"
    assert link["wallet_address"] == "artcb1testwallet"
    assert link["revoked"] is False
    assert link["unique_human_proven"] is False

    loaded = load_wallet_human_links()
    assert len(loaded) == 1
    assert loaded[0]["human_id"] == "human_test123"
    assert loaded[0]["uv_method"] == "BIOMETRIC"


# ─── S21 : unique_human_proven toujours False dans tous les scénarios ────────

def test_S21_unique_human_proven_invariant_all_scenarios() -> None:
    """S21 : unique_human_proven=False dans TOUS les scénarios sans exception."""
    # Tous les cas classify_device_scenario
    params_matrix = [
        # (credential_known, human_id_known, has_wallet, assertion, uv, user_verified, is_new)
        (True,  True,  False, True,  UserVerificationMethod.BIOMETRIC, True,  False),  # CASE_1
        (False, True,  True,  True,  UserVerificationMethod.UNKNOWN,   True,  True),   # CASE_2
        (False, True,  True,  True,  UserVerificationMethod.BIOMETRIC, True,  False),  # CASE_3
        (True,  False, False, True,  UserVerificationMethod.UNKNOWN,   True,  False),  # CASE_4
        (True,  True,  False, True,  UserVerificationMethod.PIN,       True,  False),  # CASE_5
        (False, False, False, False, UserVerificationMethod.NONE,      False, False),  # UNVERIFIED
    ]
    for (ck, hk, hw, av, uvm, uv, inc) in params_matrix:
        scenario = classify_device_scenario(
            credential_known=ck,
            human_id_known=hk,
            human_has_active_wallet=hw,
            assertion_valid=av,
            user_verified=uv,
            uv_method=uvm,
            is_new_credential=inc,
        )
        assert scenario.unique_human_proven is False, (
            f"unique_human_proven doit être False pour {scenario} (R372)"
        )
        assert scenario.certified_100 is False


# ─── S22 : CASE_5 — PIN valide ne doit pas créer wallet avec human_id connu ──

def test_S22_pin_only_cannot_create_wallet_with_known_human() -> None:
    """S22 : PIN WebAuthn valide + HumanID connu + wallet existant → refusé (CASE_3 + CASE_5)."""
    links = [
        {"human_id": "human_pinuser1", "wallet_address": "artcb1pinwallet", "revoked": False}
    ]
    policy = evaluate_wallet_creation(
        human_id="human_pinuser1",
        existing_wallet_links=links,
        uv_method=UserVerificationMethod.PIN,
        assertion_valid=True,
    )
    assert policy.allowed is False
    assert policy.case_number == 3


def test_S22b_pin_with_no_wallet_allowed_with_warning() -> None:
    """S22b : PIN + aucun wallet → autorisé mais avec warning (premier enrôlement)."""
    policy = evaluate_wallet_creation(
        human_id="human_pinuser2",
        existing_wallet_links=[],
        uv_method=UserVerificationMethod.PIN,
        assertion_valid=True,
    )
    assert policy.allowed is True
    assert any("PIN" in w or "unique_human_proven" in w for w in policy.warnings)


# ─── S23 : matrice complète 5 cas × wallet_action ────────────────────────────

def test_S23_five_cases_wallet_action_matrix() -> None:
    """S23 : matrice complète — les 5 cas × wallet_action attendue (R372 spec).

    | Cas | Description                         | wallet_action    |
    |-----|-------------------------------------|------------------|
    |  1  | même humain / même appareil         | allow_login      |
    |  2  | même humain / nouvel appareil        | allow_add_device |
    |  3  | même humain / tentative multi-wallet | block_new_wallet |
    |  4  | autre humain / appareil connu        | allow_login      |
    |  5  | PIN seul                            | allow_login      |
    """
    expected = {
        1: "allow_login",
        2: "allow_add_device",
        3: "block_new_wallet",
        4: "allow_login",
        5: "allow_login",
    }

    scenarios = {
        1: classify_device_scenario(
            credential_known=True, human_id_known=True,
            human_has_active_wallet=True, assertion_valid=True,
            user_verified=True, uv_method=UserVerificationMethod.BIOMETRIC,
            is_new_credential=False,
        ),
        2: classify_device_scenario(
            credential_known=False, human_id_known=True,
            human_has_active_wallet=True, assertion_valid=True,
            user_verified=True, uv_method=UserVerificationMethod.UNKNOWN,
            is_new_credential=True,
        ),
        3: classify_device_scenario(
            credential_known=False, human_id_known=True,
            human_has_active_wallet=True, assertion_valid=True,
            user_verified=True, uv_method=UserVerificationMethod.BIOMETRIC,
            is_new_credential=False,
        ),
        4: classify_device_scenario(
            credential_known=True, human_id_known=False,
            human_has_active_wallet=False, assertion_valid=True,
            user_verified=True, uv_method=UserVerificationMethod.UNKNOWN,
            is_new_credential=False,
        ),
        5: classify_device_scenario(
            credential_known=True, human_id_known=True,
            human_has_active_wallet=False, assertion_valid=True,
            user_verified=True, uv_method=UserVerificationMethod.PIN,
            is_new_credential=False,
        ),
    }

    for case_num, scenario in scenarios.items():
        assert scenario.case_number == case_num, (
            f"CASE_{case_num} : case_number attendu={case_num} obtenu={scenario.case_number}"
        )
        assert scenario.wallet_action == expected[case_num], (
            f"CASE_{case_num} : wallet_action attendu={expected[case_num]!r} "
            f"obtenu={scenario.wallet_action!r}"
        )
        assert scenario.unique_human_proven is False, (
            f"CASE_{case_num} : unique_human_proven doit être False (R372)"
        )
