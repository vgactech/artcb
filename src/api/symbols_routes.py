"""Routes API — registre symboles originaux IA."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("artcb.api.symbols")
router = APIRouter(prefix="/api/v1/symbols", tags=["symbols"])


class PublishSymbolsRequest(BaseModel):
    symbols: dict[str, str] = Field(default_factory=dict)
    graph_id: str | None = None
    block_index: int | None = None


def _state(request: Request):
    return request.app.state.artcb


@router.get("/registry")
def get_symbol_registry(request: Request) -> dict:
    state = _state(request)
    return {
        "concepts": state.symbol_registry.export(),
        "count": len(state.symbol_registry.export()),
        "path": str(state.symbol_registry.path),
    }


@router.post("/publish")
def publish_symbols(body: PublishSymbolsRequest, request: Request) -> dict:
    state = _state(request)
    if not body.symbols:
        raise HTTPException(status_code=422, detail="symbols required")
    published = state.publish_public_symbols(
        body.symbols,
        block_index=body.block_index,
        graph_id=body.graph_id,
    )
    return {"published": published, "count": len(published)}


@router.get("/archive")
def list_symbol_archive(request: Request) -> dict:
    entries = _state(request).symbol_archive.list_entries()
    return {"entries": entries, "count": len(entries)}


@router.post("/sync")
def sync_symbols_peers(request: Request) -> dict:
    results = _state(request).symbol_sync.sync_all_peers()
    return {"results": results, "peer_count": len(results)}
