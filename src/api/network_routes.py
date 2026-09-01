"""Public network directory — no wallet required (D-044).

Replit bootstrap can list infrastructure nodes without init-node.
This is a static verified registry, not automatic P2P discovery.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.artcb.crypto_policy import GENESIS_HASH, NETWORK_ID, PROTOCOL_VERSION
from src.artcb.node_registry import public_registry

router = APIRouter(prefix="/api/v1/network", tags=["network"])


@router.get("/nodes")
def list_infrastructure_nodes() -> dict:
    registry = public_registry()
    return {
        "network_id": NETWORK_ID,
        "protocol_version": PROTOCOL_VERSION,
        "genesis_hash": GENESIS_HASH,
        "discovery": "static_registry_not_dht",
        "wallet_required_for_p2p": True,
        "nodes": registry["nodes"],
    }
