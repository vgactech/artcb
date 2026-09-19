"""R349 — HTTP API USER ↔ WALLET ownership (LOCAL_NODE, replication-ready fields)."""

MODULE_VERSION = '1.0.0'  # R390 — auto-versioning
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError

from src.artcb.identity.user_wallet_ownership import (
    PROTOCOL,
    UserWalletBindError,
    UserWalletOwnershipStore,
    issue_challenge,
    reject_private_key_fields,
    verify_and_build,
)

logger = logging.getLogger("artcb.api.user_wallet")
router = APIRouter(prefix="/api/v1/identity/user-wallet", tags=["identity-user-wallet"])
_challenges: dict[str, dict[str, Any]] = {}


def _state(request: Request):
    return request.app.state.artcb


def _store(request: Request) -> UserWalletOwnershipStore:
    return UserWalletOwnershipStore(
        _state(request).settings.data_dir / "identity" / "user_wallet_ownership.json"
    )


class BindBody(BaseModel):
    model_config = {"extra": "forbid"}

    owner_public_key_hex: str = Field(min_length=32)
    challenge: str = Field(min_length=16)
    signature_hex: str = Field(min_length=16)
    user_label: str = Field(default="")


@router.get("/challenge")
def user_wallet_challenge(
    request: Request,
    wallet_address: str = Query(min_length=8),
) -> dict[str, Any]:
    state = _state(request)
    node_id = getattr(state.p2p_identity, "node_id", "") or ""
    # Wallet must exist on this node (ownership of unknown address is meaningless here)
    from src.artcb.wallet.manager import WalletManager

    wallets = WalletManager().list_wallets()
    if not any(w.get("address") == wallet_address.strip() for w in wallets):
        raise HTTPException(
            status_code=404,
            detail={"code": "wallet_unknown_on_node", "protocol": PROTOCOL},
        )
    return issue_challenge(
        wallet_address=wallet_address,
        node_id=node_id,
        store=_challenges,
    )


@router.post("/bind")
async def user_wallet_bind(request: Request) -> dict[str, Any]:
    try:
        raw = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_json"}) from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail={"code": "invalid_json_object"})
    try:
        reject_private_key_fields(raw)
        body = BindBody.model_validate(raw)
        rec = verify_and_build(
            challenge=body.challenge,
            store=_challenges,
            owner_public_key_hex=body.owner_public_key_hex,
            signature_hex=body.signature_hex,
            user_label=body.user_label,
        )
        # Optional consistency: pubkey must match wallet metadata on this node
        from src.artcb.wallet.manager import WalletManager

        wallets = WalletManager().list_wallets()
        meta = next((w for w in wallets if w.get("address") == rec.wallet_address), None)
        if meta and meta.get("public_key_hex"):
            if meta["public_key_hex"].lower() != rec.owner_public_key_hex.lower():
                raise UserWalletBindError("public_key_mismatch_wallet_meta")
        stored = _store(request).upsert(rec)
    except UserWalletBindError as exc:
        code = str(exc)
        status = 401 if code == "signature_invalid" else 400
        raise HTTPException(status_code=status, detail={"code": code, "protocol": PROTOCOL}) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    logger.info(
        "user_wallet_bound wallet=%s persistence=LOCAL_NODE event=%s",
        stored.get("wallet_address", "")[:18],
        stored.get("event_id"),
    )
    return {
        "protocol": PROTOCOL,
        "ok": True,
        "ownership": stored,
        "persistence": "LOCAL_NODE",
        "replication_target": "REPLICATED_PROTOCOL",
        "unique_human": False,
        "certified_100": False,
        "r345_untouched": True,
        "r348_separate": True,
        "note": "USER↔WALLET ownership ≠ USER↔NODE ≠ UNIQUE_HUMAN",
    }


@router.get("/status")
def user_wallet_status(
    request: Request,
    wallet_address: str | None = None,
) -> dict[str, Any]:
    store = _store(request)
    if wallet_address:
        row = store.get(wallet_address)
        rows = [row] if row else []
    else:
        rows = store.list_all()
    return {
        "protocol": PROTOCOL,
        "count": len(rows),
        "ownerships": rows,
        "persistence": "LOCAL_NODE",
        "replication_target": "REPLICATED_PROTOCOL",
        "unique_human": False,
        "certified_100": False,
    }
