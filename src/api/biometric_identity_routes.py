"""Routes API — Identité biométrique ARTCB (P0-C 2026-09-16).

Endpoints :
    POST /api/v1/identity/biometric/enroll
        → Inscription biométrique : template normalisé → HumanIdentityRecord on-chain.
        → Retourne : human_id + record public (commitment, helper_data).
        → JAMAIS : blinding_hex, secret_hex, template_raw.

    POST /api/v1/identity/biometric/uniqueness-check
        → Vérification d'unicité avant inscription.
        → Retourne : match_found=True/False.

    GET /api/v1/identity/biometric/{human_id}
        → Consulter un HumanIdentityRecord public (sans données sensibles).

HONNÊTETÉ (CERTIFIED_100=false) :
    - unique_human_proven = False jusqu'à certification réelle.
    - Le matching est basé sur hash (stub) — pas FHE certifié.
    - L'image brute est rejetée (HTTP 400) à chaque endpoint.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.config import load_settings
from src.artcb.crypto.homomorphic import commit_biometric_template
from src.artcb.identity.biometric_onchain import (
    BiometricEnrollmentResult,
    UniquenessCheckResult,
    check_uniqueness,
    enroll_biometric,
    fuzzy_reproduce,
)

logger = logging.getLogger("artcb.api.identity.biometric")
router = APIRouter(prefix="/api/v1/identity/biometric", tags=["identity-biometric"])

# Stockage on-chain local (JSON-Lines) — en production → append_block
_RECORDS_FILENAME = "biometric_identities.jsonl"


def _records_path() -> Path:
    settings = load_settings()
    p = settings.data_dir / "identity"
    p.mkdir(parents=True, exist_ok=True)
    return p / _RECORDS_FILENAME


def _load_records() -> list[dict[str, Any]]:
    path = _records_path()
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def _append_record(record: dict[str, Any]) -> None:
    path = _records_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _reject_raw_biometric(body_dict: dict[str, Any]) -> None:
    """Rejette tout champ contenant une image biométrique brute."""
    forbidden = {"image", "photo", "frame", "template_raw", "biometric_raw", "fingerprint_image"}
    for key in forbidden:
        if key in body_dict and body_dict[key]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"raw_biometric_rejected — '{key}' refusé. "
                    "Le modèle normalisé seul est accepté, jamais l'image brute."
                ),
            )


# --------------------------------------------------------------------------- #
#  Schémas
# --------------------------------------------------------------------------- #

class EnrollRequest(BaseModel):
    """Corps d'inscription biométrique.

    template_hex : modèle biométrique normalisé en hex (jamais l'image brute).
                   Minimum 32 bytes (64 hex chars) — typiquement 512-2048 bytes.
    wallet_address : adresse du wallet lié (optionnel — spec §7 : créé après l'identité).
    """
    template_hex: str = Field(
        min_length=64,
        description="Modèle biométrique normalisé (hex). Jamais l'image brute.",
    )
    wallet_address: str | None = Field(
        default=None,
        description="Adresse du wallet à lier (optionnel — créé après l'identité).",
    )
    # Champs interdits — rejetés si présents
    image: str | None = None
    photo: str | None = None
    frame: str | None = None
    template_raw: str | None = None


class UniquenessCheckRequest(BaseModel):
    """Corps de vérification d'unicité."""
    template_hex: str = Field(
        min_length=64,
        description="Modèle biométrique normalisé (hex) à vérifier.",
    )
    image: str | None = None
    photo: str | None = None
    frame: str | None = None


# --------------------------------------------------------------------------- #
#  Endpoints
# --------------------------------------------------------------------------- #

@router.post("/enroll", summary="Inscription biométrique → HumanIdentityRecord on-chain")
def enroll(body: EnrollRequest, request: Request) -> dict[str, Any]:
    """
    Inscription biométrique ARTCB (spec §2, §3, §4 — P0-C 2026-09-16).

    Flow :
      1. Client normalise le template côté appareil.
      2. Client envoie template_hex (jamais l'image brute).
      3. Serveur : FuzzyExtractor → engagement → HumanIdentityRecord.
      4. Test d'unicité → refus si déjà enregistré (spec §5).
      5. Inscription on-chain (helper_data + commitment — jamais le secret).
      6. Retour : human_id + record public.

    Champs retournés PRIVÉS (rester côté client, jamais rejouer côté serveur) :
      - secret_hex  : secret FuzzyExtractor (à garder localement pour recovery).
      - blinding_hex: facteur aveuglant (à garder localement).

    unique_human_proven = False (stub — FAR/FRR non certifiés).
    """
    # Rejet image brute
    _reject_raw_biometric(body.model_dump())

    try:
        template_bytes = bytes.fromhex(body.template_hex)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"template_hex invalide : {exc}") from exc

    if len(template_bytes) < 32:
        raise HTTPException(
            status_code=400,
            detail="template_hex trop court (min 32 bytes / 64 hex chars).",
        )

    # Récupérer le node_id depuis l'app state
    node_id: str | None = None
    try:
        node_id = getattr(request.app.state, "node_id", None)
    except Exception:
        pass

    # Test d'unicité avant inscription (spec §5)
    existing_records = _load_records()
    commitment_check = commit_biometric_template(template_bytes)
    uniqueness = check_uniqueness(commitment_check, existing_records)
    if uniqueness.match_found:
        logger.warning(
            "P0-C enroll: unicité refusée — human_id=%s déjà enregistré",
            uniqueness.existing_human_id,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "human_identity_already_registered",
                "message": "Human identity already registered — spec §5.",
                "existing_human_id": uniqueness.existing_human_id,
                "unique_human_proven": False,
                "hint": "Un humain = une HumanIdentity. Changement d'appareil → recovery phrase.",
            },
        )

    # Inscription
    result, secret_hex, blinding_hex = enroll_biometric(
        template_bytes,
        wallet_address=body.wallet_address,
        node_id=node_id,
    )

    # Persistance on-chain locale
    _append_record(result.human_identity_record)
    logger.info(
        "P0-C enroll_ok: human_id=%s wallet=%s unique_human_proven=False",
        result.human_id,
        body.wallet_address,
    )

    return {
        "ok": True,
        "human_id": result.human_id,
        "status": result.status,
        "human_identity_record": result.human_identity_record,
        "commitment_public": result.commitment_public,
        # Champs privés — l'utilisateur doit les conserver localement
        "private_for_client": {
            "secret_hex": secret_hex,
            "blinding_hex": blinding_hex,
            "WARNING": (
                "Conservez secret_hex et blinding_hex côté client uniquement. "
                "Ils ne seront plus renvoyés. Ils permettent la recovery phrase (spec §10)."
            ),
        },
        "unique_human_proven": False,
        "certified": False,
        "note": result.private_fields_note,
    }


@router.post("/uniqueness-check", summary="Vérifier l'unicité biométrique avant inscription")
def uniqueness_check(body: UniquenessCheckRequest) -> dict[str, Any]:
    """
    Vérifie si un template biométrique correspond à une identité déjà enregistrée.

    Retourne match_found=True → identité déjà présente (création refusée).
    Retourne match_found=False → nouveau template (inscription autorisée).

    Stub : comparaison par hash exact (production : FHE).
    """
    _reject_raw_biometric(body.model_dump())

    try:
        template_bytes = bytes.fromhex(body.template_hex)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"template_hex invalide : {exc}") from exc

    commitment = commit_biometric_template(template_bytes)
    existing_records = _load_records()
    result = check_uniqueness(commitment, existing_records)

    return {
        "match_found": result.match_found,
        "existing_human_id": result.existing_human_id,
        "match_score": result.match_score,
        "certified": result.certified,
        "unique_human_proven": result.unique_human_proven,
        "note": result.note,
    }


@router.get("/{human_id}", summary="Consulter un HumanIdentityRecord public")
def get_human_identity(human_id: str) -> dict[str, Any]:
    """
    Retourne le record public d'une identité biométrique.

    Ne retourne jamais :
      - template biométrique brut
      - blinding factor
      - secret FuzzyExtractor
    """
    records = _load_records()
    for rec in records:
        if rec.get("human_id") == human_id:
            # Retourner uniquement les champs publics
            return {
                "found": True,
                "human_id": rec.get("human_id"),
                "commitment": rec.get("commitment"),
                "template_hash": rec.get("template_hash"),
                "algorithm": rec.get("algorithm"),
                "biometric_version": rec.get("biometric_version"),
                "status": rec.get("status"),
                "created_at": rec.get("created_at"),
                "wallet_address": rec.get("wallet_address"),
                "unique_human_proven": rec.get("unique_human_proven", False),
                "node_id": rec.get("node_id"),
                # helper_data est public — nécessaire pour re-dérivation
                "helper_data": rec.get("helper_data"),
            }
    raise HTTPException(status_code=404, detail=f"HumanIdentity {human_id!r} not found")


@router.get("/", summary="Liste des human_id enregistrés (public)")
def list_human_identities() -> dict[str, Any]:
    """Liste les human_id publics. Ne retourne jamais les templates ni les blinding."""
    records = _load_records()
    return {
        "count": len(records),
        "human_ids": [r.get("human_id") for r in records if r.get("human_id")],
        "unique_human_proven": False,
        "certified": False,
        "note": "Stub P0-C — unicité par hash exact uniquement.",
    }
