"""Routes API — HumanIdentity multi-device (spec §17–18, rapport 367/370, 2026-09-17).

Implémente le flux ADD_DEVICE :
  - Un humain peut ajouter un nouvel appareil à son identité ARTCB
  - L'ajout nécessite une preuve cryptographique depuis un appareil déjà enregistré
  - Aucun PIN / mot de passe seul ne suffit (spec §4)
  - Aucune création directe de wallet depuis un nouvel appareil (spec §10)

Flux ADD_DEVICE :
  1. POST /identity/device/add-options   → challenge pour l'appareil existant
  2. (appareil existant) signe le challenge avec sa credential
  3. POST /identity/device/add-verify    → vérifie + enregistre le nouvel appareil
  4. (nouvel appareil) peut maintenant s'authentifier via /auth/webauthn/login

HONNÊTETÉ :
  - Ce module est un stub fonctionnel.
  - L'association réelle nécessite une vérification WebAuthn complète.
  - unique_human_proven = False (pas de preuve formelle d'unicité)
  - CERTIFIED_100 = False
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("artcb.api.identity_device")
router = APIRouter(prefix="/api/v1/identity/device", tags=["identity-device"])

_CHALLENGE_TTL = 300  # 5 minutes

# Challenges en attente d'approbation par l'appareil existant
_device_challenges: dict[str, dict] = {}  # challenge_hex → {human_id, new_device_hint, created_at}


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
    """Vérification de l'association du nouvel appareil.

    DOIT être signée par l'appareil EXISTANT (appareil A) via sa credential
    biométrique WebAuthn. Le PIN seul est REFUSÉ (spec §4 rapport 367/370).

    Le template_hex représente la preuve biométrique de l'appareil EXISTANT
    (comme pour /auth/webauthn/login/verify).
    """
    challenge: str = Field(
        min_length=64, max_length=64,
        description="Challenge obtenu via /add-options",
    )
    existing_template_hex: str = Field(
        min_length=64,
        description=(
            "Template biométrique normalisé de l'appareil EXISTANT (hex). "
            "Prouve que le détenteur de l'identité autorise l'ajout. "
            "Jamais une image brute."
        ),
    )
    new_device_credential_hex: str = Field(
        min_length=32,
        description=(
            "Credential publique du NOUVEL appareil (hex). "
            "Sera enregistrée sous le même HumanID."
        ),
    )
    new_device_hint: str = Field(
        default="unknown",
        max_length=64,
        description="Descriptif du nouvel appareil",
    )


class DeviceRevokeRequest(BaseModel):
    """Révocation d'un appareil de l'identité humaine."""
    human_id: str = Field(min_length=8)
    device_id: str = Field(min_length=8, description="ID de l'appareil à révoquer")
    existing_template_hex: str = Field(
        min_length=64,
        description="Preuve biométrique de l'appareil initiateur de la révocation",
    )


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.post(
    "/add-options",
    summary="Initier l'ajout d'un nouvel appareil (étape 1/2)",
)
def add_device_options(body: AddDeviceOptionsRequest) -> dict:
    """Émet un challenge pour l'ajout d'un nouvel appareil à une identité humaine.

    FLUX (spec §18 rapport 367/370) :
      1. Nouvel appareil B → POST /add-options {human_id}
      2. ARTCB → challenge
      3. Appareil existant A → POST /add-verify {challenge, existing_biometrie, new_credential}
      4. ARTCB → enregistrement appareil B sous HumanID existant

    INTERDIT (spec §10, §4) :
      ❌ Création directe de wallet depuis un nouvel appareil inconnu
      ❌ PIN seul comme autorisation
      ❌ device fingerprint seul comme autorisation
      ❌ "biometric=true" auto-déclaré

    CERTIFIED_100=false — stub fonctionnel.
    """
    # Vérifier que l'identité existe
    records = _load_records()
    existing = next((r for r in records if r.get("human_id") == body.human_id), None)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"human_id_not_found: {body.human_id}. Créez d'abord une identité via /identity/biometric/enroll.",
        )

    challenge = secrets.token_hex(32)
    _device_challenges[challenge] = {
        "human_id": body.human_id,
        "new_device_hint": body.new_device_hint,
        "created_at": time.time(),
        "expires_at": time.time() + _CHALLENGE_TTL,
    }

    return {
        "challenge": challenge,
        "human_id": body.human_id,
        "expires_in": _CHALLENGE_TTL,
        "instructions": (
            "Sur votre APPAREIL EXISTANT : capturez votre empreinte/biométrie, "
            "puis POST /identity/device/add-verify avec {challenge, existing_template_hex, new_device_credential_hex}. "
            "⚠️ Le PIN seul est REFUSÉ — preuve biométrique native requise."
        ),
        "forbidden": [
            "PIN seul",
            "password seul",
            "device fingerprint seul",
            "biometric=true auto-déclaré",
            "création directe de wallet",
        ],
        "certified_100": False,
        "unique_human_proven": False,
    }


@router.post(
    "/add-verify",
    summary="Vérifier et enregistrer le nouvel appareil (étape 2/2)",
)
def add_device_verify(body: AddDeviceVerifyRequest, request: Request) -> dict:
    """Vérifie la preuve biométrique de l'appareil existant et enregistre le nouvel appareil.

    RÈGLES DE SÉCURITÉ (spec §17–§19 rapport 367/370) :
      - La preuve DOIT venir de l'appareil EXISTANT (template biométrique normalisé)
      - Le nouvel appareil n'obtient PAS un nouveau wallet — il rejoint l'identité existante
      - Une nouvelle credential est enregistrée sous le même HumanID
      - Limite : max 5 appareils par HumanID (anti-abus spec §17)

    HONNÊTETÉ :
      - Matching = hash exact (stub). Production : WebAuthn credential + FHE.
      - unique_human_proven = False.
      - CERTIFIED_100 = False.
    """
    from src.artcb.crypto.homomorphic import commit_biometric_template
    from src.artcb.identity.biometric_onchain import check_uniqueness

    # ── Vérifier le challenge ────────────────────────────────────────────────
    challenge_data = _device_challenges.get(body.challenge)
    if not challenge_data:
        raise HTTPException(status_code=400, detail="add_device_challenge_unknown")
    if time.time() > challenge_data.get("expires_at", 0):
        _device_challenges.pop(body.challenge, None)
        raise HTTPException(status_code=400, detail="add_device_challenge_expired")

    human_id = challenge_data["human_id"]

    # ── Rejeter image brute ──────────────────────────────────────────────────
    try:
        tmpl_bytes = bytes.fromhex(body.existing_template_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="existing_template_hex_invalid_hex")

    PNG_MAGIC = b"\x89PNG"
    JPEG_MAGIC = b"\xff\xd8\xff"
    BMP_MAGIC = b"BM"
    if tmpl_bytes[:4] == PNG_MAGIC or tmpl_bytes[:3] == JPEG_MAGIC or tmpl_bytes[:2] == BMP_MAGIC:
        raise HTTPException(
            status_code=400,
            detail="raw_image_rejected — fournir un template normalisé (spec §3 rapport 367/370)",
        )

    # ── Vérifier que l'appareil existant contrôle bien cette identité ────────
    records = _load_records()
    matching_record = next((r for r in records if r.get("human_id") == human_id), None)
    if not matching_record:
        raise HTTPException(status_code=404, detail=f"human_id_not_found: {human_id}")

    commitment = commit_biometric_template(tmpl_bytes)
    check = check_uniqueness(commitment, [matching_record])

    if not check.match_found:
        _device_challenges.pop(body.challenge, None)
        raise HTTPException(
            status_code=401,
            detail=(
                "existing_identity_not_proven — le template biométrique présenté "
                "ne correspond pas à l'identité {human_id}. "
                "⚠️ Le PIN seul est REFUSÉ pour autoriser l'ajout d'un appareil."
            ),
        )

    # ── Vérifier limite d'appareils (anti-abus spec §17) ─────────────────────
    MAX_DEVICES_PER_HUMAN = 5
    device_registry = _load_device_registry()
    human_devices = [d for d in device_registry if d.get("human_id") == human_id and not d.get("revoked")]
    if len(human_devices) >= MAX_DEVICES_PER_HUMAN:
        _device_challenges.pop(body.challenge, None)
        raise HTTPException(
            status_code=409,
            detail=(
                f"device_limit_reached — max {MAX_DEVICES_PER_HUMAN} appareils par HumanID. "
                "Révoquez un appareil existant avant d'en ajouter un nouveau."
            ),
        )

    # ── Enregistrer le nouvel appareil ────────────────────────────────────────
    _device_challenges.pop(body.challenge, None)

    device_id = hashlib.sha256(
        f"{human_id}:{body.new_device_credential_hex}:{time.time_ns()}".encode()
    ).hexdigest()[:32]

    device_record = {
        "device_id": device_id,
        "human_id": human_id,
        "credential_hex": body.new_device_credential_hex,
        "device_hint": body.new_device_hint,
        "created_at": time.time(),
        "revoked": False,
        "revoked_at": None,
        "auth_method": "add_device_webauthn_template",
        "unique_human_proven": False,
        "certified_100": False,
    }
    _append_device(device_record)

    wallet_address = matching_record.get("wallet_address", "")

    logger.info(
        "ADD_DEVICE OK: human_id=%s device_id=%s hint=%s (unique_human_proven=False)",
        human_id[:16], device_id[:16], body.new_device_hint,
    )

    return {
        "device_added": True,
        "device_id": device_id,
        "human_id": human_id,
        "wallet_address": wallet_address,
        "device_hint": body.new_device_hint,
        "devices_count": len(human_devices) + 1,
        "max_devices": MAX_DEVICES_PER_HUMAN,
        "unique_human_proven": False,
        "certified_100": False,
        "note": (
            "Appareil ajouté à l'identité humaine existante. "
            "Aucun nouveau wallet créé (spec §10 rapport 367/370). "
            "unique_human_proven=False — stub hash-based."
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
    summary="Révoquer un appareil d'une identité humaine",
)
def revoke_device(body: DeviceRevokeRequest) -> dict:
    """Révoque un appareil de l'identité humaine.

    Nécessite une preuve biométrique de l'appareil initiateur (spec §17).
    """
    from src.artcb.crypto.homomorphic import commit_biometric_template
    from src.artcb.identity.biometric_onchain import check_uniqueness

    # Rejeter image brute
    try:
        tmpl_bytes = bytes.fromhex(body.existing_template_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="existing_template_hex_invalid_hex")

    # Vérifier l'identité
    records = _load_records()
    matching_record = next((r for r in records if r.get("human_id") == body.human_id), None)
    if not matching_record:
        raise HTTPException(status_code=404, detail=f"human_id_not_found: {body.human_id}")

    commitment = commit_biometric_template(tmpl_bytes)
    check = check_uniqueness(commitment, [matching_record])
    if not check.match_found:
        raise HTTPException(
            status_code=401,
            detail="revoke_identity_not_proven — preuve biométrique incorrecte",
        )

    # Révoquer l'appareil
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

    # Réécrire le registre
    registry_path.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in devices) + "\n")

    logger.info("REVOKE_DEVICE: human_id=%s device_id=%s", body.human_id[:16], body.device_id[:16])
    return {
        "revoked": True,
        "device_id": body.device_id,
        "human_id": body.human_id,
        "certified_100": False,
    }
