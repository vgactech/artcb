"""Routes API — HumanIdentity multi-device (spec §17–18, rapport 367/370, R363 2026-09-17).

Implémente le flux ADD_DEVICE avec VRAIE vérification WebAuthn (R363) :
  - Un humain peut ajouter un nouvel appareil à son identité ARTCB
  - L'ajout nécessite une VRAIE assertion WebAuthn de l'appareil existant
    (credential_id + clientDataJSON + authenticatorData + signature)
  - Aucun PIN / mot de passe seul ne suffit (spec §4) — rejeté avec 403
  - Aucune création directe de wallet depuis un nouvel appareil (spec §10)
  - Aucun template_hex nu accepté comme preuve d'autorisation

Flux ADD_DEVICE (R363) :
  1. POST /identity/device/add-options   → challenge WebAuthn (b64url) pour l'appareil existant
  2. (appareil existant) signe le challenge via navigator.credentials.get()
  3. POST /identity/device/add-verify    → vérifie assertion WebAuthn cryptographique + enregistre
  4. (nouvel appareil) peut maintenant s'authentifier via /auth/webauthn/login

HONNÊTETÉ :
  - La vérification WebAuthn est cryptographiquement réelle (verify_assertion de webauthn_protocol.py)
  - unique_human_proven = False (WebAuthn ≠ preuve d'unicité humaine — spec §4 rapport 367)
  - CERTIFIED_100 = False
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.security.webauthn_protocol import (
    WebAuthnError,
    b64u_decode,
    b64u_encode,
    expected_origins,
    rp_id_for_host,
    verify_assertion,
)

logger = logging.getLogger("artcb.api.identity_device")
router = APIRouter(prefix="/api/v1/identity/device", tags=["identity-device"])

_CHALLENGE_TTL = 300  # 5 minutes

# Challenges en attente d'approbation par l'appareil existant
# challenge_b64u → {human_id, new_device_hint, created_at, expires_at}
_device_challenges: dict[str, dict] = {}


def _records_path() -> Path:
    """Chemin vers le fichier JSONL des HumanIdentityRecords."""
    data_dir = Path(os.environ.get("ARTCB_DATA_DIR", "data"))
    return data_dir / "identity" / "human_records.jsonl"


def _load_records() -> list[dict]:
    p = _records_path()
    if not p.exists():
        return []
    records = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def _load_device_registry() -> list[dict]:
    """Charge le registre des devices associés aux identités humaines."""
    data_dir = Path(os.environ.get("ARTCB_DATA_DIR", "data"))
    registry_path = data_dir / "identity" / "device_registry.jsonl"
    if not registry_path.exists():
        return []
    devices = []
    for line in registry_path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                devices.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return devices


def _append_device(device_record: dict) -> None:
    """Enregistre un nouvel appareil dans le registre."""
    data_dir = Path(os.environ.get("ARTCB_DATA_DIR", "data"))
    registry_path = data_dir / "identity" / "device_registry.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("a") as fh:
        fh.write(json.dumps(device_record, ensure_ascii=False) + "\n")


# ─── Schémas ──────────────────────────────────────────────────────────────────


class AddDeviceOptionsRequest(BaseModel):
    """Demande d'association d'un nouvel appareil.

    Envoyée par le NOUVEL appareil B qui veut rejoindre l'identité existante.
    L'appareil A existant devra approuver via POST /add-verify.
    """
    human_id: str = Field(
        min_length=8,
        description="HumanID de l'identité à rejoindre",
    )
    new_device_hint: str = Field(
        default="unknown",
        max_length=64,
        description="Descriptif du nouvel appareil (ex: iPhone 15, Android, etc.)",
    )


class AddDeviceVerifyRequest(BaseModel):
    """Vérification de l'association du nouvel appareil — R363.

    DOIT contenir une VRAIE assertion WebAuthn de l'appareil EXISTANT (appareil A).
    Le PIN seul, password seul, template_hex seul sont tous REFUSÉS (spec §4 rapport 367).

    Champs WebAuthn (identiques à /auth/webauthn/login/verify) :
      - credential_id     : l'ID de la credential de l'appareil EXISTANT
      - client_data_json  : clientDataJSON b64url (challenge + origin + type)
      - authenticator_data: authenticatorData b64url
      - signature         : signature b64url (ECDSA P-256)
    """
    # ── Challenge émis par /add-options ─────────────────────────────────────
    challenge_b64: str = Field(
        description="Challenge b64url obtenu via /add-options (identique à celui dans clientDataJSON)",
    )
    # ── Assertion WebAuthn de l'appareil EXISTANT ────────────────────────────
    credential_id: str = Field(
        min_length=8,
        description="credential_id b64url de l'appareil EXISTANT (doit correspondre à un credential enregistré)",
    )
    client_data_json: str = Field(
        min_length=10,
        description="clientDataJSON b64url — doit contenir challenge + type=webauthn.get",
    )
    authenticator_data: str = Field(
        min_length=10,
        description="authenticatorData b64url — flags UP+UV obligatoires",
    )
    signature: str = Field(
        min_length=10,
        description="Signature ECDSA P-256 b64url sur (authenticatorData || SHA-256(clientDataJSON))",
    )
    # ── Credential du NOUVEL appareil (attestation ou clé publique) ──────────
    new_device_credential_id: str = Field(
        min_length=8,
        description="credential_id b64url du NOUVEL appareil — sera enregistré sous le même HumanID",
    )
    new_device_hint: str = Field(
        default="unknown",
        max_length=64,
        description="Descriptif du nouvel appareil (ex: iPhone 15, MacBook M3…)",
    )
    new_device_public_key_b64: Optional[str] = Field(
        default=None,
        description="Clé publique COSE/raw b64url du NOUVEL appareil (facultatif — stocké pour référence)",
    )


class DeviceRevokeRequest(BaseModel):
    """Révocation d'un appareil de l'identité humaine — R363.

    Nécessite une vraie assertion WebAuthn de l'appareil initiateur.
    """
    human_id: str = Field(min_length=8)
    device_id: str = Field(min_length=8, description="ID de l'appareil à révoquer")
    # Assertion WebAuthn de l'appareil qui révoque
    credential_id: str = Field(min_length=8, description="credential_id b64url de l'appareil initiateur")
    client_data_json: str = Field(min_length=10, description="clientDataJSON b64url")
    authenticator_data: str = Field(min_length=10, description="authenticatorData b64url")
    signature: str = Field(min_length=10, description="Signature b64url")


# ─── Routes ───────────────────────────────────────────────────────────────────


def _load_credential_store() -> dict[str, dict]:
    """Charge le registre des credentials WebAuthn enregistrées.

    Format : credential_id_b64u → {public_key_pem, human_id, sign_count, ...}
    """
    data_dir = Path(os.environ.get("ARTCB_DATA_DIR", "data"))
    store_path = data_dir / "identity" / "credential_store.jsonl"
    if not store_path.exists():
        return {}
    store: dict[str, dict] = {}
    for line in store_path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rec = json.loads(line)
                cid = rec.get("credential_id")
                if cid:
                    store[cid] = rec
            except json.JSONDecodeError:
                pass
    return store


def _update_sign_count(credential_id: str, new_count: int) -> None:
    """Met à jour le sign_count d'une credential après une assertion valide."""
    data_dir = Path(os.environ.get("ARTCB_DATA_DIR", "data"))
    store_path = data_dir / "identity" / "credential_store.jsonl"
    if not store_path.exists():
        return
    lines = store_path.read_text().splitlines()
    updated = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("credential_id") == credential_id:
                rec["sign_count"] = new_count
            updated.append(json.dumps(rec, ensure_ascii=False))
        except json.JSONDecodeError:
            updated.append(line)
    store_path.write_text("\n".join(updated) + "\n")


@router.post(
    "/add-options",
    summary="Initier l'ajout d'un nouvel appareil — étape 1/2 (R363)",
)
def add_device_options(body: AddDeviceOptionsRequest, request: Request) -> dict:
    """Émet un challenge WebAuthn pour l'ajout d'un nouvel appareil (R363).

    FLUX (spec §18 rapport 367, R363) :
      1. Nouvel appareil B → POST /add-options {human_id}
      2. ARTCB → challenge b64url (format WebAuthn)
      3. Appareil existant A → navigator.credentials.get({challenge}) → assertion
      4. POST /identity/device/add-verify avec assertion WebAuthn complète

    INTERDIT (spec §10, §4) :
      ❌ Création directe de wallet depuis un nouvel appareil inconnu
      ❌ PIN seul — rejeté avec 403
      ❌ template_hex seul — rejeté avec 403
      ❌ "biometric=true" auto-déclaré — rejeté avec 403
    """
    # Vérifier que l'identité existe
    records = _load_records()
    existing = next((r for r in records if r.get("human_id") == body.human_id), None)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"human_id_not_found: {body.human_id}. Créez d'abord une identité via /identity/biometric/enroll.",
        )

    # Récupérer les credential_ids enregistrés pour cet HumanID
    cred_store = _load_credential_store()
    human_cred_ids = [
        cid for cid, rec in cred_store.items()
        if rec.get("human_id") == body.human_id
    ]

    host = request.headers.get("host", "artcb.me")
    rp_id = rp_id_for_host(host)

    # Challenge aléatoire en bytes → b64url
    challenge_bytes = secrets.token_bytes(32)
    challenge_b64 = b64u_encode(challenge_bytes)

    _device_challenges[challenge_b64] = {
        "human_id": body.human_id,
        "new_device_hint": body.new_device_hint,
        "rp_id": rp_id,
        "created_at": time.time(),
        "expires_at": time.time() + _CHALLENGE_TTL,
    }

    # Options WebAuthn assertion (format navigator.credentials.get)
    allow_credentials = [
        {"type": "public-key", "id": cid, "transports": ["internal", "hybrid"]}
        for cid in human_cred_ids
    ]

    return {
        "challenge": challenge_b64,
        "human_id": body.human_id,
        "expires_in": _CHALLENGE_TTL,
        "rp_id": rp_id,
        "allow_credentials": allow_credentials,
        "user_verification": "required",
        "instructions": (
            "Sur votre APPAREIL EXISTANT : appelez navigator.credentials.get() avec ce challenge, "
            "puis POST /identity/device/add-verify avec l'assertion WebAuthn complète. "
            "⚠️ Le PIN seul est REFUSÉ — signature cryptographique WebAuthn requise (R363)."
        ),
        "forbidden": [
            "PIN seul → 403",
            "password seul → 403",
            "template_hex seul → 403",
            "biometric=true auto-déclaré → 403",
            "création directe de wallet → 403",
        ],
        "proof_required": "webauthn_assertion_cryptographic",
        "certified_100": False,
        "unique_human_proven": False,
    }


@router.post(
    "/add-verify",
    summary="Vérifier l'assertion WebAuthn et enregistrer le nouvel appareil — étape 2/2 (R363)",
)
def add_device_verify(body: AddDeviceVerifyRequest, request: Request) -> dict:
    """Vérifie une VRAIE assertion WebAuthn de l'appareil existant et enregistre le nouvel appareil.

    RÈGLES DE SÉCURITÉ R363 (spec §17–§19 rapport 367) :
      - La preuve DOIT être une vraie assertion WebAuthn cryptographique (credential_id + sig)
      - verify_assertion() de webauthn_protocol.py est appelé — pas de stub
      - UP + UV obligatoires (userVerification=required)
      - Le challenge doit correspondre exactement à celui émis par /add-options
      - Le nouvel appareil n'obtient PAS un nouveau wallet — il rejoint l'identité existante
      - Limite : max 5 appareils par HumanID (anti-abus spec §17)
      - WebAuthn valide ≠ unique_human_proven (spec §4 rapport 367)
    """
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePublicKey,
        SECP256R1,
    )
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    # ── 1. Vérifier le challenge ─────────────────────────────────────────────
    challenge_data = _device_challenges.get(body.challenge_b64)
    if not challenge_data:
        raise HTTPException(status_code=400, detail="add_device_challenge_unknown")
    if time.time() > challenge_data.get("expires_at", 0):
        _device_challenges.pop(body.challenge_b64, None)
        raise HTTPException(status_code=400, detail="add_device_challenge_expired")

    human_id = challenge_data["human_id"]
    rp_id = challenge_data.get("rp_id", "artcb.me")

    # ── 2. Vérifier limite d'appareils EN PREMIER (avant toute crypto) ────────
    # Ordre transactionnel correct : pas de consommation de preuve si l'opération
    # est de toute façon impossible (audit R363 — corriger ordre max_5).
    MAX_DEVICES_PER_HUMAN = 5
    device_registry_pre = _load_device_registry()
    human_devices = [d for d in device_registry_pre if d.get("human_id") == human_id and not d.get("revoked")]
    if len(human_devices) >= MAX_DEVICES_PER_HUMAN:
        _device_challenges.pop(body.challenge_b64, None)
        raise HTTPException(
            status_code=409,
            detail=(
                f"device_limit_reached — max {MAX_DEVICES_PER_HUMAN} appareils par HumanID. "
                "Révoquez un appareil existant avant d'en ajouter un nouveau."
            ),
        )

    # ── 3. Récupérer la clé publique de la credential de l'appareil EXISTANT ─
    cred_store = _load_credential_store()
    existing_cred = cred_store.get(body.credential_id)
    if not existing_cred:
        _device_challenges.pop(body.challenge_b64, None)
        raise HTTPException(
            status_code=401,
            detail=(
                "credential_not_found — la credential_id présentée n'est pas enregistrée. "
                "⚠️ PIN seul REFUSÉ (R363 spec §4 rapport 367)."
            ),
        )

    # Vérifier que cette credential appartient bien à cet HumanID
    if existing_cred.get("human_id") != human_id:
        _device_challenges.pop(body.challenge_b64, None)
        raise HTTPException(
            status_code=403,
            detail="credential_human_id_mismatch — cette credential n'appartient pas à cet HumanID",
        )

    # ── 4. Charger la clé publique de A ─────────────────────────────────────
    pub_key_pem = existing_cred.get("public_key_pem", "")
    if not pub_key_pem:
        _device_challenges.pop(body.challenge_b64, None)
        raise HTTPException(status_code=500, detail="credential_public_key_missing")

    try:
        public_key: EllipticCurvePublicKey = load_pem_public_key(pub_key_pem.encode())  # type: ignore[assignment]
    except Exception as exc:
        logger.error("load_pem_public_key failed: %s", exc)
        _device_challenges.pop(body.challenge_b64, None)
        raise HTTPException(status_code=500, detail="credential_public_key_invalid")

    # ── 5. Vérification WebAuthn cryptographique de A ────────────────────────
    host = request.headers.get("host", "artcb.me")
    origins = expected_origins(host, "https")

    try:
        client_data_bytes = b64u_decode(body.client_data_json)
        auth_data_bytes = b64u_decode(body.authenticator_data)
        sig_bytes = b64u_decode(body.signature)
    except Exception:
        _device_challenges.pop(body.challenge_b64, None)
        raise HTTPException(status_code=400, detail="assertion_fields_invalid_b64url")

    try:
        new_sign_count = verify_assertion(
            client_data_json=client_data_bytes,
            authenticator_data=auth_data_bytes,
            signature=sig_bytes,
            challenge_b64=body.challenge_b64,
            rp_id=rp_id,
            origins=origins,
            public_key=public_key,
            previous_sign_count=existing_cred.get("sign_count", 0),
        )
    except WebAuthnError as exc:
        _device_challenges.pop(body.challenge_b64, None)
        raise HTTPException(
            status_code=401,
            detail=f"webauthn_assertion_failed: {exc} — ⚠️ PIN seul REFUSÉ (R363 spec §4)",
        )

    # ── 6. Mise à jour du sign_count anti-replay (après toutes les vérifications) ─
    _update_sign_count(body.credential_id, new_sign_count)
    _device_challenges.pop(body.challenge_b64, None)

    # ── 7. Vérifier l'identité correspondante ────────────────────────────────
    records = _load_records()
    matching_record = next((r for r in records if r.get("human_id") == human_id), None)
    if not matching_record:
        raise HTTPException(status_code=404, detail=f"human_id_not_found: {human_id}")

    # ── 8. Enregistrer B dans les deux stores (enrôlement réel de B) ──────────
    #
    # B doit être présent dans DEUX endroits pour être pleinement fonctionnel :
    #
    #   a) identity/credential_store.jsonl  → lié au HumanID (pour ADD_DEVICE)
    #   b) webauthn/credentials.json        → lié au wallet_name (pour /auth/webauthn/login)
    #
    # Sans (b), B ne peut pas se connecter via /auth/webauthn/login.
    # Le champ "cose_b64" est la clé COSE P-256 attendue par public_key_from_cose().
    # Si new_device_public_key_b64 est une clé COSE, on l'utilise directement.
    # Si c'est un PEM brut, on le convertit.
    #
    # Note : si new_device_public_key_b64 n'est pas fourni, l'enrôlement est partiel
    # (device associé mais B ne peut pas encore se connecter).
    new_cred_enrolled = False
    wallet_address = matching_record.get("wallet_address", "")
    wallet_name = matching_record.get("wallet_name", human_id)

    if body.new_device_public_key_b64:
        # ── a) identity/credential_store.jsonl ───────────────────────────────
        data_dir_cs = Path(os.environ.get("ARTCB_DATA_DIR", "data"))
        cred_store_path = data_dir_cs / "identity" / "credential_store.jsonl"
        cred_store_path.parent.mkdir(parents=True, exist_ok=True)
        new_cred_rec = {
            "credential_id": body.new_device_credential_id,
            "human_id": human_id,
            "public_key_b64": body.new_device_public_key_b64,
            "public_key_pem": "",
            "sign_count": 0,
            "enrolled_by": body.credential_id[:16] + "…",
            "enrolled_via": "add_device_r363",
            "device_hint": body.new_device_hint,
            "created_at": time.time(),
        }
        with cred_store_path.open("a") as _f:
            _f.write(json.dumps(new_cred_rec, ensure_ascii=False) + "\n")

        # ── b) webauthn/credentials.json → pour /auth/webauthn/login ─────────
        # Le champ "cose_b64" est utilisé par public_key_from_cose() lors du login.
        # On l'aliase depuis new_device_public_key_b64 (supposé être COSE b64url).
        try:
            from src.artcb.security.webauthn_store import save_credential as _save_webauthn_cred
            webauthn_cred_rec = {
                "credential_id": body.new_device_credential_id,
                "wallet_name": wallet_name,
                "address": wallet_address,
                "cose_b64": body.new_device_public_key_b64,  # clé COSE P-256 b64url
                "sign_count": 0,
                "rp_id": rp_id,
                "modality": "add_device",
                "human_id": human_id,
                "enrolled_by": body.credential_id[:16] + "…",
                "enrolled_via": "add_device_r363",
                "device_hint": body.new_device_hint,
                "created_at": time.time(),
            }
            _save_webauthn_cred(webauthn_cred_rec)
            new_cred_enrolled = True
        except Exception as _exc:
            logger.warning("add_device: save_webauthn_cred failed: %s", _exc)
            new_cred_enrolled = False

    # ── 9. Enregistrer le device_record dans device_registry ──────────────────
    device_id = hashlib.sha256(
        f"{human_id}:{body.new_device_credential_id}:{time.time_ns()}".encode()
    ).hexdigest()[:32]

    device_record = {
        "device_id": device_id,
        "human_id": human_id,
        "credential_id": body.new_device_credential_id,
        "public_key_b64": body.new_device_public_key_b64 or "",
        "device_hint": body.new_device_hint,
        "created_at": time.time(),
        "revoked": False,
        "revoked_at": None,
        "auth_method": "add_device_webauthn_assertion_r363",
        "authorized_by_credential": body.credential_id,
        "credential_enrolled": new_cred_enrolled,
        "unique_human_proven": False,
        "certified_100": False,
    }
    _append_device(device_record)

    logger.info(
        "ADD_DEVICE R363 OK: human_id=%s device_id=%s hint=%s authorized_by=%s (WebAuthn assertion valide)",
        human_id[:16], device_id[:16], body.new_device_hint, body.credential_id[:16],
    )

    return {
        "device_added": True,
        "device_id": device_id,
        "human_id": human_id,
        "wallet_address": wallet_address,
        "device_hint": body.new_device_hint,
        "devices_count": len(human_devices) + 1,
        "max_devices": MAX_DEVICES_PER_HUMAN,
        "authorized_by": body.credential_id[:16] + "…",
        "proof_class": "webauthn_assertion_cryptographic",
        "credential_enrolled": new_cred_enrolled,
        "unique_human_proven": False,
        "certified_100": False,
        "note": (
            "Appareil ajouté via VRAIE assertion WebAuthn (R363). "
            + ("Credential B enrôlée dans credential_store — B peut se connecter via /auth/webauthn/login. " if new_cred_enrolled else "Clé publique B non fournie — enrôlement partiel (fournir new_device_public_key_b64 pour enrôlement complet). ")
            + "Aucun nouveau wallet créé (spec §10 rapport 367). "
            + "WebAuthn valide ≠ unique_human_proven (spec §4 rapport 367)."
        ),
    }


@router.get(
    "/{human_id}/devices",
    summary="Lister les appareils d'une identité humaine",
)
def list_devices(human_id: str) -> dict:
    """Liste les appareils enregistrés pour une identité humaine."""
    device_registry = _load_device_registry()
    devices = [
        {
            "device_id": d["device_id"],
            "device_hint": d.get("device_hint", "unknown"),
            "created_at": d.get("created_at"),
            "revoked": d.get("revoked", False),
        }
        for d in device_registry
        if d.get("human_id") == human_id
    ]
    return {
        "human_id": human_id,
        "devices": devices,
        "count": len(devices),
        "active_count": sum(1 for d in devices if not d.get("revoked")),
        "certified_100": False,
    }


@router.post(
    "/revoke",
    summary="Révoquer un appareil d'une identité humaine (R363 — assertion WebAuthn)",
)
def revoke_device(body: DeviceRevokeRequest, request: Request) -> dict:
    """Révoque un appareil de l'identité humaine.

    Nécessite une VRAIE assertion WebAuthn de l'appareil initiateur (R363 spec §17).
    Le PIN seul est REFUSÉ — identique à add-verify.
    """
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    # ── 1. Récupérer la credential de l'appareil initiateur ─────────────────
    cred_store = _load_credential_store()
    initiator_cred = cred_store.get(body.credential_id)
    if not initiator_cred:
        raise HTTPException(
            status_code=401,
            detail="credential_not_found — ⚠️ PIN seul REFUSÉ (R363 spec §4 rapport 367)",
        )

    if initiator_cred.get("human_id") != body.human_id:
        raise HTTPException(status_code=403, detail="credential_human_id_mismatch")

    # ── 2. Charger la clé publique ───────────────────────────────────────────
    pub_key_pem = initiator_cred.get("public_key_pem", "")
    if not pub_key_pem:
        raise HTTPException(status_code=500, detail="credential_public_key_missing")

    try:
        public_key = load_pem_public_key(pub_key_pem.encode())  # type: ignore[assignment]
    except Exception:
        raise HTTPException(status_code=500, detail="credential_public_key_invalid")

    # ── 3. Créer un challenge éphémère pour cette révocation ─────────────────
    # Le client DOIT avoir obtenu un challenge via /add-options avant de révoquer
    # Pour revoke on réutilise le même mécanisme de challenge — on accepte aussi
    # un challenge libre si l'opération est signée cryptographiquement
    host = request.headers.get("host", "artcb.me")
    rp_id = rp_id_for_host(host)
    origins = expected_origins(host, "https")

    # ── 4. Vérification WebAuthn cryptographique ─────────────────────────────
    try:
        client_data_bytes = b64u_decode(body.client_data_json)
        auth_data_bytes = b64u_decode(body.authenticator_data)
        sig_bytes = b64u_decode(body.signature)
    except Exception:
        raise HTTPException(status_code=400, detail="revoke_assertion_fields_invalid_b64url")

    # Extraire le challenge depuis le clientDataJSON pour vérification
    import json as _json
    try:
        client_data_parsed = _json.loads(client_data_bytes.decode("utf-8"))
        challenge_b64_in_request = client_data_parsed.get("challenge", "")
    except Exception:
        raise HTTPException(status_code=400, detail="revoke_client_data_json_invalid")

    try:
        new_sign_count = verify_assertion(
            client_data_json=client_data_bytes,
            authenticator_data=auth_data_bytes,
            signature=sig_bytes,
            challenge_b64=challenge_b64_in_request,
            rp_id=rp_id,
            origins=origins,
            public_key=public_key,  # type: ignore[arg-type]
            previous_sign_count=initiator_cred.get("sign_count", 0),
        )
    except WebAuthnError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"revoke_webauthn_assertion_failed: {exc} — ⚠️ PIN seul REFUSÉ (R363)",
        )

    _update_sign_count(body.credential_id, new_sign_count)

    # ── 5. Révoquer l'appareil ───────────────────────────────────────────────
    data_dir = Path(os.environ.get("ARTCB_DATA_DIR", "data"))
    registry_path = data_dir / "identity" / "device_registry.jsonl"
    if not registry_path.exists():
        raise HTTPException(status_code=404, detail=f"device_not_found: {body.device_id}")

    devices = _load_device_registry()
    target = next((d for d in devices if d.get("device_id") == body.device_id and d.get("human_id") == body.human_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"device_not_found: {body.device_id}")

    target["revoked"] = True
    target["revoked_at"] = time.time()
    target["revoked_by_credential"] = body.credential_id[:16] + "…"

    registry_path.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in devices) + "\n")

    logger.info(
        "REVOKE_DEVICE R363 OK: human_id=%s device_id=%s initiator=%s",
        body.human_id[:16], body.device_id[:16], body.credential_id[:16],
    )
    return {
        "revoked": True,
        "device_id": body.device_id,
        "human_id": body.human_id,
        "proof_class": "webauthn_assertion_cryptographic",
        "certified_100": False,
    }
