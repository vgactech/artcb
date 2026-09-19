"""Routes FastAPI — Bridges blockchain ARTCB (Phase 12.2).

Endpoints :
    POST /api/v1/bridges/import         — importer une tx externe dans ARTCB
    GET  /api/v1/bridges/status         — état de tous les bridges
    GET  /api/v1/bridges/{chain}/last   — dernière tx importée par chaîne
    GET  /api/v1/interop/chains         — liste des chaînes supportées
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.bridges.manager import BridgeError, BridgeManager, SUPPORTED_CHAINS

logger = logging.getLogger("artcb.api.bridges")
router = APIRouter(prefix="/api/v1", tags=["bridges"])

_bridge_manager = BridgeManager()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BridgeImportRequest(BaseModel):
    chain: str = Field(..., description="Blockchain source", examples=["ethereum"])
    tx_hash: str = Field(..., description="Hash de la transaction")
    description: str = Field("", description="Description optionnelle")
    gravity_visibility: str = Field("private", description="Visibilité du bloc ARTCB gravé")


class BridgeImportResponse(BaseModel):
    chain: str
    tx_hash: str
    block_index: int | None = None
    pol_score: float | None = None
    ir_text: str
    message: str
    gravure_status: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/bridges/import", response_model=BridgeImportResponse, summary="Importer une tx externe dans ARTCB")
async def bridge_import(body: BridgeImportRequest, request: Request) -> BridgeImportResponse:
    """Lit une transaction sur une blockchain externe et l'encode en IR PoL dans ARTCB."""
    try:
        result = _bridge_manager.import_transaction(chain=body.chain, tx_hash=body.tx_hash)
    except BridgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    ir_text = result.ir_text
    if body.description:
        ir_text += f" Contexte : {body.description}"

    # Graver dans la chaîne ARTCB via l'app state
    block_index: int | None = None
    pol_score: float | None = None
    gravure_status = "pending"
    try:
        artcb = request.app.state.artcb
        chain_mgr = artcb.chain
        encoder = artcb.encoder
        graph = encoder.encode(ir_text)
        block = chain_mgr.append_block(
            graph=graph,
            visibility=body.gravity_visibility,
            memo_type=f"bridge_{body.chain}",
            contributors=[],
            source="bridge",
        )
        block_index = block.get("index")
        pol_score = block.get("pol_score")
        gravure_status = "gravé"
        logger.info("Bridge import gravé bloc=#%d chain=%s tx=%s", block_index, body.chain, body.tx_hash[:16])
    except Exception as exc:
        logger.warning("Bridge import gravure échouée : %s", exc)
        gravure_status = f"erreur_gravure: {exc!s:.80}"

    return BridgeImportResponse(
        chain=result.chain,
        tx_hash=result.tx_hash,
        block_index=block_index,
        pol_score=pol_score,
        ir_text=ir_text[:500],
        message=f"Transaction {body.chain.upper()} encodée en IR PoL et gravée dans ARTCB.",
        gravure_status=gravure_status,
    )


@router.get("/bridges/status", summary="État de tous les bridges")
async def bridges_status() -> dict[str, Any]:
    """Ping tous les RPC configurés et retourne leur statut."""
    statuses = _bridge_manager.status_all()
    ok_count = sum(1 for s in statuses if s.get("status") == "ok")
    return {
        "bridges": statuses,
        "summary": f"{ok_count}/{len(statuses)} bridges opérationnels",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/bridges/{chain}/last", summary="Dernière tx importée par chaîne")
async def bridge_last(chain: str) -> dict[str, Any]:
    """Ping le bridge d'une chaîne spécifique et retourne le dernier bloc disponible."""
    if chain.lower() not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=404, detail=f"Chaîne non supportée : {chain}")
    status = _bridge_manager.ping_chain(chain)
    return {"chain": chain, **status, "timestamp": datetime.now(UTC).isoformat()}


@router.get("/interop/chains", summary="Liste des chaînes supportées")
async def interop_chains() -> dict[str, Any]:
    """Retourne la liste des blockchains supportées par les bridges ARTCB."""
    chains_info = []
    for c in SUPPORTED_CHAINS:
        chains_info.append({
            "chain": c,
            "type": "EVM" if c in ("ethereum", "bnb", "polygon", "avalanche") else c.upper(),
            "bridge_type": "semantic_pol",
            "description": f"Import de transactions {c.upper()} encodées en IR PoL dans ARTCB",
        })
    return {
        "supported_chains": chains_info,
        "total": len(SUPPORTED_CHAINS),
        "bridge_principle": "lecture_seule_encodage_semantique",
        "no_token_transfer": True,
        "pqc_signing": "ML-DSA-65",
    }
