"""
Phase 13 — Routes FastAPI libp2p natif ARTCB.

Endpoints :
  GET  /api/v1/p2p/libp2p/status          Statut nœud DHT + connexions
  GET  /api/v1/p2p/libp2p/peers           Pairs connus dans la table Kademlia
  POST /api/v1/p2p/libp2p/connect         Connecter un nouveau pair (host:port)
  POST /api/v1/p2p/libp2p/bootstrap       Bootstrap DHT depuis une liste de seeds
  POST /api/v1/p2p/libp2p/announce_block  Diffuser un bloc public via Gossipsub
  GET  /api/v1/p2p/libp2p/dht             Table Kademlia complète (debug)
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.p2p.libp2p_node import LibP2PNode
from src.api.api_keys_routes import require_operator_write

logger = logging.getLogger("artcb.api.p2p.libp2p")
router = APIRouter(prefix="/api/v1/p2p/libp2p", tags=["p2p-libp2p"])

# ── Singleton nœud libp2p (démarré à la demande) ─────────────────────────────
_libp2p_node: LibP2PNode | None = None
_libp2p_lock = asyncio.Lock()


async def _get_or_create_node(request: Request) -> LibP2PNode:
    """Retourne le nœud libp2p, le crée et le démarre si nécessaire."""
    global _libp2p_node
    async with _libp2p_lock:
        if _libp2p_node is not None and _libp2p_node._running:
            return _libp2p_node
        state = request.app.state.artcb
        identity = state.p2p_identity
        data_dir = Path(os.getenv("ARTCB_DATA_DIR", "data"))
        node = LibP2PNode(
            node_id=identity.node_id,
            host="0.0.0.0",
            port=identity.p2p_port,
            api_port=identity.api_port,
            data_dir=data_dir,
            kem_pub_hex=identity.kem_public_key_hex,
        )
        await node.start()
        _libp2p_node = node
        logger.info(
            "LibP2PNode démarré (Phase 13) node_id=%s port=%d",
            node.node_id, node.port,
        )
        return node


# ── Schémas ────────────────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)


class BootstrapRequest(BaseModel):
    seeds: list[str] = Field(
        description='Liste de seeds "host:port"',
        examples=[["192.168.1.2:18444", "10.0.0.5:18444"]],
    )


class AnnounceBlockRequest(BaseModel):
    block: dict = Field(description="Bloc public ARTCB à diffuser via Gossipsub")


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/status")
async def libp2p_status(request: Request) -> dict:
    """Statut libp2p — n'auto-démarre pas (un visiteur ne doit pas allumer le DHT)."""
    global _libp2p_node
    if _libp2p_node is None or not getattr(_libp2p_node, "_running", False):
        return {
            "running": False,
            "autostart": False,
            "message": "libp2p idle; POST /bootstrap requires operator Bearer",
        }
    return {"running": True, **_libp2p_node.status()}


@router.get("/peers")
async def libp2p_peers(request: Request) -> dict:
    """Pairs Kademlia — lecture seule, pas d'autostart."""
    global _libp2p_node
    if _libp2p_node is None or not getattr(_libp2p_node, "_running", False):
        return {"running": False, "peers": [], "count": 0, "connected": []}
    peers = _libp2p_node.dht.all_peers()
    return {
        "running": True,
        "peers": [p.to_dict() for p in peers],
        "count": len(peers),
        "connected": list(_libp2p_node._connections.keys()),
    }


@router.post("/connect")
async def libp2p_connect(
    body: ConnectRequest,
    request: Request,
    _auth: dict = Depends(require_operator_write),
) -> dict:
    """
    Connecte le nœud à un pair TCP distant.
    Retourne les infos du pair si connexion réussie.
    """
    node = await _get_or_create_node(request)
    peer = await node.connect_peer(body.host, body.port)
    if peer is None:
        raise HTTPException(
            status_code=502,
            detail=f"Impossible de se connecter à {body.host}:{body.port}",
        )
    return {"peer": peer.to_dict(), "message": "Connexion établie", "protocol": "ARTCB-P2P/1.0"}


@router.post("/bootstrap")
async def libp2p_bootstrap(
    body: BootstrapRequest,
    request: Request,
    _auth: dict = Depends(require_operator_write),
) -> dict:
    """
    Bootstrap Kademlia DHT depuis une liste de seeds.
    Format seeds : ["host:port", ...]
    """
    node = await _get_or_create_node(request)
    seeds: list[tuple[str, int]] = []
    for s in body.seeds:
        try:
            h, p = s.rsplit(":", 1)
            seeds.append((h.strip(), int(p)))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Seed invalide : {s!r}") from None
    discovered = await node.bootstrap(seeds)
    return {
        "discovered": discovered,
        "dht_total": node.dht.peer_count(),
        "connected": len(node._connections),
        "seeds_tried": len(seeds),
    }


@router.post("/announce_block")
async def libp2p_announce_block(
    body: AnnounceBlockRequest,
    request: Request,
    _auth: dict = Depends(require_operator_write),
) -> dict:
    """
    Diffuse un bloc public à tous les pairs connectés via Gossipsub.
    Le bloc doit avoir visibility="public".
    """
    node = await _get_or_create_node(request)
    if body.block.get("visibility") != "public":
        raise HTTPException(
            status_code=400,
            detail="Seuls les blocs public peuvent être diffusés via Gossipsub",
        )
    sent = await node.announce_block(body.block)
    return {
        "sent_to_peers": sent,
        "connected_peers": len(node._connections),
        "gossipsub": "ARTCB-Gossipsub/1.0",
    }


@router.get("/dht")
async def libp2p_dht(request: Request) -> dict:
    """Table Kademlia — lecture seule, pas d'autostart."""
    global _libp2p_node
    if _libp2p_node is None or not getattr(_libp2p_node, "_running", False):
        return {"running": False, "dht": {}, "message": "libp2p idle"}
    return {
        "running": True,
        "own_node_id": _libp2p_node.node_id,
        "dht": _libp2p_node.dht.to_dict(),
        "network_id": _libp2p_node.network_id,
        "protocol": "Kademlia-ARTCB/1.0",
    }


@router.delete("/stop")
async def libp2p_stop(_auth: dict = Depends(require_operator_write)) -> dict:
    """Arrête proprement le nœud libp2p (admin)."""
    global _libp2p_node
    async with _libp2p_lock:
        if _libp2p_node and _libp2p_node._running:
            await _libp2p_node.stop()
            _libp2p_node = None
            return {"stopped": True}
        return {"stopped": False, "message": "Nœud non actif"}
