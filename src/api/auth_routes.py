"""Authentification utilisateur ARTCB — login, challenge, verify.

Protocole :
  1. POST /auth/login     — login classique (name + password) [DÉPRÉCIÉ — P0-A 2026-09-16]
                            Les wallets biométriques ARTCB ne peuvent pas utiliser ce chemin.
                            Voie recommandée : /auth/verify (clé privée) ou /auth/webauthn/login (biométrie).
  2. GET  /auth/challenge — nonce pour signature crypto
  3. POST /auth/verify    — vérification signature Ed25519 du challenge  ← VOIE PRINCIPALE
  4. POST /auth/webauthn/login/verify — authentification biométrique     ← VOIE BIOMÉTRIQUE
  5. POST /auth/logout    — invalide le token de session

L'API key (/api-keys/generate) n'est utilisable QU'APRÈS authentification.

DEPRECATION P0-A (2026-09-16) :
  /auth/login (name + password) est déprécié pour les nouvelles identités ARTCB.
  Les identités HumanIdentity (biométriques) n'ont jamais de mot de passe connu.
  Les wallets classiques existants peuvent encore utiliser /auth/login temporairement.
  Tous les nouveaux clients doivent utiliser /auth/verify ou /auth/webauthn/login.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from nacl import signing
from nacl.exceptions import BadSignatureError
from pydantic import BaseModel, Field

logger = logging.getLogger("artcb.api.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# TTL des challenges (5 minutes) et des sessions (30 minutes — standard Web3/blockchain)
# Référence : EIP-4361, PCI-DSS, RFC 6749 (access token)
# Les réseaux sociaux utilisent 1-2h, les banques 15 min, le Web3 30-60 min.
# ARTCB étant une blockchain financière post-quantique → 30 min (1800s).
_CHALLENGE_TTL = 300
_SESSION_TTL = 1800

# R320 (2026-09-11T21:30:00Z) — durcissement session.
# Ajout, rien de supprimé : _SESSION_TTL reste la durée absolue (30 min).
#
# 1. Inactivité (« idle ») : un token volé et laissé de côté meurt plus vite que
#    la durée absolue. Le compteur repart à chaque appel authentifié valide.
# 2. Empreinte d'appareil : le token est lié au couple (User-Agent, en-tête
#    X-ARTCB-Device-Id) observé à la connexion. Rejouer le token depuis un autre
#    appareil → 401 session_device_mismatch.
# Les deux sont réglables par variable d'environnement pour ne jamais bloquer un
# agent autonome en phase de développement réel.
_SESSION_IDLE_TTL = int(os.getenv("ARTCB_SESSION_IDLE_TTL", "900"))


def _bind_device_enforced() -> bool:
    return (os.getenv("ARTCB_SESSION_BIND_DEVICE", "1").strip().lower()
            not in {"0", "false", "no", "off"})


def device_fingerprint(request: Request | None) -> str:
    """Empreinte d'appareil stable et non secrète (jamais d'IP seule).

    On hache User-Agent + X-ARTCB-Device-Id. L'IP change (4G ↔ Wi-Fi, NAT,
    proxy) : la lier casserait des sessions légitimes sans gain réel.
    """
    if request is None:
        return ""
    ua = (request.headers.get("user-agent") or "").strip()
    dev = (request.headers.get("x-artcb-device-id") or "").strip()
    if not ua and not dev:
        return ""
    return hashlib.sha256(f"{ua}|{dev}".encode()).hexdigest()[:32]


# Stockage sessions : mémoire + disque (R322). Challenges restent en mémoire (TTL court).
# ~~(en production : Redis ou table SQL)~~ — sessions.json sous ARTCB_DATA_DIR/auth/
from src.api.session_store import ensure_loaded as _sessions_ensure_loaded
from src.api.session_store import save_sessions as _sessions_save

_challenges: dict[str, float] = {}   # nonce_hex → expires_at
_sessions: dict[str, dict] = {}       # token_hash → {wallet_name, address, created_at, expires_at}


def _prune_sessions() -> int:
    """R320 — retire les sessions expirées (fuite mémoire + surface d'attaque)."""
    _sessions_ensure_loaded(_sessions)
    now = time.time()
    dead = [h for h, r in _sessions.items() if now > r.get("expires_at", 0)]
    for h in dead:
        _sessions.pop(h, None)
    if dead:
        _sessions_save(_sessions)
    return len(dead)


def issue_session(
    *,
    wallet_name: str,
    address: str,
    request: Request | None = None,
) -> dict:
    """Create a sess_ token (password login, WebAuthn, or face-unlock)."""
    _prune_sessions()
    raw_token = "sess_" + secrets.token_hex(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    now = time.time()
    fp = device_fingerprint(request)
    record = {
        "wallet_name": wallet_name,
        "address": address,
        "created_at": now,
        "expires_at": now + _SESSION_TTL,
        # R320
        "session_id": token_hash[:16],
        "device_fp": fp,
        "last_seen": now,
        "idle_ttl": _SESSION_IDLE_TTL,
    }
    _sessions[token_hash] = record
    _sessions_save(_sessions)
    return {
        "session_token": raw_token,
        "wallet_name": wallet_name,
        "address": address,
        "expires_in": _SESSION_TTL,
        "idle_expires_in": _SESSION_IDLE_TTL,
        "session_id": record["session_id"],
        "device_bound": bool(fp) and _bind_device_enforced(),
    }


# --------------------------------------------------------------------------- #
#  Schémas Pydantic
# --------------------------------------------------------------------------- #

# Same text for every failure so the response does not reveal whether the wallet
# exists. The hint matters: biometric wallets are sealed with a random vault
# password that was never shown, so /auth/login can never succeed for them
# (rapport 210 §9.4). They must use /register (empreinte / visage).
LOGIN_FAILED_DETAIL = (
    "Identifiants invalides. Wallet créé par empreinte ou visage ? "
    "Utilisez la connexion biométrique (/register), pas le mot de passe."
)


def _log_login_failure(wallet_name: str, reason: str, request: Request) -> None:
    """Audit line for 401s: wallet name + reason, never the password (rapport 210 §9.8-E)."""
    client = request.client.host if request.client else "?"
    logger.warning("Login failed wallet=%s reason=%s client=%s", wallet_name, reason, client)


class LoginRequest(BaseModel):
    name: str = Field(min_length=1, description="Nom du wallet / identifiant")
    password: str = Field(min_length=1, description="Mot de passe du compte")


class VerifyRequest(BaseModel):
    address: str = Field(min_length=8, description="Adresse artcb1xxx du wallet")
    challenge: str = Field(min_length=8, description="Nonce hex reçu via GET /challenge")
    signature: str = Field(min_length=8, description="Signature Ed25519 hex du challenge")


# --------------------------------------------------------------------------- #
#  Helper : vérification de session (Depends)
# --------------------------------------------------------------------------- #

def require_session(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """
    Dependency FastAPI : extrait et valide le token de session Bearer.
    Retourne le record de session ou lève 401.
    Utilisé pour protéger /api-keys/generate et tout endpoint authentifié.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentification requise. POST /api/v1/auth/login d'abord.",
        )
    raw = authorization.removeprefix("Bearer ").strip()
    # Les tokens de session commencent par "sess_"
    if not raw.startswith("sess_"):
        raise HTTPException(
            status_code=401,
            detail="Token de session invalide (format sess_xxx attendu). Utilisez /auth/login.",
        )
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    _sessions_ensure_loaded(_sessions)
    record = _sessions.get(token_hash)
    if not record:
        raise HTTPException(status_code=401, detail="Session expirée ou invalide. Reconnectez-vous.")
    now = time.time()
    if now > record["expires_at"]:
        del _sessions[token_hash]
        _sessions_save(_sessions)
        raise HTTPException(status_code=401, detail="Session expirée. Reconnectez-vous.")
    # R320 (2026-09-11T21:30:00Z) — inactivité + appareil.
    idle_ttl = int(record.get("idle_ttl") or _SESSION_IDLE_TTL)
    last_seen = float(record.get("last_seen") or record["created_at"])
    if idle_ttl > 0 and (now - last_seen) > idle_ttl:
        del _sessions[token_hash]
        _sessions_save(_sessions)
        raise HTTPException(status_code=401, detail="session_idle_timeout")
    bound_fp = record.get("device_fp") or ""
    if bound_fp and _bind_device_enforced():
        current_fp = device_fingerprint(request)
        if current_fp and current_fp != bound_fp:
            logger.warning(
                "Session %s rejouée depuis un autre appareil", record.get("session_id"),
            )
            raise HTTPException(status_code=401, detail="session_device_mismatch")
    record["last_seen"] = now
    _sessions_save(_sessions)
    return record


# --------------------------------------------------------------------------- #
#  Endpoints
# --------------------------------------------------------------------------- #

# P0-A (2026-09-16) — /auth/login déprécié. Code conservé (R299 : jamais supprimer).
# Les wallets classiques existants restent fonctionnels.
# Nouveaux clients → /auth/verify (clé privée) ou /auth/webauthn/login (biométrie).
_LOGIN_DEPRECATED_HINT = (
    "DEPRECATED: /auth/login (name+password) est déprécié. "
    "Utilisez /auth/verify (clé privée + challenge) ou /auth/webauthn/login (biométrie). "
    "Les wallets HumanIdentity ARTCB n'ont pas de mot de passe connu."
)

from fastapi.responses import JSONResponse


@router.post("/login", summary="[DÉPRÉCIÉ] Connexion par nom + mot de passe")
def login(body: LoginRequest, request: Request) -> JSONResponse:
    """
    [DÉPRÉCIÉ — P0-A 2026-09-16] Connexion classique : identifiant + mot de passe.

    Ce chemin sera supprimé dans une future version.
    Voies recommandées :
      - GET  /auth/challenge  + POST /auth/verify  → signature clé privée
      - POST /auth/webauthn/login/options + /verify → biométrie (empreinte, Face ID)

    Pour les wallets classiques existants uniquement.
    """
    from src.artcb.wallet.encryption import decrypt_private_key
    from src.artcb.wallet.manager import WalletManager

    wm = WalletManager()
    key_path = wm.wallet_dir / f"{body.name}.key"
    if not key_path.exists():
        _log_login_failure(body.name, "wallet_unknown", request)
        raise HTTPException(status_code=401, detail=LOGIN_FAILED_DETAIL)

    try:
        raw = key_path.read_bytes()
        seed: bytes | None = None
        try:
            seed = decrypt_private_key(raw, body.password)
        except Exception:
            seed = None
        if seed is None:
            _log_login_failure(body.name, "password_mismatch", request)
            raise HTTPException(status_code=401, detail=LOGIN_FAILED_DETAIL)
    except HTTPException:
        raise
    except Exception:
        _log_login_failure(body.name, "key_unreadable", request)
        raise HTTPException(status_code=401, detail=LOGIN_FAILED_DETAIL)

    # Reconstruire l'adresse depuis la seed déjà déchiffrée
    from nacl import signing as _signing
    from src.artcb.wallet.address import address_from_signing_key as _addr
    signing_key = _signing.SigningKey(seed)
    address = _addr(signing_key)

    logger.warning(
        "DEPRECATED /auth/login used: wallet=%s — steer to /auth/verify or /auth/webauthn/login",
        body.name,
    )
    issued = issue_session(wallet_name=body.name, address=address, request=request)
    issued["message"] = "Connecté. Utilisez session_token dans Authorization: Bearer <token>"
    issued["deprecated"] = True
    issued["deprecation_hint"] = _LOGIN_DEPRECATED_HINT
    issued["recommended_path"] = "/auth/verify (clé privée) ou /auth/webauthn/login (biométrie)"

    return JSONResponse(
        content=issued,
        headers={
            "Deprecation": "true",
            "Sunset": "2027-01-01",
            "Link": '</api/v1/auth/verify>; rel="successor-version"',
        },
    )


@router.get("/challenge", summary="Obtenir un nonce pour l'authentification par signature")
def get_challenge() -> dict:
    """
    Retourne un nonce aléatoire (challenge) que l'utilisateur doit signer
    avec sa clé privée Ed25519 pour prouver qu'il en est le propriétaire.

    Le challenge expire dans 5 minutes.
    """
    challenge = secrets.token_hex(32)
    _challenges[challenge] = time.time() + _CHALLENGE_TTL
    logger.debug("Challenge issued: %s", challenge[:16])
    return {
        "challenge": challenge,
        "expires_in": _CHALLENGE_TTL,
        "instructions": (
            "Signez ce challenge avec votre clé privée Ed25519, "
            "puis POST /auth/verify avec {address, challenge, signature}."
        ),
    }


@router.post("/verify", summary="Vérifier signature Ed25519 du challenge")
def verify_signature(body: VerifyRequest, request: Request) -> dict:
    """
    Vérifie que l'utilisateur contrôle la clé privée correspondant à l'adresse.

    Flow :
      1. GET /auth/challenge  → nonce
      2. Client signe le nonce avec sa clé privée
      3. POST /auth/verify    → serveur vérifie, crée session
    """
    from src.artcb.wallet.manager import WalletManager

    # Vérifier que le challenge existe et n'est pas expiré
    exp = _challenges.get(body.challenge)
    if not exp:
        raise HTTPException(status_code=400, detail="Challenge inconnu")
    if time.time() > exp:
        del _challenges[body.challenge]
        raise HTTPException(status_code=400, detail="Challenge expiré — en demandez un nouveau")

    # Retrouver la clé publique associée à cette adresse depuis les métadonnées JSON
    # (la clé publique est dans le .json, pas dans le .key chiffré — pas de déchiffrement requis)
    from nacl import signing as _signing
    wm = WalletManager()
    wallets = wm.list_wallets()
    wallet_record = next(
        (w for w in wallets if w.get("address") == body.address), None
    )
    if not wallet_record:
        raise HTTPException(status_code=404, detail="Adresse inconnue sur ce nœud")
    wallet_name = wallet_record["name"]

    try:
        # La clé publique est stockée en clair dans le .json — pas besoin de déchiffrer
        pub_hex = wallet_record.get("public_key_hex", "")
        if not pub_hex:
            raise HTTPException(status_code=500, detail="Clé publique manquante dans les métadonnées")
        verify_key = _signing.VerifyKey(bytes.fromhex(pub_hex))
        sig_bytes = bytes.fromhex(body.signature)
        challenge_bytes = bytes.fromhex(body.challenge)
        verify_key.verify(challenge_bytes, sig_bytes)
    except (BadSignatureError, ValueError):
        raise HTTPException(status_code=401, detail="Signature invalide")

    # Challenge utilisé : le supprimer (usage unique)
    del _challenges[body.challenge]

    logger.info("Verify OK: address=%s wallet=%s", body.address[:16], wallet_name)
    return issue_session(wallet_name=wallet_name, address=body.address, request=request)


@router.get("/me", summary="Identité de la session courante (user, pas opérateur)")
def auth_me(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Who is calling: human session, agent under session, or nobody.

    Operator ``artcb_`` keys are not a user. Use ``/api/v1/api-keys/me`` for those.
    """
    agent_id = (request.headers.get("x-artcb-agent-id") or "").strip() or None
    if not authorization or not authorization.startswith("Bearer "):
        return {
            "authenticated": False,
            "kind": "anonymous",
            "address": None,
            "wallet_name": None,
            "agent_id": agent_id,
            "is_user": False,
            "is_operator": False,
        }
    raw = authorization.removeprefix("Bearer ").strip()
    if raw.startswith("sess_"):
        record = require_session(request, authorization)
        kind = "agent" if agent_id else "human"
        return {
            "authenticated": True,
            "kind": kind,
            "address": record.get("address"),
            "wallet_name": record.get("wallet_name"),
            "agent_id": agent_id,
            "parent_address": record.get("address") if kind == "agent" else None,
            "is_user": True,
            "is_operator": False,
            "unique_human_proven": bool(record.get("unique_human_proven")),
            "expires_at": record.get("expires_at"),
        }
    if raw.startswith("artcb_"):
        return {
            "authenticated": True,
            "kind": "operator_or_api_key",
            "address": None,
            "wallet_name": None,
            "agent_id": agent_id,
            "is_user": False,
            "is_operator": True,
            "hint": "Bearer artcb_ n'est pas une session humaine. POST /auth/login.",
        }
    return {
        "authenticated": False,
        "kind": "unrecognized",
        "address": None,
        "is_user": False,
        "is_operator": False,
    }


@router.post("/logout", summary="Déconnecter la session courante")
def logout(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Invalide le token de session."""
    if authorization and authorization.startswith("Bearer sess_"):
        raw = authorization.removeprefix("Bearer ").strip()
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        _sessions_ensure_loaded(_sessions)
        _sessions.pop(token_hash, None)
        _sessions_save(_sessions)
    return {"logged_out": True}


# --------------------------------------------------------------------------- #
#  R320 (2026-09-11T21:30:00Z) — inventaire et révocation des sessions
# --------------------------------------------------------------------------- #

@router.get("/sessions", summary="Lister mes sessions actives (jamais les tokens)")
def list_my_sessions(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Un utilisateur doit pouvoir voir d'où il est connecté.

    Ne renvoie jamais un token ni son hash complet : seulement un ``session_id``
    court, l'empreinte d'appareil tronquée et les horodatages.
    """
    record = require_session(request, authorization)
    _prune_sessions()
    address = record.get("address")
    rows = [
        {
            "session_id": r.get("session_id"),
            "wallet_name": r.get("wallet_name"),
            "created_at": r.get("created_at"),
            "last_seen": r.get("last_seen"),
            "expires_at": r.get("expires_at"),
            "device_fp_prefix": (r.get("device_fp") or "")[:8],
            "current": r.get("session_id") == record.get("session_id"),
        }
        for r in _sessions.values()
        if r.get("address") == address
    ]
    return {
        "address": address,
        "active_sessions": len(rows),
        "sessions": sorted(rows, key=lambda x: x["created_at"] or 0),
        "absolute_ttl_s": _SESSION_TTL,
        "idle_ttl_s": _SESSION_IDLE_TTL,
        "device_binding_enforced": _bind_device_enforced(),
    }


class RevokeRequest(BaseModel):
    session_id: str = Field(min_length=4, description="session_id retourné par GET /auth/sessions")


@router.post("/revoke", summary="Révoquer une de mes sessions par session_id")
def revoke_session(
    body: RevokeRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Révocation ciblée : on ne peut révoquer que ses propres sessions."""
    record = require_session(request, authorization)
    address = record.get("address")
    target = [
        h for h, r in _sessions.items()
        if r.get("session_id") == body.session_id and r.get("address") == address
    ]
    if not target:
        raise HTTPException(status_code=404, detail="session_not_found_for_this_address")
    for h in target:
        _sessions.pop(h, None)
    _sessions_save(_sessions)
    logger.info("Session %s révoquée par son propriétaire", body.session_id)
    return {"revoked": len(target), "session_id": body.session_id}


@router.post("/logout-all", summary="Révoquer toutes mes sessions (appareil perdu)")
def logout_all(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Déconnecte partout : le geste à faire quand un appareil est perdu."""
    record = require_session(request, authorization)
    address = record.get("address")
    victims = [h for h, r in _sessions.items() if r.get("address") == address]
    for h in victims:
        _sessions.pop(h, None)
    _sessions_save(_sessions)
    logger.info("logout-all : %d sessions révoquées pour %s", len(victims), str(address)[:16])
    return {"revoked": len(victims), "address": address}


# --------------------------------------------------------------------------- #
#  WebAuthn ARTCB — Login biométrique template (P0-A v2 — 2026-09-17)
#
#  Flux ARTCB biométrique (template_hex) — DISTINCT du flux FIDO2 standard :
#    1. POST /auth/webauthn/biometric/options  → challenge
#    2. (client) capture empreinte → calcule template_bytes + template_hex
#    3. POST /auth/webauthn/biometric/verify   → vérif unicité HumanIdentityRecord
#                                               → session si identité trouvée
#
#  NOTE R384 : Renommé /biometric/ pour éviter la collision avec
#  webauthn_routes.py qui expose /webauthn/login/options pour le flux FIDO2
#  standard (credential navigator). Les deux routes coexistaient sur la même
#  URL — FastAPI enregistrait la dernière (webauthn_router écrasait auth_router).
#
#  DIFFÉRENCE AVEC WEBAUTHN FIDO2 CLASSIQUE :
#    - Pas de credential FIDO2 local : c'est l'identité ARTCB HumanIdentityRecord
#      qui est la source de vérité (spec §1–§5).
#    - Le template biométrique est comparé au template_hash_hex enregistré
#      dans le HumanIdentityRecord (stub hash exact — production : FHE/TEE).
#    - Aucune image brute ni private key n'est transmise.
#
#  HONNÊTETÉ :
#    - unique_human_proven = False (hash exact — pas de matching FHE certifié)
#    - CERTIFIED_100 = False
# --------------------------------------------------------------------------- #

_webauthn_challenges: dict[str, float] = {}  # challenge_hex → expires_at


class WebAuthnLoginOptionsRequest(BaseModel):
    """Options pour initier le login biométrique ARTCB."""
    hint: str = Field(
        default="fingerprint",
        description="Type de biométrie souhaité : fingerprint | face | qr-smartphone",
    )


class WebAuthnLoginVerifyRequest(BaseModel):
    """Vérification du login biométrique ARTCB.

    Le client fournit :
      - challenge  : le challenge obtenu depuis /options
      - template_hex : le template biométrique normalisé (hex) — JAMAIS une image brute

    Note : template_hex doit être ≥ 64 chars (32 bytes minimum pour un template normalisé).
    L'image brute (champs 'image', 'photo', 'raw') est rejetée.
    """
    challenge: str = Field(min_length=64, max_length=64, description="Challenge hex obtenu via /options")
    template_hex: str = Field(min_length=64, description="Template biométrique normalisé (hex) — pas d'image brute")
    human_id: str | None = Field(default=None, description="HumanID optionnel pour cibler une identité existante")


@router.post(
    "/webauthn/biometric/options",
    summary="Initier le login biométrique ARTCB template (étape 1/2)",
    response_description="Challenge à signer biométriquement",
)
def webauthn_biometric_options(body: WebAuthnLoginOptionsRequest) -> dict:
    """Émet un challenge pour le login biométrique ARTCB (flux template_hex).

    DISTINCT du flux FIDO2 standard (/auth/webauthn/login/options).
    L'utilisateur doit ensuite capturer son empreinte/visage, dériver le
    template biométrique, et POST /auth/webauthn/biometric/verify avec ce
    challenge et le template_hex normalisé.

    OVH1 bloqué — réponse exclusivement depuis N2/N3/N4.
    """
    challenge = secrets.token_hex(32)
    _webauthn_challenges[challenge] = time.time() + _CHALLENGE_TTL
    return {
        "challenge": challenge,
        "expires_in": _CHALLENGE_TTL,
        "hint": body.hint,
        "instructions": (
            "Capturez votre empreinte biométrique, dérivez le template normalisé (hex ≥ 64 chars), "
            "puis POST /auth/webauthn/login/verify avec {challenge, template_hex}. "
            "Ne transmettez jamais l'image brute — rejeté HTTP 400."
        ),
        "certified_100": False,
        "unique_human_proven": False,
    }


@router.post(
    "/webauthn/biometric/verify",
    summary="Vérifier le login biométrique ARTCB template (étape 2/2)",
    response_description="Session token si identité biométrique trouvée",
)
def webauthn_biometric_verify(body: WebAuthnLoginVerifyRequest, request: Request) -> dict:
    """Vérifie le template biométrique contre les identités HumanIdentityRecord enregistrées.

    Flux ARTCB template (DISTINCT du flux FIDO2 /auth/webauthn/login/verify).

    Flow :
      1. Charge tous les HumanIdentityRecord depuis l'état local
      2. Calcule BiometricCommitment sur le template présenté
      3. Compare template_hash_hex avec les records (check_uniqueness stub)
      4. Si match → émet une session pour ce wallet (si le HumanIdentityRecord a un wallet)
      5. Si no match → 401 (identité biométrique non enregistrée)

    HONNÊTETÉ :
      - Matching = hash exact (stub). Production : FHE/TEE.
      - unique_human_proven = False sur la session émise.
      - CERTIFIED_100 = False.
    """
    from src.artcb.crypto.homomorphic import commit_biometric_template
    from src.artcb.identity.biometric_onchain import check_uniqueness

    # ── Vérifier le challenge ────────────────────────────────────────────────
    exp = _webauthn_challenges.get(body.challenge)
    if not exp:
        raise HTTPException(status_code=400, detail="webauthn_challenge_unknown")
    if time.time() > exp:
        _webauthn_challenges.pop(body.challenge, None)
        raise HTTPException(status_code=400, detail="webauthn_challenge_expired")

    # ── Rejeter image brute ──────────────────────────────────────────────────
    # Le template_hex ne doit pas être une image (pas de magic bytes connus)
    try:
        tmpl_bytes = bytes.fromhex(body.template_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="template_hex_invalid_hex")

    PNG_MAGIC  = b"\x89PNG"
    JPEG_MAGIC = b"\xff\xd8\xff"
    BMP_MAGIC  = b"BM"
    if tmpl_bytes[:4] == PNG_MAGIC or tmpl_bytes[:3] == JPEG_MAGIC or tmpl_bytes[:2] == BMP_MAGIC:
        raise HTTPException(status_code=400, detail="raw_image_rejected — fournir un template normalisé")

    # ── Charger les HumanIdentityRecords ────────────────────────────────────
    from src.api.biometric_identity_routes import _load_records
    records = _load_records()

    # ── Filtrer optionnellement par human_id (avant le check "pas d'identité") ──
    # Si human_id est spécifié et introuvable → 404 (pas 401)
    if body.human_id:
        target_records = [r for r in records if r.get("human_id") == body.human_id]
        if not target_records:
            _webauthn_challenges.pop(body.challenge, None)
            raise HTTPException(status_code=404, detail=f"human_id_not_found: {body.human_id}")
    else:
        target_records = records

    if not target_records:
        _webauthn_challenges.pop(body.challenge, None)
        raise HTTPException(
            status_code=401,
            detail="biometric_identity_not_found — aucune identité biométrique enregistrée sur ce nœud",
        )

    # ── Calculer commitment sur le template présenté ────────────────────────
    try:
        commitment = commit_biometric_template(tmpl_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"commitment_error: {exc}")

    # ── Vérification d'unicité (match = identité trouvée) ───────────────────
    check = check_uniqueness(commitment, target_records)

    if not check.match_found:
        _webauthn_challenges.pop(body.challenge, None)
        raise HTTPException(
            status_code=401,
            detail=(
                "biometric_identity_not_found — aucune identité correspondante. "
                "Inscrivez-vous via POST /api/v1/identity/biometric/enroll."
            ),
        )

    # ── Challenge consommé (usage unique) ────────────────────────────────────
    _webauthn_challenges.pop(body.challenge, None)

    # ── Récupérer le wallet associé ─────────────────────────────────────────
    matched_record = next(
        (r for r in target_records if r.get("human_id") == check.existing_human_id),
        None,
    )
    wallet_address = (matched_record or {}).get("wallet_address") or ""
    wallet_name    = (matched_record or {}).get("wallet_name") or check.existing_human_id or "unknown"
    human_id       = check.existing_human_id or ""

    logger.info(
        "WebAuthn ARTCB login OK: human_id=%s wallet=%s (unique_human_proven=False)",
        human_id[:16] if human_id else "?", wallet_name,
    )

    session = issue_session(
        wallet_name=wallet_name,
        address=wallet_address,
        request=request,
    )
    return {
        **session,
        "human_id": human_id,
        "login_method": "webauthn_artcb_biometric",
        "unique_human_proven": False,
        "certified_100": False,
        "note": (
            "Login biométrique ARTCB — matching hash exact (stub). "
            "unique_human_proven=False jusqu'à validation FHE/TEE certifiée."
        ),
    }
