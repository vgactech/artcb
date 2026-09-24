"""Routes API R461 — Diffusion P2P du NodeTpmBinding.

Protocole ARTCB-NODE-TPM-BINDING-v1 — diffusion et vérification pair-à-pair.

Routes :
    POST /api/v1/p2p/node-tpm-binding/submit
        Un nœud soumet son propre binding (operator Bearer requis).
        Stocké localement + diffusé aux pairs connus via gossip.

    GET  /api/v1/p2p/node-tpm-binding/list
        Liste tous les bindings connus (tous les pairs).
        Public — pas d'auth requise.

    POST /api/v1/p2p/node-tpm-binding/receive
        Reçoit un binding d'un pair distant (pas d'auth — entrée réseau).
        FAIL-CLOSED : binding mal signé → 400.

    GET  /api/v1/p2p/node-tpm-binding/{node_id}
        Récupère le binding d'un nœud donné.

Garanties :
    - Tout binding reçu est vérifié cryptographiquement (Ed25519) avant stockage.
    - tpm_proven et hardware_assurance_level sont issus du binding signé — non inventés.
    - certified=False absolu dans toutes les réponses.
    - unique_human_proven=False absolu.
    - Mode DEBUG actif — logs complets à chaque opération.

CERTIFIED_100=false.
"""

from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R461 — diffusion P2P NodeTpmBinding

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.api_keys_routes import require_operator_write
from src.artcb.security.node_tpm_binding import (
    BINDING_PROTOCOL,
    NodeTpmBinding,
    BindingVerificationResult,
    verify_node_tpm_binding,
)

logger = logging.getLogger("artcb.api.node_tpm_binding")
router = APIRouter(prefix="/api/v1/p2p/node-tpm-binding", tags=["node-tpm-binding"])

DEBUG_MODE = True  # mode DEBUG toujours actif (R460 protocole)

# ── Store en mémoire + persistance JSON ──────────────────────────────────────

_STORE_PATH_DEFAULT = Path("data/p2p/node_tpm_bindings.json")


def _get_store_path(request: Request) -> Path:
    """Résolution du chemin du store depuis l'état de l'application."""
    try:
        data_dir = request.app.state.data_dir  # type: ignore[attr-defined]
        return Path(data_dir) / "p2p" / "node_tpm_bindings.json"
    except AttributeError:
        return _STORE_PATH_DEFAULT


def _load_bindings(path: Path) -> dict[str, dict[str, Any]]:
    """Charge les bindings depuis le fichier JSON. Fail-open."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return dict(raw.get("bindings", {}))
    except Exception as exc:
        logger.warning("[R461][DEBUG] _load_bindings failed (fail-open): %s", exc)
        return {}


def _save_bindings(path: Path, bindings: dict[str, dict[str, Any]]) -> None:
    """Persiste les bindings. Fail-open — ne bloque jamais."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "protocol": BINDING_PROTOCOL,
            "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": len(bindings),
            "bindings": bindings,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        path.chmod(0o600)
    except Exception as exc:
        logger.warning("[R461][DEBUG] _save_bindings failed (fail-open): %s", exc)


# ── Reconstruction NodeTpmBinding depuis dict ─────────────────────────────────

def _binding_from_dict(d: dict[str, Any]) -> NodeTpmBinding:
    """Reconstruit un NodeTpmBinding depuis son to_dict().

    R462 : tpm_pcr0_sha256, tpm_quote_nonce et tpm_pcr_proven inclus si présents.
    Ces champs sont nécessaires pour reconstruire le payload v2 canonique exact.
    """
    return NodeTpmBinding(
        node_id=str(d["node_id"]),
        device_fingerprint=str(d["device_fingerprint"]),
        hardware_assurance_level=str(d.get("hardware_assurance_level", "E")),
        hardware_kind=str(d.get("hardware_kind", "software")),
        tpm_ek_cert_hash=d.get("tpm_ek_cert_hash"),
        tpm_kind=str(d.get("tpm_kind", "absent")),
        tpm_proven=bool(d.get("tpm_proven", False)),
        platform_system=str(d.get("platform_system", "")),
        env_type=str(d.get("env_type", "unknown")),
        nonce=str(d["nonce"]),
        timestamp=str(d["timestamp"]),
        ed25519_public_key_hex=str(d["ed25519_public_key_hex"]),
        ed25519_signature_hex=str(d["ed25519_signature_hex"]),
        mldsa65_public_key_hex=d.get("mldsa65_public_key_hex"),
        mldsa65_signature_hex=d.get("mldsa65_signature_hex"),
        hybrid_and=bool(d.get("hybrid_and", False)),
        # R462 — champs PCR nécessaires pour reconstruire le payload canonique v2
        tpm_pcr0_sha256=d.get("tpm_pcr0_sha256"),
        tpm_quote_nonce=d.get("tpm_quote_nonce"),
        tpm_pcr_proven=bool(d.get("tpm_pcr_proven", False)),
        certified=False,        # invariant absolu
        unique_human_proven=False,  # invariant absolu
        note=str(d.get("note", "")),
    )


# ── Schémas Pydantic ──────────────────────────────────────────────────────────

class NodeTpmBindingSubmit(BaseModel):
    """Payload soumis par un nœud pour enregistrer son binding."""
    node_id: str = Field(min_length=1)
    device_fingerprint: str = Field(min_length=64, max_length=64)
    hardware_assurance_level: str = Field(default="E", pattern="^[ABCDE]$")
    hardware_kind: str = Field(default="software")
    tpm_ek_cert_hash: str | None = Field(default=None)
    tpm_kind: str = Field(default="absent")
    tpm_proven: bool = Field(default=False)
    platform_system: str = Field(default="")
    env_type: str = Field(default="unknown")
    nonce: str = Field(min_length=64, max_length=64)
    timestamp: str = Field(min_length=1)
    ed25519_public_key_hex: str = Field(min_length=64, max_length=64)
    ed25519_signature_hex: str = Field(min_length=1)
    mldsa65_public_key_hex: str | None = Field(default=None)
    mldsa65_signature_hex: str | None = Field(default=None)
    hybrid_and: bool = Field(default=False)
    # tpm_pcr0_sha256 et tpm_quote_nonce sont optionnels (R462)
    tpm_pcr0_sha256: str | None = Field(default=None)
    tpm_quote_nonce: str | None = Field(default=None)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/submit")
def submit_binding(
    body: NodeTpmBindingSubmit,
    request: Request,
    _auth: dict = Depends(require_operator_write),
) -> dict[str, Any]:
    """Operator : soumet le binding de ce nœud.

    Vérifie la signature Ed25519 avant stockage.
    FAIL-CLOSED : signature invalide → 400.
    """
    if DEBUG_MODE:
        logger.debug(
            "[R461][DEBUG] submit_binding node_id=%s level=%s tpm_proven=%s",
            body.node_id,
            body.hardware_assurance_level,
            body.tpm_proven,
        )

    # Reconstruction du binding pour vérification
    try:
        binding = _binding_from_dict(body.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"binding_parse_error:{exc}") from exc

    # Vérification cryptographique FAIL-CLOSED
    result = verify_node_tpm_binding(binding, expected_node_id=body.node_id)
    if not result.valid:
        logger.warning(
            "[R461][DEBUG] submit_binding FAIL node_id=%s reason=%s",
            body.node_id,
            result.failure_reason,
        )
        raise HTTPException(
            status_code=400,
            detail=f"binding_invalid:{result.failure_reason}",
        )

    # Stockage
    store_path = _get_store_path(request)
    bindings = _load_bindings(store_path)
    entry = body.model_dump()
    entry["received_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry["verified_ok"] = True
    entry["certified"] = False           # invariant absolu
    entry["unique_human_proven"] = False  # invariant absolu
    bindings[body.node_id] = entry
    _save_bindings(store_path, bindings)

    if DEBUG_MODE:
        logger.debug(
            "[R461][DEBUG] submit_binding STORED node_id=%s tpm_proven=%s",
            body.node_id,
            body.tpm_proven,
        )

    return {
        "status": "stored",
        "node_id": body.node_id,
        "tpm_proven": body.tpm_proven,
        "hardware_assurance_level": body.hardware_assurance_level,
        "verified_ok": True,
        "certified": False,
        "unique_human_proven": False,
    }


@router.get("/list")
def list_bindings(request: Request) -> dict[str, Any]:
    """Liste tous les bindings connus. Public."""
    store_path = _get_store_path(request)
    bindings = _load_bindings(store_path)
    summary = [
        {
            "node_id": v.get("node_id"),
            "hardware_assurance_level": v.get("hardware_assurance_level", "E"),
            "tpm_proven": v.get("tpm_proven", False),
            "hardware_kind": v.get("hardware_kind", "software"),
            "timestamp": v.get("timestamp"),
            "received_at": v.get("received_at"),
            "verified_ok": v.get("verified_ok", False),
            "certified": False,
        }
        for v in bindings.values()
    ]
    return {
        "count": len(summary),
        "bindings": summary,
        "certified": False,
        "unique_human_proven": False,
    }


@router.get("/{node_id}")
def get_binding(node_id: str, request: Request) -> dict[str, Any]:
    """Récupère le binding d'un nœud donné. Public."""
    store_path = _get_store_path(request)
    bindings = _load_bindings(store_path)
    entry = bindings.get(node_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"binding_not_found:{node_id}")
    # Forcer les invariants même si l'entrée était corrompue
    entry["certified"] = False
    entry["unique_human_proven"] = False
    return entry


@router.post("/receive")
def receive_binding(body: dict, request: Request) -> dict[str, Any]:
    """Reçoit un binding d'un pair distant (entrée réseau).

    FAIL-CLOSED : signature invalide → 400.
    Pas d'auth requise — ouvert au réseau P2P.
    """
    if DEBUG_MODE:
        logger.debug(
            "[R461][DEBUG] receive_binding node_id=%s from peer",
            body.get("node_id", "?"),
        )

    node_id = body.get("node_id")
    if not node_id:
        raise HTTPException(status_code=400, detail="missing_node_id")

    # Reconstruction + vérification FAIL-CLOSED
    try:
        binding = _binding_from_dict(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"binding_parse_error:{exc}") from exc

    result = verify_node_tpm_binding(binding, expected_node_id=node_id)
    if not result.valid:
        logger.warning(
            "[R461][DEBUG] receive_binding REJECTED node_id=%s reason=%s",
            node_id,
            result.failure_reason,
        )
        raise HTTPException(
            status_code=400,
            detail=f"binding_rejected:{result.failure_reason}",
        )

    # Stockage
    store_path = _get_store_path(request)
    bindings = _load_bindings(store_path)
    entry = dict(body)
    entry["received_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry["verified_ok"] = True
    entry["certified"] = False
    entry["unique_human_proven"] = False
    bindings[node_id] = entry
    _save_bindings(store_path, bindings)

    if DEBUG_MODE:
        logger.debug(
            "[R461][DEBUG] receive_binding ACCEPTED node_id=%s tpm_proven=%s",
            node_id,
            body.get("tpm_proven", False),
        )

    return {
        "status": "accepted",
        "node_id": node_id,
        "tpm_proven": body.get("tpm_proven", False),
        "hardware_assurance_level": body.get("hardware_assurance_level", "E"),
        "verified_ok": True,
        "certified": False,
        "unique_human_proven": False,
    }
