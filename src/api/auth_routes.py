"""Authentification utilisateur ARTCB — login, challenge, verify.

Protocole :
  1. POST /auth/login     — login classique (name + password)
  2. GET  /auth/challenge — nonce pour signature crypto
  3. POST /auth/verify    — vérification signature Ed25519 du challenge
  4. POST /auth/logout    — invalide le token de session

L'API key (/api-keys/generate) n'est utilisable QU'APRÈS authentification.
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

@router.post("/login", summary="Connexion par nom + mot de passe")
def login(body: LoginRequest, request: Request) -> dict:
    """
    Connexion classique : identifiant (nom du wallet) + mot de passe.

    Le mot de passe est utilisé pour déchiffrer la seed Ed25519 stockée
    sur le serveur. Si le déchiffrement réussit, une session est créée.

    Retourne un token de session `sess_xxx` valide 30 minutes.
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
    # (pas besoin de rappeler load_wallet qui re-déchiffrerait avec la passphrase serveur)
    from nacl import signing as _signing
    from src.artcb.wallet.address import address_from_signing_key as _addr
    signing_key = _signing.SigningKey(seed)
    address = _addr(signing_key)

    logger.info("Login successful: wallet=%s address=%s", body.name, address)
    issued = issue_session(wallet_name=body.name, address=address, request=request)
    issued["message"] = "Connecté. Utilisez session_token dans Authorization: Bearer <token>"
    return issued


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
