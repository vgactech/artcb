"""R454 — Politique WebAuthn FAIL-CLOSED : PIN seul / face_camera → rejeté (Issue #89).

Principe fondamental ARTCB (R372 / R373) :

    PIN seul    ≠   preuve biométrique
    face_camera ≠   authenticateur natif WebAuthn
    cross-platform authenticator ≠ authenticateur de plateforme

Ce module implémente un gate FAIL-CLOSED appliqué AVANT toute opération
sensible (création de wallet, enrôlement, opération économique).

Il NE décide PAS de l'authentification réseau — il décide si la méthode
d'authentification présentée est SUFFISANTE pour une opération donnée.

## Hiérarchie des opérations

    OPERATION_LOGIN           → tolérant (face_camera, PIN autorisés)
    OPERATION_WALLET_CREATE   → strict (WebAuthn platform + UV requis)
    OPERATION_ENROLL_DEVICE   → strict (WebAuthn platform + UV requis)
    OPERATION_ECONOMIC        → strict (WebAuthn platform + UV requis)
    OPERATION_ADMIN           → très strict (WebAuthn platform + UV + non-PIN)

## Résultat

    WebAuthnGateResult.allowed = True  → opération autorisée
    WebAuthnGateResult.allowed = False → opération REFUSÉE (FAIL-CLOSED)
    WebAuthnGateResult.reason  → code de rejet lisible par machine

## Invariants inviolables

    1. face_camera n'autorise JAMAIS OPERATION_WALLET_CREATE
    2. PIN (UV=true, méthode=PIN ou UNKNOWN) n'autorise JAMAIS OPERATION_ECONOMIC
    3. cross-platform authenticator → même restriction que PIN
    4. unique_human_proven reste toujours False — ce module ne le modifie pas
    5. FAIL-CLOSED : doute → refus (jamais d'autorisation par défaut)

CERTIFIED_100 = False.
"""

from __future__ import annotations

MODULE_VERSION = '1.0.1'  # R454 — WebAuthn FAIL-CLOSED gate

import enum
import logging
from dataclasses import dataclass, field
from typing import Any

from src.artcb.identity.human_identity_policy import UserVerificationMethod

logger = logging.getLogger("artcb.security.webauthn_failclosed")

# ─── Opérations ARTCB ────────────────────────────────────────────────────────

class ArtcbOperation(str, enum.Enum):
    """Opérations soumises au gate WebAuthn FAIL-CLOSED."""
    LOGIN            = "LOGIN"            # connexion simple — tolérant
    WALLET_CREATE    = "WALLET_CREATE"    # création wallet économique — strict
    ENROLL_DEVICE    = "ENROLL_DEVICE"    # ajout d'un appareil — strict
    ECONOMIC         = "ECONOMIC"         # opération économique (tx, reward) — strict
    ADMIN            = "ADMIN"            # opération admin — très strict

# ─── Méthodes de présentation ────────────────────────────────────────────────

class AuthModality(str, enum.Enum):
    """Modalité déclarée lors de l'authentification.

    Provient de la session / de la réponse d'assertion WebAuthn.
    """
    WEBAUTHN_PLATFORM  = "webauthn_platform"  # authentificateur natif (Touch ID, Face ID, Windows Hello)
    WEBAUTHN_ROAMING   = "webauthn_roaming"   # clé de sécurité physique cross-platform
    FACE_CAMERA        = "face_camera"        # caméra seule — FALLBACK ACCESSIBILITÉ uniquement
    PIN_ONLY           = "pin_only"           # PIN présenté directement au serveur (sans WebAuthn)
    UNKNOWN            = "unknown"            # modalité non déterminée

    @classmethod
    def from_session(cls, session: dict[str, Any]) -> "AuthModality":
        """Extrait la modalité depuis une session ARTCB.

        Politique conservatrice : en cas de doute → UNKNOWN.
        """
        raw = str(session.get("modality") or "").lower().strip()
        if raw in {"webauthn_fingerprint", "webauthn_face", "platform"}:
            return cls.WEBAUTHN_PLATFORM
        if raw in {"webauthn_roaming", "cross-platform", "roaming"}:
            return cls.WEBAUTHN_ROAMING
        if raw == "face_camera":
            return cls.FACE_CAMERA
        if raw in {"pin", "pin_only", "password"}:
            return cls.PIN_ONLY
        return cls.UNKNOWN

    def is_native_webauthn(self) -> bool:
        """Retourne True si la modalité est un authentificateur WebAuthn natif."""
        return self in {AuthModality.WEBAUTHN_PLATFORM, AuthModality.WEBAUTHN_ROAMING}

    def is_face_camera(self) -> bool:
        return self == AuthModality.FACE_CAMERA

    def is_pin_equivalent(self) -> bool:
        """PIN seul, inconnu ou caméra → équivalent PIN pour la politique."""
        return self in {
            AuthModality.PIN_ONLY,
            AuthModality.UNKNOWN,
            AuthModality.FACE_CAMERA,
        }


# ─── Contexte d'authentification ─────────────────────────────────────────────

@dataclass
class WebAuthnContext:
    """Contexte complet d'une authentification présentée pour évaluation.

    Tous les champs ont des valeurs conservatives par défaut (FAIL-CLOSED).
    """
    modality: AuthModality = AuthModality.UNKNOWN
    uv_method: UserVerificationMethod = UserVerificationMethod.UNKNOWN
    user_verified: bool = False           # flag UV dans les flags authData
    is_platform_bound: bool = False       # authentificateur de plateforme ?
    assertion_valid: bool = False         # signature WebAuthn vérifiée ?
    unique_human_proven: bool = False     # invariant — toujours False
    attestation_present: bool = False     # attestation d'authenticateur présente ?

    # Informations supplémentaires pour débogage (jamais utilisées pour autoriser)
    session_id: str = ""
    wallet_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Invariant inviolable : unique_human_proven est toujours False
        object.__setattr__(self, "unique_human_proven", False)

    @classmethod
    def from_session(cls, session: dict[str, Any], *, wallet_id: str = "") -> "WebAuthnContext":
        """Construit un contexte depuis une session ARTCB issue de webauthn_routes.py."""
        modality = AuthModality.from_session(session)
        uv_raw = str(session.get("uv_method") or "UNKNOWN").upper()
        try:
            uv_method = UserVerificationMethod(uv_raw)
        except ValueError:
            uv_method = UserVerificationMethod.UNKNOWN

        return cls(
            modality=modality,
            uv_method=uv_method,
            user_verified=bool(session.get("user_verified", False)),
            is_platform_bound=bool(session.get("is_platform_bound", False))
                              or modality == AuthModality.WEBAUTHN_PLATFORM,
            assertion_valid=bool(session.get("assertion_valid", False)),
            unique_human_proven=False,  # invariant
            attestation_present=bool(session.get("attestation_present", False)),
            session_id=str(session.get("session_id") or ""),
            wallet_id=wallet_id,
        )


# ─── Résultat du gate ─────────────────────────────────────────────────────────

@dataclass
class WebAuthnGateResult:
    """Résultat FAIL-CLOSED du gate WebAuthn.

    allowed=True  → opération autorisée
    allowed=False → opération refusée (FAIL-CLOSED)
    """
    allowed: bool
    reason: str                      # code machine (ex: "pin_not_sufficient")
    operation: ArtcbOperation = ArtcbOperation.LOGIN
    modality: AuthModality = AuthModality.UNKNOWN
    uv_method: UserVerificationMethod = UserVerificationMethod.UNKNOWN
    unique_human_proven: bool = False  # invariant — toujours False
    debug_info: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Invariant inviolable
        object.__setattr__(self, "unique_human_proven", False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "operation": self.operation.value,
            "modality": self.modality.value,
            "uv_method": self.uv_method.value,
            "unique_human_proven": False,
            "debug_info": self.debug_info,
        }


# ─── Gate FAIL-CLOSED ─────────────────────────────────────────────────────────

# Opérations qui exigent un authentificateur WebAuthn natif (platform ou roaming)
_STRICT_OPERATIONS = frozenset({
    ArtcbOperation.WALLET_CREATE,
    ArtcbOperation.ENROLL_DEVICE,
    ArtcbOperation.ECONOMIC,
    ArtcbOperation.ADMIN,
})

# Opérations qui exigent is_platform_bound=True (authentificateur de plateforme)
_PLATFORM_REQUIRED_OPERATIONS = frozenset({
    ArtcbOperation.WALLET_CREATE,
    ArtcbOperation.ENROLL_DEVICE,
    ArtcbOperation.ADMIN,
})

# Opérations qui refusent PIN/UNKNOWN/face_camera quelle que soit l'assertion
_PIN_BLOCKED_OPERATIONS = frozenset({
    ArtcbOperation.WALLET_CREATE,
    ArtcbOperation.ECONOMIC,
    ArtcbOperation.ADMIN,
})


def evaluate_gate(ctx: WebAuthnContext, operation: ArtcbOperation) -> WebAuthnGateResult:
    """Gate FAIL-CLOSED principal.

    Évalue si le contexte d'authentification est SUFFISANT pour l'opération.
    En cas de doute → False (FAIL-CLOSED).
    """
    _log_entry(ctx, operation)

    # ── Vérification 0 : signature WebAuthn valide ──────────────────────────
    if operation in _STRICT_OPERATIONS and not ctx.assertion_valid:
        return _deny(ctx, operation, "assertion_not_valid",
                     "Signature WebAuthn non vérifiée — opération refusée")

    # ── Vérification 1 : face_camera → bloqué pour toute opération stricte ──
    if ctx.modality.is_face_camera() and operation in _STRICT_OPERATIONS:
        return _deny(ctx, operation, "face_camera_not_sufficient",
                     "face_camera = FALLBACK ACCESSIBILITÉ uniquement — ne prouve pas l'identité WebAuthn")

    # ── Vérification 2 : modalité non-WebAuthn pour opérations strictes ──────
    if operation in _STRICT_OPERATIONS and not ctx.modality.is_native_webauthn():
        return _deny(ctx, operation, "non_webauthn_modality",
                     f"Modalité {ctx.modality.value!r} insuffisante pour {operation.value}")

    # ── Vérification 3 : authenticateur de plateforme requis ─────────────────
    if operation in _PLATFORM_REQUIRED_OPERATIONS and not ctx.is_platform_bound:
        return _deny(ctx, operation, "platform_authenticator_required",
                     "Authentificateur de plateforme (Touch ID / Face ID / Windows Hello) requis")

    # ── Vérification 4 : UV=true requis pour opérations strictes ─────────────
    if operation in _STRICT_OPERATIONS and not ctx.user_verified:
        return _deny(ctx, operation, "user_verification_required",
                     "user_verified=False — UV du dispositif non confirmé")

    # ── Vérification 5 : PIN/UNKNOWN bloqué pour opérations critiques ─────────
    if operation in _PIN_BLOCKED_OPERATIONS and ctx.uv_method in {
        UserVerificationMethod.PIN,
        UserVerificationMethod.UNKNOWN,
    }:
        return _deny(ctx, operation, "pin_not_sufficient",
                     f"uv_method={ctx.uv_method.value} insuffisant pour {operation.value} — "
                     "WebAuthn biométrique natif requis")

    # ── Vérification 6 : UNKNOWN modality pour opérations strictes ───────────
    if operation in _STRICT_OPERATIONS and ctx.modality == AuthModality.UNKNOWN:
        return _deny(ctx, operation, "unknown_modality_not_sufficient",
                     "Modalité inconnue — FAIL-CLOSED pour opération stricte")

    # ── Autorisé ──────────────────────────────────────────────────────────────
    result = WebAuthnGateResult(
        allowed=True,
        reason="ok",
        operation=operation,
        modality=ctx.modality,
        uv_method=ctx.uv_method,
        unique_human_proven=False,
        debug_info={"wallet_id": ctx.wallet_id, "session_id": ctx.session_id},
    )
    logger.debug(
        "gate_allow operation=%s modality=%s uv=%s wallet=%s",
        operation.value, ctx.modality.value, ctx.uv_method.value, ctx.wallet_id,
    )
    return result


def _deny(ctx: WebAuthnContext, operation: ArtcbOperation, reason: str, detail: str) -> WebAuthnGateResult:
    logger.warning(
        "gate_deny operation=%s modality=%s uv=%s reason=%s wallet=%s — %s",
        operation.value, ctx.modality.value, ctx.uv_method.value,
        reason, ctx.wallet_id, detail,
    )
    return WebAuthnGateResult(
        allowed=False,
        reason=reason,
        operation=operation,
        modality=ctx.modality,
        uv_method=ctx.uv_method,
        unique_human_proven=False,
        debug_info={"detail": detail, "wallet_id": ctx.wallet_id, "session_id": ctx.session_id},
    )


def _log_entry(ctx: WebAuthnContext, operation: ArtcbOperation) -> None:
    logger.debug(
        "gate_eval operation=%s modality=%s uv=%s user_verified=%s platform=%s wallet=%s",
        operation.value, ctx.modality.value, ctx.uv_method.value,
        ctx.user_verified, ctx.is_platform_bound, ctx.wallet_id,
    )


# ─── Helpers de haut niveau ──────────────────────────────────────────────────

def check_wallet_creation(ctx: WebAuthnContext) -> WebAuthnGateResult:
    """Vérification rapide pour la création de wallet économique."""
    return evaluate_gate(ctx, ArtcbOperation.WALLET_CREATE)


def check_economic_operation(ctx: WebAuthnContext) -> WebAuthnGateResult:
    """Vérification rapide pour toute opération économique."""
    return evaluate_gate(ctx, ArtcbOperation.ECONOMIC)


def check_device_enrollment(ctx: WebAuthnContext) -> WebAuthnGateResult:
    """Vérification rapide pour l'enrôlement d'un nouvel appareil."""
    return evaluate_gate(ctx, ArtcbOperation.ENROLL_DEVICE)


def check_login(ctx: WebAuthnContext) -> WebAuthnGateResult:
    """Vérification rapide pour login (tolérant)."""
    return evaluate_gate(ctx, ArtcbOperation.LOGIN)
