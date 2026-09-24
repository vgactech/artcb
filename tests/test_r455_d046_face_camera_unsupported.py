"""R455 — Tests D-046 : face_camera UNSUPPORTED — rejet total dans ARTCB.

D-046 (2026-09-25) : aucune fonctionnalité ARTCB ne doit accepter face_camera
à quelque niveau que ce soit. La seule voie biométrique passe par WebAuthn/FIDO
natif de la plateforme (Touch ID, Face ID OS, Windows Hello).

Couverture (20 tests F01–F20) :

Groupe A — gate FAIL-CLOSED face_camera toutes opérations
  F01 — face_camera + LOGIN → refusé (face_camera_unsupported_d046)
  F02 — face_camera + WALLET_CREATE → refusé
  F03 — face_camera + ECONOMIC → refusé
  F04 — face_camera + ENROLL_DEVICE → refusé
  F05 — face_camera + ADMIN → refusé
  F06 — raison = "face_camera_unsupported_d046" pour toutes les 5 opérations

Groupe B — store : MODALITY_FACE retiré d'ALLOWED_MODALITIES
  F07 — ALLOWED_MODALITIES ne contient pas MODALITY_FACE
  F08 — FACE_CAMERA_UNSUPPORTED sentinel = True
  F09 — ALLOWED_MODALITIES contient uniquement MODALITY_FINGERPRINT

Groupe C — API routes : endpoints /face/* → 410 Gone
  F10 — face_enroll_options → HTTPException 410
  F11 — face_enroll_verify → HTTPException 410
  F12 — face_login → HTTPException 410
  F13 — face_login_options → HTTPException 410
  F14 — payload 410 contient "face_camera_unsupported_d046"

Groupe D — constantes D-046 vérifiables par machine
  F15 — FACE_CAMERA_POLICY = "UNSUPPORTED_D046"
  F16 — FACE_CAMERA_INACTIVE_PRODUCTION = True dans webauthn_routes

Groupe E — WebAuthn platform biométrique TOUJOURS accepté (régression)
  F17 — platform + BIOMETRIC + LOGIN → autorisé
  F18 — platform + BIOMETRIC + WALLET_CREATE → autorisé
  F19 — unique_human_proven=False même pour WebAuthn platform autorisé

Groupe F — from_session() : face_camera détecté et classifié pour rejet
  F20 — from_session({"modality":"face_camera"}) → FACE_CAMERA → rejeté
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.artcb.security.webauthn_failclosed import (
    FACE_CAMERA_POLICY,
    ArtcbOperation,
    AuthModality,
    WebAuthnContext,
    evaluate_gate,
)
from src.artcb.security.webauthn_store import (
    ALLOWED_MODALITIES,
    FACE_CAMERA_UNSUPPORTED,
    MODALITY_FACE,
    MODALITY_FINGERPRINT,
)
from src.artcb.identity.human_identity_policy import UserVerificationMethod

# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _face_ctx() -> WebAuthnContext:
    return WebAuthnContext(
        modality=AuthModality.FACE_CAMERA,
        uv_method=UserVerificationMethod.UNKNOWN,
        user_verified=True,
        is_platform_bound=False,
        assertion_valid=True,
    )


def _platform_ctx() -> WebAuthnContext:
    return WebAuthnContext(
        modality=AuthModality.WEBAUTHN_PLATFORM,
        uv_method=UserVerificationMethod.BIOMETRIC,
        user_verified=True,
        is_platform_bound=True,
        assertion_valid=True,
    )


# ─── Groupe A — gate FAIL-CLOSED face_camera toutes opérations ───────────────

def test_f01_face_camera_login_denied_d046():
    """F01 — D-046 : face_camera + LOGIN → refusé."""
    r = evaluate_gate(_face_ctx(), ArtcbOperation.LOGIN)
    assert not r.allowed
    assert r.reason == "face_camera_unsupported_d046"


def test_f02_face_camera_wallet_create_denied():
    """F02 — D-046 : face_camera + WALLET_CREATE → refusé."""
    r = evaluate_gate(_face_ctx(), ArtcbOperation.WALLET_CREATE)
    assert not r.allowed
    assert r.reason == "face_camera_unsupported_d046"


def test_f03_face_camera_economic_denied():
    """F03 — D-046 : face_camera + ECONOMIC → refusé."""
    r = evaluate_gate(_face_ctx(), ArtcbOperation.ECONOMIC)
    assert not r.allowed
    assert r.reason == "face_camera_unsupported_d046"


def test_f04_face_camera_enroll_device_denied():
    """F04 — D-046 : face_camera + ENROLL_DEVICE → refusé."""
    r = evaluate_gate(_face_ctx(), ArtcbOperation.ENROLL_DEVICE)
    assert not r.allowed
    assert r.reason == "face_camera_unsupported_d046"


def test_f05_face_camera_admin_denied():
    """F05 — D-046 : face_camera + ADMIN → refusé."""
    r = evaluate_gate(_face_ctx(), ArtcbOperation.ADMIN)
    assert not r.allowed
    assert r.reason == "face_camera_unsupported_d046"


def test_f06_reason_consistent_all_operations():
    """F06 — D-046 : raison = 'face_camera_unsupported_d046' pour les 5 opérations."""
    ctx = _face_ctx()
    for op in ArtcbOperation:
        r = evaluate_gate(ctx, op)
        assert not r.allowed, f"face_camera ne doit pas être autorisé pour {op.value}"
        assert r.reason == "face_camera_unsupported_d046", (
            f"Raison attendue 'face_camera_unsupported_d046', obtenue '{r.reason}' pour {op.value}"
        )


# ─── Groupe B — store ALLOWED_MODALITIES ────────────────────────────────────

def test_f07_modality_face_not_in_allowed():
    """F07 — D-046 : MODALITY_FACE absent d'ALLOWED_MODALITIES."""
    assert MODALITY_FACE not in ALLOWED_MODALITIES, (
        f"MODALITY_FACE '{MODALITY_FACE}' ne doit pas être dans ALLOWED_MODALITIES={ALLOWED_MODALITIES}"
    )


def test_f08_face_camera_unsupported_sentinel():
    """F08 — D-046 : FACE_CAMERA_UNSUPPORTED = True (sentinel vérifiable)."""
    assert FACE_CAMERA_UNSUPPORTED is True


def test_f09_allowed_modalities_fingerprint_only():
    """F09 — D-046 : ALLOWED_MODALITIES contient uniquement MODALITY_FINGERPRINT."""
    assert MODALITY_FINGERPRINT in ALLOWED_MODALITIES
    assert ALLOWED_MODALITIES == frozenset({MODALITY_FINGERPRINT}), (
        f"ALLOWED_MODALITIES attendu {{fingerprint}}, obtenu {ALLOWED_MODALITIES}"
    )


# ─── Groupe C — API routes /face/* → 410 Gone ────────────────────────────────

def _make_face_begin_body(name: str = "test-wallet") -> object:
    """Crée un body minimal pour les endpoints face."""
    from unittest.mock import MagicMock
    body = MagicMock()
    body.name = name
    body.create_wallet = False
    body.nonce = "test-nonce"
    body.liveness_ok = True
    body.device_secret = "secret"
    return body


def _make_face_finish_body(name: str = "test-wallet") -> object:
    from unittest.mock import MagicMock
    body = MagicMock()
    body.name = name
    body.nonce = "test-nonce"
    body.liveness_ok = True
    body.device_secret = "secret"
    body.image_b64 = None
    body.create_wallet = False
    return body


def test_f10_face_enroll_options_410():
    """F10 — D-046 : /face/enroll/options retourne 410 Gone."""
    from src.api.webauthn_routes import face_enroll_options
    with pytest.raises(HTTPException) as exc_info:
        face_enroll_options(_make_face_begin_body())
    assert exc_info.value.status_code == 410
    assert exc_info.value.detail["error"] == "face_camera_unsupported_d046"


def test_f11_face_enroll_verify_410():
    """F11 — D-046 : /face/enroll/verify retourne 410 Gone."""
    from src.api.webauthn_routes import face_enroll_verify
    from unittest.mock import MagicMock
    with pytest.raises(HTTPException) as exc_info:
        face_enroll_verify(_make_face_finish_body(), MagicMock())
    assert exc_info.value.status_code == 410


def test_f12_face_login_410():
    """F12 — D-046 : /face/login retourne 410 Gone."""
    from src.api.webauthn_routes import face_login
    from unittest.mock import MagicMock
    with pytest.raises(HTTPException) as exc_info:
        face_login(_make_face_finish_body(), MagicMock())
    assert exc_info.value.status_code == 410


def test_f13_face_login_options_410():
    """F13 — D-046 : /face/login/options retourne 410 Gone."""
    from src.api.webauthn_routes import face_login_options
    with pytest.raises(HTTPException) as exc_info:
        face_login_options(_make_face_begin_body())
    assert exc_info.value.status_code == 410


def test_f14_410_payload_contains_policy():
    """F14 — D-046 : payload 410 contient 'face_camera_unsupported_d046' et 'UNSUPPORTED_D046'."""
    from src.api.webauthn_routes import face_enroll_options
    with pytest.raises(HTTPException) as exc_info:
        face_enroll_options(_make_face_begin_body())
    detail = exc_info.value.detail
    assert detail["error"] == "face_camera_unsupported_d046"
    assert detail["policy"] == "UNSUPPORTED_D046"


# ─── Groupe D — constantes D-046 ─────────────────────────────────────────────

def test_f15_face_camera_policy_constant():
    """F15 — D-046 : FACE_CAMERA_POLICY = 'UNSUPPORTED_D046'."""
    assert FACE_CAMERA_POLICY == "UNSUPPORTED_D046"


def test_f16_face_camera_inactive_production():
    """F16 — D-046 : FACE_CAMERA_INACTIVE_PRODUCTION = True dans webauthn_routes."""
    from src.api.webauthn_routes import FACE_CAMERA_INACTIVE_PRODUCTION
    assert FACE_CAMERA_INACTIVE_PRODUCTION is True


# ─── Groupe E — régression WebAuthn platform ─────────────────────────────────

def test_f17_platform_biometric_login_still_allowed():
    """F17 — Régression : WebAuthn platform + BIOMETRIC + LOGIN → autorisé."""
    r = evaluate_gate(_platform_ctx(), ArtcbOperation.LOGIN)
    assert r.allowed, f"WebAuthn platform LOGIN doit rester autorisé: {r.reason}"


def test_f18_platform_biometric_wallet_create_still_allowed():
    """F18 — Régression : WebAuthn platform + BIOMETRIC + WALLET_CREATE → autorisé."""
    r = evaluate_gate(_platform_ctx(), ArtcbOperation.WALLET_CREATE)
    assert r.allowed, f"WebAuthn platform WALLET_CREATE doit rester autorisé: {r.reason}"


def test_f19_unique_human_proven_false_even_platform():
    """F19 — unique_human_proven=False même pour WebAuthn platform autorisé."""
    r = evaluate_gate(_platform_ctx(), ArtcbOperation.WALLET_CREATE)
    assert r.allowed
    assert r.unique_human_proven is False


# ─── Groupe F — from_session détection face_camera ──────────────────────────

def test_f20_from_session_face_camera_detected_and_denied():
    """F20 — from_session({'modality':'face_camera'}) → FACE_CAMERA → rejeté pour toutes opérations."""
    session = {"modality": "face_camera", "user_verified": True, "assertion_valid": True}
    ctx = WebAuthnContext.from_session(session)
    assert ctx.modality == AuthModality.FACE_CAMERA
    # Rejeté pour toutes les opérations
    for op in ArtcbOperation:
        r = evaluate_gate(ctx, op)
        assert not r.allowed, f"face_camera doit être rejeté pour {op.value}"
        assert r.reason == "face_camera_unsupported_d046"
