"""WebAuthn + camera face-unlock enrollment for www.artcb.me.

Fingerprint / Face ID = platform authenticator (WebAuthn).
Camera face (motor disability, no OS face unlock) = liveness + device secret.
Raw biometric images are rejected and never stored.

Honest scope (rapport 214 §Priorité 1): the camera path is a *local face
presence check* bound to a device secret. It is NOT a proof that the account
holder is a unique living human. ASSURANCE_LEVELS below is what each method
actually demonstrates; every enrollment / login transition is written to the
audit log (`artcb.api.webauthn.audit`) so a divergence audit can replay it.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

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
    broadcast_credential,
    credentials_for_wallet,
    find_credential,
    find_face,
    receive_credential,
    save_credential,
    save_face,
    update_sign_count,
)

logger = logging.getLogger("artcb.api.webauthn")
audit = logging.getLogger("artcb.api.webauthn.audit")
router = APIRouter(prefix="/api/v1/auth", tags=["auth-biometric"])

_face_challenges: dict[str, dict[str, Any]] = {}
_FACE_TTL = 300

# What each method proves. Level numbers follow rapport 214 (0-3). None of the
# methods available today reaches level 3 (unique human, independently verified).
ASSURANCE_LEVELS: dict[str, dict[str, Any]] = {
    "password": {
        "level": 0,
        "proves": "knowledge of the wallet password on this node",
        "does_not_prove": "human presence, uniqueness",
    },
    "webauthn_fingerprint": {
        "level": 2,
        "proves": "possession of the enrolled device + OS user verification",
        "does_not_prove": "that the person is a unique human worldwide",
    },
    "webauthn_face": {
        "level": 2,
        "proves": "possession of the enrolled device + OS user verification (same sensor path as fingerprint)",
        "does_not_prove": "camera-based liveness, uniqueness",
    },
    "face_camera": {
        "level": 1,
        "proves": "local face presence in frame + possession of the device secret",
        "does_not_prove": "identity, liveness against photo/video/mask, uniqueness",
        # R350 (2026-09-17) — spec §4 rapport 367/370 :
        # face_camera N'EST PAS une voie d'authentification principale ARTCB.
        # Elle reste disponible pour accessibilité motrice uniquement.
        # En production, toujours orienter vers WebAuthn natif.
        "production_status": "FALLBACK_ACCESSIBILITY_ONLY",
        "not_accepted_as": [
            "human_identity_proof",
            "unique_human_proof",
            "biometric_artcb_primary",
        ],
    },
}

# D-046 (2026-09-25) — face_camera INTERDIT dans ARTCB jusqu'à nouvel ordre.
# Aucune fonctionnalité face_camera ne doit être active ou accessible.
# Les endpoints /face/* retournent 410 Gone.
# La seule voie biométrique autorisée est WebAuthn/FIDO natif (Touch ID, Face ID OS,
# Windows Hello) — ARTCB ne reçoit jamais d'image faciale.
FACE_CAMERA_INACTIVE_PRODUCTION = True   # D-046 : forcé True
FACE_CAMERA_LABEL = "[D-046 DÉSACTIVÉ] face_camera interdit"


def _audit(event: str, *, wallet: str, request: Request | None = None, **fields: Any) -> None:
    """One line per transition. Never a secret, never an image, never a hash of them."""
    client = request.client.host if request is not None and request.client else "?"
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    audit.info("biometric event=%s wallet=%s client=%s %s", event, wallet, client, extra)

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


def _create_wallet_if_needed(
    name: str,
    *,
    create: bool,
    request: Request | None = None,
) -> dict[str, Any]:
    from src.artcb.wallet.manager import WalletManager
    from src.api.auth_routes import device_fingerprint as client_device_fingerprint
    from src.artcb.security.wallet_device_binding import WalletDeviceBindingError

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

    # R345: same client device limit as classic create (not HumanIdentity uniqueness)
    if request is not None:
        state = request.app.state.artcb
        client_fp = client_device_fingerprint(request)
        if state.wallet_device_binding and client_fp:
            try:
                state.wallet_device_binding.check_and_bind(
                    wallet_name=name,
                    device_fingerprint=client_fp,
                    env_type="client_ua_device_id_bio",
                )
            except WalletDeviceBindingError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "device_wallet_limit",
                        "message": str(exc),
                        "hint": (
                            "Un seul wallet par appareil navigateur. "
                            "WebAuthn/visage ≠ HumanIdentity unique mondiale."
                        ),
                        "binding_scope": "client",
                        "unique_human_proven": False,
                    },
                ) from exc

    vault = secrets.token_urlsafe(32)
    wallet = wm.create_wallet(name=name, user_password=vault)
    seed_hex = wallet.signing_key.encode().hex()
    logger.info("Biometric wallet created name=%s address=%s hybrid=%s", name, wallet.address, wallet.is_hybrid)
    # R361 — restitution complète des clés privées.
    # Ed25519 seed (32 octets) + ML-DSA-65 secret (4032 octets) affichés UNE SEULE FOIS.
    result: dict = {
        "created": True,
        "name": name,
        "address": wallet.address,
        "seed_hex": seed_hex,
        "WARNING": (
            "SAUVEGARDEZ seed_hex ET pqc_secret_key_hex MAINTENANT — "
            "ces clés privées ne seront plus jamais affichées. "
            "La biométrie déverrouille l'accès au nœud, pas les clés privées."
        ),
        "auth_method": "biometric_vault",
        "password_login_possible": False,
        "unique_human_proven": False,
    }
    # PQC : clé privée ML-DSA-65 si générée
    if wallet.pqc_secret_key is not None:
        result["pqc_secret_key_hex"] = wallet.pqc_secret_key.hex()
    if wallet.pqc_public_key_hex:
        result["pqc_public_key_hex"] = wallet.pqc_public_key_hex
    if wallet.address_v2:
        result["address_v2"] = wallet.address_v2
    return result


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
    methods = sorted({f"webauthn_{c.get('modality')}" for c in creds} | ({"face_camera"} if face else set()))
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
        "assurance": {m: ASSURANCE_LEVELS[m] for m in methods if m in ASSURANCE_LEVELS},
        "max_assurance_level": max((ASSURANCE_LEVELS[m]["level"] for m in methods if m in ASSURANCE_LEVELS), default=None),
        "unique_human_proven": False,
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
        _audit("webauthn_register_failed", wallet=body.name, request=request, reason=str(exc) or "invalid")
        raise HTTPException(status_code=400, detail=str(exc) if str(exc) else "webauthn_register_failed") from exc

    wallet = _create_wallet_if_needed(body.name, create=body.create_wallet, request=request)
    modality = body.modality if body.modality != "both" else pending.get("modality") or MODALITY_FINGERPRINT
    _audit(
        "webauthn_register_ok",
        wallet=body.name,
        request=request,
        modality=modality,
        wallet_created=wallet["created"],
        level=ASSURANCE_LEVELS[f"webauthn_{modality}"]["level"],
        existing_credentials=len(credentials_for_wallet(body.name)),
    )
    credential_record = {
        "credential_id": verified["credential_id"],
        "cose_b64": verified["cose_b64"],
        "sign_count": verified["sign_count"],
        "wallet_name": body.name,
        "address": wallet["address"],
        "modality": modality,
        "rp_id": verified["rp_id"],
    }
    save_credential(credential_record)
    # R387 — TASK-006 : fanout fire-and-forget vers les pairs officiels
    # Les credentials WebAuthn (credential_id + clé publique COSE) sont des données
    # publiques — elles peuvent être répliquées sans risque de confidentialité.
    broadcast_credential(credential_record)
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
        _audit("webauthn_login_failed", wallet=body.name, request=request, reason="credential_unknown")
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
        _audit("webauthn_login_failed", wallet=body.name, request=request, reason=str(exc) or "invalid")
        raise HTTPException(status_code=401, detail=str(exc) if str(exc) else "webauthn_login_failed") from exc
    update_sign_count(cred_id, sign_count)
    _audit("webauthn_login_ok", wallet=body.name, request=request, modality=stored.get("modality"), sign_count=sign_count)
    session = issue_session(wallet_name=body.name, address=str(stored.get("address") or ""))
    session["ok"] = True
    session["modality"] = stored.get("modality")
    session["raw_biometric_stored"] = False
    return session


@router.post("/face/enroll/options")
def face_enroll_options(body: FaceBeginBody) -> dict[str, Any]:  # noqa: ARG001
    # D-046 : face_camera désactivé — aucune opération faciale acceptée
    raise HTTPException(
        status_code=410,
        detail={
            "error": "face_camera_unsupported_d046",
            "message": "face_camera est interdit dans ARTCB (D-046). "
                       "Utiliser WebAuthn/FIDO natif (Touch ID, Face ID OS, Windows Hello).",
            "policy": "UNSUPPORTED_D046",
        },
    )


@router.post("/face/enroll/verify")
def face_enroll_verify(body: FaceFinishBody, request: Request) -> dict[str, Any]:  # noqa: ARG001
    # D-046 : face_camera désactivé — aucune opération faciale acceptée
    raise HTTPException(
        status_code=410,
        detail={
            "error": "face_camera_unsupported_d046",
            "message": "face_camera est interdit dans ARTCB (D-046). "
                       "Utiliser WebAuthn/FIDO natif (Touch ID, Face ID OS, Windows Hello).",
            "policy": "UNSUPPORTED_D046",
        },
    )


@router.post("/face/login")
def face_login(body: FaceFinishBody, request: Request) -> dict[str, Any]:  # noqa: ARG001
    # D-046 : face_camera désactivé — y compris le login
    raise HTTPException(
        status_code=410,
        detail={
            "error": "face_camera_unsupported_d046",
            "message": "face_camera est interdit dans ARTCB (D-046). "
                       "Utiliser WebAuthn/FIDO natif (Touch ID, Face ID OS, Windows Hello).",
            "policy": "UNSUPPORTED_D046",
        },
    )


@router.post("/face/login/options")
def face_login_options(body: FaceBeginBody) -> dict[str, Any]:  # noqa: ARG001
    # D-046 : face_camera désactivé — y compris les options de login
    raise HTTPException(
        status_code=410,
        detail={
            "error": "face_camera_unsupported_d046",
            "message": "face_camera est interdit dans ARTCB (D-046). "
                       "Utiliser WebAuthn/FIDO natif (Touch ID, Face ID OS, Windows Hello).",
            "policy": "UNSUPPORTED_D046",
        },
    )


# ─── R387 — TASK-006 : Endpoint de réception des credentials WebAuthn répliqués ───


class IdentityReceiveBody(BaseModel):
    """Corps de la requête POST /webauthn/identity/receive (fanout R387).

    Reçu d'un nœud pair via broadcast_credential().
    Seuls les champs publics sont attendus — jamais de clé privée.
    """
    credential_id: str
    cose_b64: str
    wallet_name: str
    address: str | None = None
    modality: str | None = None
    rp_id: str | None = None
    sign_count: int = 0


@router.post("/webauthn/identity/receive")
def webauthn_identity_receive(body: IdentityReceiveBody, request: Request) -> dict[str, Any]:
    """Reçoit un credential WebAuthn répliqué par un nœud pair (R387 — TASK-006).

    Ce endpoint est appelé par broadcast_credential() des autres nœuds.
    Il stocke le credential localement pour que ce nœud puisse authentifier
    l'utilisateur même si son wallet a été créé sur un autre nœud.

    Sécurité :
      - Seuls les champs publics sont traités (credential_id + clé publique COSE)
      - La clé privée ne passe jamais ici — elle ne quitte pas l'appareil utilisateur
      - Tout nœud peut appeler ce endpoint (pas d'auth Bearer requise pour le fanout
        entre nœuds officiels, car les données sont publiques par définition)

    DEBUG : toute réception est loguée dans artcb.api.webauthn.audit.
    """
    record = {
        "credential_id": body.credential_id,
        "cose_b64": body.cose_b64,
        "wallet_name": body.wallet_name,
        "address": body.address,
        "modality": body.modality,
        "rp_id": body.rp_id,
        "sign_count": body.sign_count,
    }
    source = request.headers.get("X-ARTCB-Fanout-Source", "unknown")
    stored = receive_credential(record)
    if not stored:
        _audit(
            "webauthn_identity_receive_rejected",
            wallet=body.wallet_name,
            request=request,
            source_node=source,
        )
        raise HTTPException(status_code=400, detail="identity_receive_invalid_record")
    _audit(
        "webauthn_identity_receive_ok",
        wallet=body.wallet_name,
        request=request,
        source_node=source,
        modality=str(body.modality),
    )
    logger.info(
        "webauthn_identity_receive: credential répliqué wallet=%s modality=%s depuis=%s",
        body.wallet_name, body.modality, source,
    )
    return {
        "ok": True,
        "stored": True,
        "wallet_name": body.wallet_name,
        "credential_id_prefix": body.credential_id[:12],
        "source_node": source,
    }
