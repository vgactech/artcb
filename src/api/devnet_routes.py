"""Routes artcb-devnet — faucet, explorer, Gradium TTS."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.crypto_policy import NETWORK_ID
from src.artcb.devnet.faucet import FaucetError
from src.artcb.integrations.gradium import GradiumError, synthesize_speech

logger = logging.getLogger("artcb.api.devnet")
router = APIRouter(prefix="/api/v1", tags=["devnet"])


class FaucetRequest(BaseModel):
    address: str = Field(min_length=10)


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str = "default"
    language: str = "fr"


def _state(request: Request):
    return request.app.state.artcb


@router.post("/devnet/faucet")
def devnet_faucet(body: FaucetRequest, request: Request) -> dict:
    """Distribue tARTCB de test. Interdit sur mainnet (D-017 / D-043)."""
    if not NETWORK_ID.endswith("devnet-1"):
        raise HTTPException(status_code=403, detail="faucet_disabled_on_mainnet")
    try:
        return request.app.state.artcb.faucet.request(body.address)
    except FaucetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/devnet/faucet/status")
def devnet_faucet_status(request: Request) -> dict:
    summary = _state(request).faucet.ledger_summary()
    summary["enabled"] = NETWORK_ID.endswith("devnet-1")
    return summary


@router.get("/chain/explorer")
def chain_explorer(request: Request) -> dict:
    """Explorer PoL — tip + 10 last visible blocks. No full-file verify."""
    state = _state(request)
    height = state.chain.height()
    start = max(0, height - 10)
    latest = list(state.chain.iter_blocks(from_index=start, limit=10))
    principal = state.authz.resolve(request)
    visible = state.authz.filter_blocks(principal, latest, "READ")
    public_n = sum(1 for b in latest if b.get("visibility") == "public")
    return {
        "network": NETWORK_ID,
        "block_count": height,
        "public_block_count": public_n,
        "public_block_count_window": public_n,
        "total_rewards_satoshi": state.chain._book.issued_satoshi() if hasattr(state.chain, "_book") else None,
        "symbol_registry_count": len(state.symbol_registry.export()),
        "latest_blocks": visible,
        "verify": {"valid": state.chain.chain_valid_tip(), "mode": "tip"},
    }


@router.post("/integrations/gradium/tts")
def gradium_tts(body: TtsRequest, request: Request) -> dict:
    """Synthese vocale Gradium avec fallback Web Speech documente."""
    try:
        return synthesize_speech(
            body.text,
            settings=_state(request).settings,
            voice=body.voice,
            language=body.language,
        )
    except GradiumError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
