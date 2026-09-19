"""R348 — HTTP API for USER ↔ NODE association (challenge + signature).

Does not modify /wallet/create device binding (R345).
Does not claim UNIQUE_HUMAN.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.identity.user_node_association import (
    PROTOCOL,
    UserNodeAssociationError,
    UserNodeAssociationStore,
    issue_challenge,
    reject_private_key_fields,
    verify_and_build_association,
)

logger = logging.getLogger("artcb.api.user_node")
router = APIRouter(prefix="/api/v1/identity/user-node", tags=["identity-user-node"])

# In-memory challenges (TTL short); associations persist under data/
_challenges: dict[str, dict[str, Any]] = {}


def _state(request: Request):
    return request.app.state.artcb


def _store(request: Request) -> UserNodeAssociationStore:
    data_dir = _state(request).settings.data_dir
    return UserNodeAssociationStore(data_dir / "identity" / "user_node_associations.json")


class AssociateBody(BaseModel):
    model_config = {"extra": "forbid"}

    user_address: str = Field(min_length=8)
    user_public_key_hex: str = Field(min_length=32)
    challenge: str = Field(min_length=16)
    signature_hex: str = Field(min_length=16)
    role: str = Field(default="client")


@router.get("/challenge", summary="Challenge for USER↔NODE association (sign locally)")
def user_node_challenge(request: Request) -> dict[str, Any]:
    state = _state(request)
    ident = state.p2p_identity
    node_id = getattr(ident, "node_id", "") or ""
    node_wallet = getattr(ident, "wallet_address", None)
    out = issue_challenge(
        node_id=node_id,
        node_wallet_address=node_wallet,
        store=_challenges,
    )
    out["r345_untouched"] = True
    out["human_registry_not_required"] = True
    out["persistence"] = "LOCAL_NODE"
    return out


@router.post("/associate", summary="Bind USER to NODE via Ed25519 signature (no privkey)")
async def user_node_associate(request: Request) -> dict[str, Any]:
    # Scan RAW JSON before Pydantic so seed_hex/private_key cannot be silently dropped.
    try:
        raw = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_json"}) from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail={"code": "invalid_json_object"})
    try:
        reject_private_key_fields(raw)
        body = AssociateBody.model_validate(raw)
        rec = verify_and_build_association(
            challenge=body.challenge,
            store=_challenges,
            user_address=body.user_address,
            user_public_key_hex=body.user_public_key_hex,
            signature_hex=body.signature_hex,
            role=body.role,
        )
        stored = _store(request).upsert(rec)
    except UserNodeAssociationError as exc:
        code = str(exc)
        status = 400
        if code == "signature_invalid":
            status = 401
        raise HTTPException(status_code=status, detail={"code": code, "protocol": PROTOCOL}) from exc
    except Exception as exc:
        # pydantic ValidationError → 422
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        raise

    logger.info(
        "user_node_associated user=%s node=%s role=%s persistence=LOCAL_NODE",
        stored.user_address[:20],
        stored.node_id[:24],
        stored.role,
    )
    return {
        "protocol": PROTOCOL,
        "ok": True,
        "association": stored.to_dict(),
        "persistence": "LOCAL_NODE",
        "unique_human": False,
        "certified_100": False,
        "r345_untouched": True,
        "note": "Association ≠ wallet ownership bind (R349) ≠ UNIQUE_HUMAN; not network-replicated yet",
    }


@router.get("/status", summary="List USER↔NODE associations (local node store)")
def user_node_status(
    request: Request,
    user_address: str | None = None,
) -> dict[str, Any]:
    store = _store(request)
    state = _state(request)
    node_id = getattr(state.p2p_identity, "node_id", "") or ""
    if user_address:
        rows = store.list_for_user(user_address)
    else:
        rows = store.list_for_node(node_id)
    return {
        "protocol": PROTOCOL,
        "node_id": node_id,
        "count": len(rows),
        "associations": rows,
        "persistence": "LOCAL_NODE",
        "unique_human": False,
        "certified_100": False,
        "r345_untouched": True,
    }
