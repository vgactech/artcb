"""R454 — Tests gate WebAuthn FAIL-CLOSED : PIN seul / face_camera → rejet (Issue #89).

Couverture (25 tests W01–W25) :

Groupe A — Opérations bloquées (FAIL-CLOSED)
  W01 — PIN + WALLET_CREATE → refusé (pin_not_sufficient)
  W02 — UNKNOWN + WALLET_CREATE → refusé (pin_not_sufficient)
  W03 — face_camera + WALLET_CREATE → refusé (face_camera_not_sufficient)
  W04 — face_camera + ECONOMIC → refusé
  W05 — face_camera + ENROLL_DEVICE → refusé
  W06 — face_camera + ADMIN → refusé
  W07 — PIN + ECONOMIC → refusé
  W08 — UNKNOWN modality + WALLET_CREATE → refusé (unknown_modality_not_sufficient)
  W09 — cross-platform (roaming) + WALLET_CREATE sans platform_bound → refusé
  W10 — assertion_valid=False + WALLET_CREATE → refusé (assertion_not_valid)
  W11 — user_verified=False + ECONOMIC → refusé (user_verification_required)

Groupe B — Opérations autorisées
  W12 — WebAuthn platform + BIOMETRIC + WALLET_CREATE → autorisé
  W13 — WebAuthn platform + BIOMETRIC + ECONOMIC → autorisé
  W14 — WebAuthn platform + BIOMETRIC + ENROLL_DEVICE → autorisé
  W15 — WebAuthn platform + BIOMETRIC + ADMIN → autorisé
  W16 — face_camera + LOGIN → autorisé (tolérant)
  W17 — PIN + LOGIN → autorisé (tolérant)
  W18 — UNKNOWN modality + LOGIN → autorisé (tolérant)

Groupe C — Invariants systémiques
  W19 — unique_human_proven=False dans tous les cas (autorisé ou refusé)
  W20 — WebAuthnContext.unique_human_proven est toujours False même si forcé True
  W21 — WebAuthnGateResult.unique_human_proven est toujours False
  W22 — from_session() : modalité conservatrice (UNKNOWN si non reconnu)
  W23 — from_session() : face_camera correctement mappé
  W24 — from_session() : platform mappé vers WEBAUTHN_PLATFORM

Groupe D — Helpers de haut niveau
  W25 — check_wallet_creation / check_economic_operation / check_device_enrollment cohérents
"""

from __future__ import annotations

import pytest
from src.artcb.security.webauthn_failclosed import (
    ArtcbOperation,
    AuthModality,
    WebAuthnContext,
    WebAuthnGateResult,
    check_device_enrollment,
    check_economic_operation,
    check_login,
    check_wallet_creation,
    evaluate_gate,
)
from src.artcb.identity.human_identity_policy import UserVerificationMethod


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _platform_ctx(
    *,
    uv_method: UserVerificationMethod = UserVerificationMethod.BIOMETRIC,
    user_verified: bool = True,
    assertion_valid: bool = True,
    wallet_id: str = "wallet-test",
) -> WebAuthnContext:
    """Contexte WebAuthn platform valide (chemin nominal autorisé)."""
    return WebAuthnContext(
        modality=AuthModality.WEBAUTHN_PLATFORM,
        uv_method=uv_method,
        user_verified=user_verified,
        is_platform_bound=True,
        assertion_valid=assertion_valid,
        unique_human_proven=False,
        wallet_id=wallet_id,
    )


def _face_camera_ctx() -> WebAuthnContext:
    """Contexte face_camera (FALLBACK ACCESSIBILITÉ)."""
    return WebAuthnContext(
        modality=AuthModality.FACE_CAMERA,
        uv_method=UserVerificationMethod.UNKNOWN,
        user_verified=True,
        is_platform_bound=False,
        assertion_valid=True,
    )


def _pin_ctx() -> WebAuthnContext:
    """Contexte PIN (UV=true, méthode=PIN)."""
    return WebAuthnContext(
        modality=AuthModality.WEBAUTHN_PLATFORM,
        uv_method=UserVerificationMethod.PIN,
        user_verified=True,
        is_platform_bound=True,
        assertion_valid=True,
    )


# ─── Groupe A — Opérations bloquées ──────────────────────────────────────────

def test_w01_pin_wallet_create_denied():
    """W01 — PIN + WALLET_CREATE → refusé (pin_not_sufficient)."""
    ctx = _pin_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.WALLET_CREATE)
    assert not result.allowed, "PIN ne doit pas autoriser WALLET_CREATE"
    assert result.reason == "pin_not_sufficient"
    assert result.unique_human_proven is False


def test_w02_unknown_uv_wallet_create_denied():
    """W02 — uv_method=UNKNOWN + WALLET_CREATE → refusé."""
    ctx = _platform_ctx(uv_method=UserVerificationMethod.UNKNOWN)
    result = evaluate_gate(ctx, ArtcbOperation.WALLET_CREATE)
    assert not result.allowed
    assert result.reason == "pin_not_sufficient"


def test_w03_face_camera_wallet_create_denied():
    """W03 — face_camera + WALLET_CREATE → refusé (face_camera_not_sufficient)."""
    ctx = _face_camera_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.WALLET_CREATE)
    assert not result.allowed
    assert result.reason == "face_camera_not_sufficient"
    assert result.unique_human_proven is False


def test_w04_face_camera_economic_denied():
    """W04 — face_camera + ECONOMIC → refusé."""
    ctx = _face_camera_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.ECONOMIC)
    assert not result.allowed
    assert "face_camera" in result.reason


def test_w05_face_camera_enroll_device_denied():
    """W05 — face_camera + ENROLL_DEVICE → refusé."""
    ctx = _face_camera_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.ENROLL_DEVICE)
    assert not result.allowed


def test_w06_face_camera_admin_denied():
    """W06 — face_camera + ADMIN → refusé."""
    ctx = _face_camera_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.ADMIN)
    assert not result.allowed


def test_w07_pin_economic_denied():
    """W07 — PIN + ECONOMIC → refusé."""
    ctx = _pin_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.ECONOMIC)
    assert not result.allowed
    assert result.reason == "pin_not_sufficient"


def test_w08_unknown_modality_wallet_create_denied():
    """W08 — Modalité UNKNOWN + WALLET_CREATE → refusé FAIL-CLOSED."""
    ctx = WebAuthnContext(
        modality=AuthModality.UNKNOWN,
        uv_method=UserVerificationMethod.BIOMETRIC,
        user_verified=True,
        is_platform_bound=True,
        assertion_valid=True,
    )
    result = evaluate_gate(ctx, ArtcbOperation.WALLET_CREATE)
    assert not result.allowed, "Modalité UNKNOWN doit échouer FAIL-CLOSED pour WALLET_CREATE"
    # Soit non_webauthn_modality, soit unknown_modality_not_sufficient
    assert "not_sufficient" in result.reason or "non_webauthn" in result.reason


def test_w09_roaming_without_platform_wallet_create_denied():
    """W09 — cross-platform (roaming) sans is_platform_bound → WALLET_CREATE refusé."""
    ctx = WebAuthnContext(
        modality=AuthModality.WEBAUTHN_ROAMING,
        uv_method=UserVerificationMethod.BIOMETRIC,
        user_verified=True,
        is_platform_bound=False,  # pas d'authentificateur de plateforme
        assertion_valid=True,
    )
    result = evaluate_gate(ctx, ArtcbOperation.WALLET_CREATE)
    assert not result.allowed
    assert result.reason == "platform_authenticator_required"


def test_w10_assertion_invalid_wallet_create_denied():
    """W10 — assertion_valid=False + WALLET_CREATE → refusé (assertion_not_valid)."""
    ctx = _platform_ctx(assertion_valid=False)
    result = evaluate_gate(ctx, ArtcbOperation.WALLET_CREATE)
    assert not result.allowed
    assert result.reason == "assertion_not_valid"


def test_w11_user_not_verified_economic_denied():
    """W11 — user_verified=False + ECONOMIC → refusé (user_verification_required)."""
    ctx = _platform_ctx(user_verified=False)
    result = evaluate_gate(ctx, ArtcbOperation.ECONOMIC)
    assert not result.allowed
    assert result.reason == "user_verification_required"


# ─── Groupe B — Opérations autorisées ────────────────────────────────────────

def test_w12_platform_biometric_wallet_create_allowed():
    """W12 — WebAuthn platform + BIOMETRIC + WALLET_CREATE → autorisé."""
    ctx = _platform_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.WALLET_CREATE)
    assert result.allowed, f"Refus inattendu: {result.reason}"
    assert result.reason == "ok"
    assert result.unique_human_proven is False


def test_w13_platform_biometric_economic_allowed():
    """W13 — WebAuthn platform + BIOMETRIC + ECONOMIC → autorisé."""
    ctx = _platform_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.ECONOMIC)
    assert result.allowed


def test_w14_platform_biometric_enroll_device_allowed():
    """W14 — WebAuthn platform + BIOMETRIC + ENROLL_DEVICE → autorisé."""
    ctx = _platform_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.ENROLL_DEVICE)
    assert result.allowed


def test_w15_platform_biometric_admin_allowed():
    """W15 — WebAuthn platform + BIOMETRIC + ADMIN → autorisé."""
    ctx = _platform_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.ADMIN)
    assert result.allowed


def test_w16_face_camera_login_allowed():
    """W16 — face_camera + LOGIN → autorisé (login est tolérant)."""
    ctx = _face_camera_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.LOGIN)
    assert result.allowed, f"Login face_camera doit être autorisé: {result.reason}"


def test_w17_pin_login_allowed():
    """W17 — PIN + LOGIN → autorisé (login est tolérant)."""
    ctx = _pin_ctx()
    result = evaluate_gate(ctx, ArtcbOperation.LOGIN)
    assert result.allowed, f"Login PIN doit être autorisé: {result.reason}"


def test_w18_unknown_modality_login_allowed():
    """W18 — UNKNOWN modality + LOGIN → autorisé (tolérant)."""
    ctx = WebAuthnContext(
        modality=AuthModality.UNKNOWN,
        uv_method=UserVerificationMethod.UNKNOWN,
        user_verified=False,
        is_platform_bound=False,
        assertion_valid=False,
    )
    result = evaluate_gate(ctx, ArtcbOperation.LOGIN)
    assert result.allowed, f"Login UNKNOWN doit être autorisé: {result.reason}"


# ─── Groupe C — Invariants systémiques ───────────────────────────────────────

def test_w19_unique_human_proven_always_false():
    """W19 — unique_human_proven=False dans tous les cas (autorisé ET refusé)."""
    cases = [
        (_platform_ctx(), ArtcbOperation.WALLET_CREATE),   # autorisé
        (_face_camera_ctx(), ArtcbOperation.WALLET_CREATE), # refusé
        (_pin_ctx(), ArtcbOperation.ECONOMIC),              # refusé
        (_platform_ctx(), ArtcbOperation.LOGIN),            # autorisé
        (_face_camera_ctx(), ArtcbOperation.LOGIN),         # autorisé
    ]
    for ctx, op in cases:
        result = evaluate_gate(ctx, op)
        assert result.unique_human_proven is False, (
            f"unique_human_proven doit être False — op={op.value}, "
            f"modality={ctx.modality.value}, allowed={result.allowed}"
        )


def test_w20_context_unique_human_proven_invariant():
    """W20 — WebAuthnContext.unique_human_proven est toujours False, même si tenté True."""
    ctx = WebAuthnContext(
        modality=AuthModality.WEBAUTHN_PLATFORM,
        uv_method=UserVerificationMethod.BIOMETRIC,
        user_verified=True,
        is_platform_bound=True,
        assertion_valid=True,
        unique_human_proven=True,  # tentative de forçage → doit rester False
    )
    assert ctx.unique_human_proven is False, (
        "L'invariant unique_human_proven=False doit être maintenu dans __post_init__"
    )


def test_w21_gate_result_unique_human_proven_invariant():
    """W21 — WebAuthnGateResult.unique_human_proven est toujours False."""
    result = WebAuthnGateResult(
        allowed=True,
        reason="ok",
        operation=ArtcbOperation.WALLET_CREATE,
        modality=AuthModality.WEBAUTHN_PLATFORM,
        uv_method=UserVerificationMethod.BIOMETRIC,
        unique_human_proven=True,  # tentative de forçage
    )
    assert result.unique_human_proven is False


def test_w22_from_session_unknown_modality():
    """W22 — from_session() : modalité non reconnue → UNKNOWN (conservateur)."""
    session = {"modality": "some_unknown_method", "uv_method": "UNKNOWN"}
    ctx = WebAuthnContext.from_session(session)
    assert ctx.modality == AuthModality.UNKNOWN


def test_w23_from_session_face_camera():
    """W23 — from_session() : face_camera correctement extrait."""
    session = {
        "modality": "face_camera",
        "uv_method": "UNKNOWN",
        "user_verified": True,
        "assertion_valid": True,
    }
    ctx = WebAuthnContext.from_session(session)
    assert ctx.modality == AuthModality.FACE_CAMERA
    assert ctx.unique_human_proven is False


def test_w24_from_session_platform():
    """W24 — from_session() : webauthn_fingerprint → WEBAUTHN_PLATFORM."""
    session = {
        "modality": "webauthn_fingerprint",
        "uv_method": "BIOMETRIC",
        "user_verified": True,
        "is_platform_bound": True,
        "assertion_valid": True,
    }
    ctx = WebAuthnContext.from_session(session)
    assert ctx.modality == AuthModality.WEBAUTHN_PLATFORM
    assert ctx.is_platform_bound is True


# ─── Groupe D — Helpers de haut niveau ───────────────────────────────────────

def test_w25_high_level_helpers_consistent():
    """W25 — Helpers check_wallet_creation / check_economic / check_device_enrollment cohérents."""
    valid_ctx = _platform_ctx()
    invalid_ctx = _face_camera_ctx()

    # Valides
    assert check_wallet_creation(valid_ctx).allowed
    assert check_economic_operation(valid_ctx).allowed
    assert check_device_enrollment(valid_ctx).allowed
    assert check_login(valid_ctx).allowed

    # Invalides
    assert not check_wallet_creation(invalid_ctx).allowed
    assert not check_economic_operation(invalid_ctx).allowed
    assert not check_device_enrollment(invalid_ctx).allowed

    # Login toujours OK même avec face_camera
    assert check_login(invalid_ctx).allowed

    # PIN : wallet refusé, login OK
    pin_ctx = _pin_ctx()
    assert not check_wallet_creation(pin_ctx).allowed
    assert check_login(pin_ctx).allowed
