"""Governance REST routes — vote majorité (GOUVERNANCE_ARTCB.md)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.artcb.governance.manager import GovernanceError, GovernanceManager

logger = logging.getLogger("artcb.api.governance")
router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


class CreateProposalRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3)
    version: str = Field(min_length=1, max_length=32)
    vote_days: int = Field(default=14, ge=1, le=90)
    created_by: str = "ARTCB"
    proposal_id: str | None = None


class CastVoteRequest(BaseModel):
    proposal_id: str = Field(min_length=8)
    wallet_address: str = Field(min_length=8)
    choice: Literal["yes", "no"]


class CreatorKeyRotationRequest(BaseModel):
    """Rotation de cle createur — signature obligatoire."""
    old_address: str = Field(min_length=8, description="Ancienne adresse createur")
    new_address: str = Field(min_length=8, description="Nouvelle adresse createur")
    signature_hex: str = Field(
        min_length=1,
        description=(
            "Signature hybride de l'ancienne cle. "
            "Format : 'ed25519:HEX' ou 'hybrid:ed25519:HEX|mldsa65:HEX'. "
            "Message signe : f'{old_address}:{new_address}:{timestamp_ISO8601Z}'"
        ),
    )
    pqc_public_key_hex: str | None = Field(
        default=None,
        description="Clé publique ML-DSA-65 requise si signature hybrid: (AND des deux jambes).",
    )


class UserKeyRotationRequest(BaseModel):
    """Rotation de cle utilisateur — signature obligatoire."""
    old_address: str = Field(min_length=8, description="Ancienne adresse wallet")
    new_address: str = Field(min_length=8, description="Nouvelle adresse wallet")
    signature_hex: str = Field(
        min_length=1,
        description=(
            "Signature hybride de l'ancienne cle. "
            "Format : 'ed25519:HEX' ou 'hybrid:ed25519:HEX|mldsa65:HEX'. "
            "Message signe : f'{old_address}:{new_address}:{timestamp_ISO8601Z}'"
        ),
    )
    pqc_public_key_hex: str | None = Field(
        default=None,
        description="Clé publique ML-DSA-65 requise si signature hybrid: (AND des deux jambes).",
    )


def _state(request: Request):
    return request.app.state.artcb


def _governance(request: Request) -> GovernanceManager:
    return _state(request).governance


def _gov_http_error(exc: GovernanceError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "GOVERNANCE_ERROR", "message": str(exc)})


@router.get("/proposals")
def list_proposals(
    request: Request,
    status: str | None = Query(None, description="open|accepted|rejected|expired"),
) -> dict:
    mgr = _governance(request)
    proposals = mgr.list_proposals(status=status)  # type: ignore[arg-type]
    items = []
    for proposal in proposals:
        items.append({**proposal.to_dict(), "tally": mgr.tally(proposal.proposal_id)})
    return {"proposals": items, "count": len(items)}


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, request: Request) -> dict:
    mgr = _governance(request)
    try:
        return mgr.proposal_with_tally(proposal_id)
    except GovernanceError as exc:
        raise _gov_http_error(exc) from exc


@router.post("/proposals")
def create_proposal(body: CreateProposalRequest, request: Request) -> dict:
    """ARTCB crée une proposition de mise à jour majeure."""
    mgr = _governance(request)
    try:
        proposal = mgr.create_proposal(
            title=body.title,
            description=body.description,
            version=body.version,
            vote_days=body.vote_days,
            created_by=body.created_by,
            proposal_id=body.proposal_id,
        )
        return {"proposal": proposal.to_dict(), "tally": mgr.tally(proposal.proposal_id)}
    except GovernanceError as exc:
        raise _gov_http_error(exc) from exc


@router.post("/vote")
def cast_vote(body: CastVoteRequest, request: Request) -> dict:
    """1 wallet = 1 voix — valider ou rejeter une mise à jour majeure."""
    mgr = _governance(request)
    try:
        vote = mgr.cast_vote(
            proposal_id=body.proposal_id,
            wallet_address=body.wallet_address,
            choice=body.choice,
        )
        return {
            "vote": vote.to_dict(),
            "tally": mgr.tally(body.proposal_id),
            "requires_rollback": mgr.tally(body.proposal_id)["requires_rollback"],
        }
    except GovernanceError as exc:
        raise _gov_http_error(exc) from exc


@router.post("/creator-key-rotation", summary="Rotation de clé créateur (signature obligatoire)")
def creator_key_rotation(body: CreatorKeyRotationRequest, request: Request) -> dict:
    """Rotation de cle createur ARTCB — inscrit un bloc special signe dans la chaine.

    SECURITE : signature_hex est OBLIGATOIRE.
    Format : 'ed25519:HEX' ou 'hybrid:ed25519:HEX|mldsa65:HEX'.
    Message a signer : f'{old_address}:{new_address}:{timestamp_ISO8601Z}'
    (timestamp au format '2026-08-05T12:00:00Z' — utiliser la seconde courante).

    Retourne 400 si signature absente, invalide ou si old_address ne correspond
    pas au createur actuel.
    """
    mgr = _governance(request)
    state = _state(request)
    try:
        result = mgr.creator_key_rotation(
            old_address=body.old_address,
            new_address=body.new_address,
            signature_hex=body.signature_hex,
            blocks_path=state.chain.blocks_path if hasattr(state, "chain") else None,
            pqc_public_key_hex=body.pqc_public_key_hex,
        )
        logger.warning(
            "API CREATOR KEY ROTATION: %s... -> %s... sig=%s",
            body.old_address[:16], body.new_address[:16],
            result.get("sig_status", "?"),
        )
        return result
    except GovernanceError as exc:
        raise _gov_http_error(exc) from exc


@router.post("/user-key-rotation", summary="Rotation de clé utilisateur (signature obligatoire)")
def user_key_rotation(body: UserKeyRotationRequest, request: Request) -> dict:
    """Rotation de cle utilisateur ARTCB — inscrit un bloc special signe dans la chaine.

    SECURITE : signature_hex est OBLIGATOIRE.
    Format : 'ed25519:HEX' ou 'hybrid:ed25519:HEX|mldsa65:HEX'.
    Message a signer : f'{old_address}:{new_address}:{timestamp_ISO8601Z}'
    (timestamp au format '2026-08-05T12:00:00Z' — utiliser la seconde courante).

    Retourne 400 si signature absente ou invalide.
    """
    mgr = _governance(request)
    state = _state(request)
    try:
        result = mgr.user_key_rotation(
            old_address=body.old_address,
            new_address=body.new_address,
            signature_hex=body.signature_hex,
            blocks_path=state.chain.blocks_path if hasattr(state, "chain") else None,
            pqc_public_key_hex=body.pqc_public_key_hex,
        )
        logger.info(
            "API USER KEY ROTATION: %s... -> %s... sig=%s",
            body.old_address[:16], body.new_address[:16],
            result.get("sig_status", "?"),
        )
        return result
    except GovernanceError as exc:
        raise _gov_http_error(exc) from exc
