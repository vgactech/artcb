"""WebAuthn + camera face-unlock enrollment for www.artcb.me.

Fingerprint / Face ID = platform authenticator (WebAuthn).
Camera face (motor disability, no OS face unlock) = liveness + device secret.
Raw biometric images are rejected and never stored.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.auth_routes import issue_session
from src.artcb.security.webauthn_cose import public_key_from_cose
from src.artcb.security.webauthn_protocol import (
    WebAuthnError,
    assertion_options,
    b64u_decode,
    expected_origins,
    pop_pending,
    registration_options,
    rp_id_for_host,
    verify_assertion,
    verify_attestation,
)
from src.artcb.security.webauthn_store import (
    ALLOWED_MODALITIES,
    MODALITY_FACE,
    MODALITY_FINGERPRINT,
    credentials_for_wallet,
    find_credential,
    find_face,
    save_credential,
    save_face,
    update_sign_count,
)

logger = logging.getLogger("artcb.api.webauthn")
router = APIRouter(prefix="/api/v1/auth", tags=["auth-biometric"])

_face_challenges: dict[str, dict[str, Any]] = {}
_FACE_TTL = 300

Modality = Literal["fingerprint", "face", "both"]


class RegisterBeginBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    modality: Modality = MODALITY_FINGERPRINT
    create_wallet: bool = True


class CredentialResponse(BaseModel):
    id: str
    rawId: str | None = None
    type: str = "public-key"
    response: dict[str, str]
    authenticatorAttachment: str | None = None
    clientExtensionResults: dict[str, Any] | None = None


class RegisterFinishBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    modality: Modality = MODALITY_FINGERPRINT
    credential: CredentialResponse
    create_wallet: bool = True


class LoginBeginBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    modality: Modality | None = None


class LoginFinishBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    credential: CredentialResponse


class FaceBeginBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    create_wallet: bool = True


class FaceFinishBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    nonce: str = Field(min_length=8)
    device_secret: str = Field(min_length=32, max_length=128)
    liveness_ok: bool
    image: str | None = None
    photo: str | None = None
    frame: str | None = None
    create_wallet: bool = True


def _host_scheme(request: Request) -> tuple[str, str]:
    host = (request.headers.get("host") or request.url.hostname or "localhost").split(",")[0].strip()
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
    return host, proto


def _reject_raw_image(body: BaseModel) -> None:
    extra = body.model_dump()
    for key in ("image", "photo", "frame", "biometric", "template_raw"):
        val = extra.get(key)
        if isinstance(val, str) and val.strip():
            raise HTTPException(
                status_code=400,
                detail="raw_biometric_rejected — l'image faciale ne quitte jamais l'appareil",
            )


def _wallet_exists(name: str) -> bool:
    from src.artcb.wallet.manager import WalletManager

    return (WalletManager().wallet_dir / f"{name}.key").exists()


def _create_wallet_if_needed(name: str, *, create: bool) -> dict[str, Any]:
    from src.artcb.wallet.manager import WalletManager

    wm = WalletManager()
    key_path = wm.wallet_dir / f"{name}.key"
    if key_path.exists():
        wallets = wm.list_wallets()
        rec = next((w for w in wallets if w.get("name") == name), None)
        if not rec:
            raise HTTPException(status_code=500, detail="wallet_metadata_missing")
        return {
            "created": False,
            "name": name,
            "address": rec.get("address"),
            "seed_hex": None,
        }
    if not create:
        raise HTTPException(status_code=404, detail="wallet_unknown")
    vault = secrets.token_urlsafe(32)
    wallet = wm.create_wallet(name=name, user_password=vault)
    seed_hex = wallet.signing_key.encode().hex()
    logger.info("Biometric wallet created name=%s address=%s", name, wallet.address)
    return {
        "created": True,
        "name": name,
        "address": wallet.address,
        "seed_hex": seed_hex,
        "WARNING": (
            "SAUVEGARDEZ votre seed_hex MAINTENANT — "
            "c'est votre clé privée, elle ne sera plus jamais affichée. "
            "L'empreinte / le visage déverrouillent ce nœud, pas la seed."
        ),
    }


def _mark_auth_methods(name: str, method: str) -> None:
    import json

    from src.artcb.wallet.manager import WalletManager

    meta_path = WalletManager().wallet_dir / f"{name}.json"
    if not meta_path.is_file():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    methods = list(meta.get("auth_methods") or [])
    if method not in methods:
        methods.append(method)
    meta["auth_methods"] = methods
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


@router.get("/webauthn/status")
def webauthn_status(name: str) -> dict[str, Any]:
    creds = credentials_for_wallet(name)
    face = find_face(name)
    return {
        "wallet_name": name,
        "wallet_exists": _wallet_exists(name),
        "webauthn": [
            {"modality": c.get("modality"), "credential_id_prefix": str(c.get("credential_id") or "")[:12]}
            for c in creds
        ],
        "fingerprint_enrolled": any(c.get("modality") == MODALITY_FINGERPRINT for c in creds),
        "face_webauthn_enrolled": any(c.get("modality") == MODALITY_FACE for c in creds),
        "face_camera_enrolled": bool(face),
        "raw_biometric_stored": False,
    }


@router.post("/webauthn/register/options")
def webauthn_register_options(body: RegisterBeginBody, request: Request) -> dict[str, Any]:
    if body.modality not in ALLOWED_MODALITIES:
        raise HTTPException(status_code=400, detail="modality_invalid")
    host, _scheme = _host_scheme(request)
    user_id = hashlib.sha256(f"artcb-wallet:{body.name}".encode()).digest()[:32]
    modality = MODALITY_FACE if body.modality == "both" else body.modality
    # "both" starts with fingerprint; the client then enrolls face.
    if body.modality == "both":
        modality = MODALITY_FINGERPRINT
    options = registration_options(
        wallet_name=body.name,
        user_id=user_id,
        host=host,
        modality=modality,
    )
    return {
        "publicKey": options,
        "create_wallet": body.create_wallet,
        "raw_biometric_never_stored": True,
        "modality": modality,
        "next_modality": MODALITY_FACE if body.modality == "both" else None,
    }


@router.post("/webauthn/register/verify")
def webauthn_register_verify(body: RegisterFinishBody, request: Request) -> dict[str, Any]:
    host, scheme = _host_scheme(request)
    rp_id = rp_id_for_host(host)
    origins = expected_origins(host, scheme)
    try:
        client_json = b64u_decode(body.credential.response["clientDataJSON"])
        att_obj = b64u_decode(body.credential.response["attestationObject"])
        client_data = json.loads(client_json.decode("utf-8"))
        challenge = client_data.get("challenge")
        if not isinstance(challenge, str):
            raise WebAuthnError("challenge_missing")
        pending = pop_pending(challenge, kind="create", wallet_name=body.name)
        verified = verify_attestation(
            client_data_json=client_json,
            attestation_object=att_obj,
            challenge_b64=challenge,
            rp_id=pending.get("rp_id") or rp_id,
            origins=origins,
        )
    except (KeyError, ValueError, WebAuthnError) as exc:
        raise HTTPException(status_code=400, detail=str(exc) if str(exc) else "webauthn_register_failed") from exc

    wallet = _create_wallet_if_needed(body.name, create=body.create_wallet)
    modality = body.modality if body.modality != "both" else pending.get("modality") or MODALITY_FINGERPRINT
    save_credential(
        {
            "credential_id": verified["credential_id"],
            "cose_b64": verified["cose_b64"],
            "sign_count": verified["sign_count"],
            "wallet_name": body.name,
            "address": wallet["address"],
            "modality": modality,
            "rp_id": verified["rp_id"],
        }
    )
    _mark_auth_methods(body.name, f"webauthn_{modality}")
    session = issue_session(wallet_name=body.name, address=str(wallet["address"]))
    out: dict[str, Any] = {
        "ok": True,
        "enrolled": modality,
        "raw_biometric_stored": False,
        **session,
        "wallet_created": wallet["created"],
        "address": wallet["address"],
        "name": body.name,
    }
    if wallet.get("seed_hex"):
        out["seed_hex"] = wallet["seed_hex"]
        out["WARNING"] = wallet.get("WARNING")
    return out


@router.post("/webauthn/login/options")
def webauthn_login_options(body: LoginBeginBody, request: Request) -> dict[str, Any]:
    if not _wallet_exists(body.name):
        raise HTTPException(status_code=404, detail="wallet_unknown")
    creds = credentials_for_wallet(body.name)
    if body.modality:
        creds = [c for c in creds if c.get("modality") == body.modality]
    if not creds:
        raise HTTPException(status_code=404, detail="webauthn_not_enrolled")
    host, _scheme = _host_scheme(request)
    options = assertion_options(
        wallet_name=body.name,
        host=host,
        allow_credential_ids=[str(c["credential_id"]) for c in creds],
        modality=body.modality or str(creds[0].get("modality") or MODALITY_FINGERPRINT),
    )
    return {"publicKey": options, "raw_biometric_never_stored": True}


@router.post("/webauthn/login/verify")
def webauthn_login_verify(body: LoginFinishBody, request: Request) -> dict[str, Any]:
    host, scheme = _host_scheme(request)
    origins = expected_origins(host, scheme)
    cred_id = body.credential.id
    stored = find_credential(cred_id)
    if not stored or stored.get("wallet_name") != body.name:
        raise HTTPException(status_code=401, detail="credential_unknown")
    try:
        client_json = b64u_decode(body.credential.response["clientDataJSON"])
        auth_data = b64u_decode(body.credential.response["authenticatorData"])
        signature = b64u_decode(body.credential.response["signature"])
        client_data = json.loads(client_json.decode("utf-8"))
        challenge = client_data.get("challenge")
        if not isinstance(challenge, str):
            raise WebAuthnError("challenge_missing")
        pending = pop_pending(challenge, kind="get", wallet_name=body.name)
        public_key = public_key_from_cose(b64u_decode(str(stored["cose_b64"])))
        sign_count = verify_assertion(
            client_data_json=client_json,
            authenticator_data=auth_data,
            signature=signature,
            challenge_b64=challenge,
            rp_id=str(pending.get("rp_id") or stored.get("rp_id") or rp_id_for_host(host)),
            origins=origins,
            public_key=public_key,
            previous_sign_count=int(stored.get("sign_count") or 0),
        )
    except (KeyError, ValueError, WebAuthnError) as exc:
        raise HTTPException(status_code=401, detail=str(exc) if str(exc) else "webauthn_login_failed") from exc
    update_sign_count(cred_id, sign_count)
    session = issue_session(wallet_name=body.name, address=str(stored.get("address") or ""))
    session["ok"] = True
    session["modality"] = stored.get("modality")
    session["raw_biometric_stored"] = False
    return session


@router.post("/face/enroll/options")
def face_enroll_options(body: FaceBeginBody) -> dict[str, Any]:
    nonce = secrets.token_hex(32)
    _face_challenges[nonce] = {
        "wallet_name": body.name,
        "kind": "enroll",
        "expires_at": time.time() + _FACE_TTL,
        "create_wallet": body.create_wallet,
    }
    return {
        "nonce": nonce,
        "liveness_required": True,
        "camera_facing_mode": "user",
        "raw_biometric_never_stored": True,
        "instructions": (
            "Placez votre visage dans le cadre. Aucune photo n'est envoyée au serveur. "
            "Après la liveness, un secret d'appareil est lié au wallet."
        ),
    }


@router.post("/face/enroll/verify")
def face_enroll_verify(body: FaceFinishBody) -> dict[str, Any]:
    _reject_raw_image(body)
    rec = _face_challenges.pop(body.nonce, None)
    if not rec or rec.get("wallet_name") != body.name or rec.get("kind") != "enroll":
        raise HTTPException(status_code=400, detail="face_challenge_invalid")
    if time.time() > rec["expires_at"]:
        raise HTTPException(status_code=400, detail="face_challenge_expired")
    if not body.liveness_ok:
        raise HTTPException(status_code=400, detail="face_liveness_required")
    wallet = _create_wallet_if_needed(body.name, create=body.create_wallet)
    secret_hash = hashlib.sha256(body.device_secret.encode("utf-8")).hexdigest()
    save_face(
        {
            "wallet_name": body.name,
            "address": wallet["address"],
            "secret_hash": secret_hash,
            "liveness": True,
        }
    )
    _mark_auth_methods(body.name, "face_camera")
    session = issue_session(wallet_name=body.name, address=str(wallet["address"]))
    out: dict[str, Any] = {
        "ok": True,
        "enrolled": "face_camera",
        "raw_biometric_stored": False,
        **session,
        "wallet_created": wallet["created"],
        "address": wallet["address"],
        "name": body.name,
    }
    if wallet.get("seed_hex"):
        out["seed_hex"] = wallet["seed_hex"]
        out["WARNING"] = wallet.get("WARNING")
    return out


@router.post("/face/login")
def face_login(body: FaceFinishBody) -> dict[str, Any]:
    _reject_raw_image(body)
    rec = _face_challenges.pop(body.nonce, None)
    if not rec or rec.get("wallet_name") != body.name:
        raise HTTPException(status_code=400, detail="face_challenge_invalid")
    if time.time() > rec["expires_at"]:
        raise HTTPException(status_code=400, detail="face_challenge_expired")
    if not body.liveness_ok:
        raise HTTPException(status_code=401, detail="face_liveness_required")
    stored = find_face(body.name)
    if not stored:
        raise HTTPException(status_code=404, detail="face_not_enrolled")
    digest = hashlib.sha256(body.device_secret.encode("utf-8")).hexdigest()
    if digest != stored.get("secret_hash"):
        raise HTTPException(status_code=401, detail="face_unlock_invalid")
    session = issue_session(wallet_name=body.name, address=str(stored.get("address") or ""))
    session["ok"] = True
    session["modality"] = "face_camera"
    session["raw_biometric_stored"] = False
    return session


@router.post("/face/login/options")
def face_login_options(body: FaceBeginBody) -> dict[str, Any]:
    if not find_face(body.name):
        raise HTTPException(status_code=404, detail="face_not_enrolled")
    nonce = secrets.token_hex(32)
    _face_challenges[nonce] = {
        "wallet_name": body.name,
        "kind": "login",
        "expires_at": time.time() + _FACE_TTL,
    }
    return {
        "nonce": nonce,
        "liveness_required": True,
        "camera_facing_mode": "user",
        "raw_biometric_never_stored": True,
    }
