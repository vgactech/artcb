"""P2P artcb-devnet REST routes — sync blocs publics + transport ML-KEM."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.artcb.crypto.kem import advertised_kem_algorithm
from src.artcb.crypto.pqc import pqc_available
from src.artcb.crypto_policy import (
    GENESIS_HASH,
    NETWORK_ID,
    PROTOCOL_VERSION,
    capabilities,
    local_suite,
)
from src.artcb.p2p.handshake import build_signed_card, load_or_create_handshake_key
from src.artcb.p2p.sync import P2PSyncError

logger = logging.getLogger("artcb.api.p2p")
router = APIRouter(prefix="/api/v1/p2p", tags=["p2p"])


class AddPeerRequest(BaseModel):
    host: str = Field(min_length=3)
    port: int = Field(ge=1, le=65535)
    kem_public_key_hex: str = Field(min_length=32)
    label: str = ""
    crypto_suite: str = ""
    network_id: str = ""
    protocol_version: str = ""
    genesis_hash: str = ""
    capability_card: dict | None = None
    peer_id: str | None = None


class ReceiveBlocksRequest(BaseModel):
    envelope: dict[str, str]


def _state(request: Request):
    return request.app.state.artcb


def _local_capability_card(state) -> dict:
    pqc = pqc_available()
    identity = state.p2p_identity
    key = load_or_create_handshake_key(state.settings.data_dir)
    return build_signed_card(
        node_id=identity.node_id,
        kem_public_key_hex=identity.kem_public_key_hex,
        crypto_suite=local_suite(pqc),
        protocol_version=PROTOCOL_VERSION,
        network_id=NETWORK_ID,
        genesis_hash=GENESIS_HASH,
        handshake=key,
    )


@router.get("/status")
def p2p_status(request: Request) -> dict:
    state = _state(request)
    identity = state.p2p_identity
    peers = state.p2p_peers.list_peers()
    public_count = len(state.chain.list_blocks(visibility="public"))
    incoming_count = len(state.p2p_archive.list_blocks())
    pqc = pqc_available()
    card = _local_capability_card(state)
    return {
        "network_id": identity.network_id,
        "node_id": identity.node_id,
        "kem_public_key_hex": identity.kem_public_key_hex,
        "kem_algorithm": advertised_kem_algorithm(identity.kem_public_key_hex),
        "p2p_port": identity.p2p_port,
        "api_port": identity.api_port,
        "peer_count": len(peers),
        "public_blocks_local": public_count,
        "public_blocks_incoming": incoming_count,
        "private_never_synced": True,
        "pool_e2e_available": True,
        "pool_crypto": "ML-KEM-768",
        "protocol_version": PROTOCOL_VERSION,
        "genesis_hash": GENESIS_HASH,
        "crypto_suite": local_suite(pqc),
        "crypto_policy": capabilities(pqc),
        "capability_card": card,
        "public_state_digest": state.chain.public_state_digest(),
        "last_hash": state.chain.last_hash(),
        "message": "Calcul local par défaut — pool opt-in E2E ML-KEM ; sync P2P = blocs publics chiffrés",
    }


@router.get("/peers")
def list_peers(request: Request) -> dict:
    peers = _state(request).p2p_peers.list_peers()
    return {"peers": [p.to_dict() for p in peers], "count": len(peers)}


@router.post("/peers")
def add_peer(body: AddPeerRequest, request: Request) -> dict:
    mgr = _state(request).p2p_peers
    try:
        peer = mgr.add_peer(
            host=body.host,
            port=body.port,
            kem_public_key_hex=body.kem_public_key_hex,
            label=body.label,
            crypto_suite=body.crypto_suite,
            network_id=body.network_id,
            protocol_version=body.protocol_version,
            genesis_hash=body.genesis_hash,
            capability_card=body.capability_card,
            peer_id=body.peer_id,
        )
        return {"peer": peer.to_dict(), "message": "Pair ajouté"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/peers/{peer_id}")
def remove_peer(peer_id: str, request: Request) -> dict:
    if not _state(request).p2p_peers.remove_peer(peer_id):
        raise HTTPException(status_code=404, detail="Peer not found")
    return {"deleted": peer_id}


class RegisterPublicNodeRequest(BaseModel):
    """Auto-enregistrement d'un nouveau nœud public sur le réseau bootstrap ARTCB."""
    node_public_url: str = Field(min_length=8, description="URL publique du nœud (https://...)")
    node_label: str = Field(default="", max_length=128, description="Nom lisible du nœud")
    device_fingerprint: str = Field(min_length=8, description="SHA-256 du fingerprint appareil")
    github_repository: str | None = Field(default=None, description="Repo GitHub source (ex: vgac2025/lvx)")
    github_actor: str | None = Field(default=None, description="Compte GitHub de l'opérateur")
    network_id: str = Field(default="artcb-devnet-1", description="Réseau cible")


@router.post("/register-public", summary="Auto-enregistrement d'un nœud public (bootstrap)")
def register_public_node(body: RegisterPublicNodeRequest, request: Request) -> dict:
    """
    Endpoint bootstrap : un nouveau nœud se déclare sur le réseau ARTCB.

    Appelé automatiquement par le GitHub Actions 'register-node.yml' lors du
    premier déploiement d'une nouvelle instance clonée.

    Le nœud est ajouté à la liste des pairs P2P (peers.json) avec son URL publique.
    Aucune authentification requise — les données sont publiques (URL, fingerprint).

    Sécurité : le fingerprint identifie l'appareil de façon unique mais ne contient
    pas de données personnelles (hash non réversible).
    """
    import re
    state = _state(request)

    # Valider l'URL (doit être https:// ou http://localhost)
    url = body.node_public_url.rstrip("/")
    if not re.match(r"^https?://", url):
        raise HTTPException(status_code=400, detail="node_public_url doit commencer par http:// ou https://")

    # Vérifier que le réseau correspond
    if body.network_id != NETWORK_ID:
        raise HTTPException(
            status_code=400,
            detail=f"Réseau inconnu: {body.network_id} — ce nœud est sur {NETWORK_ID}",
        )

    # Extraire host:port depuis l'URL
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # Générer un peer_id basé sur le fingerprint
    import hashlib
    peer_id = "peer_" + hashlib.sha256(body.device_fingerprint.encode()).hexdigest()[:12]

    # Tenter de récupérer la clé KEM publique du nœud distant
    kem_public_hex = ""
    remote_suite = ""
    remote_nid = ""
    remote_pv = ""
    remote_gh = ""
    remote_card = None
    try:
        import httpx
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{url}/api/v1/p2p/status")
            r.raise_for_status()
            payload = r.json()
            kem_public_hex = payload.get("kem_public_key_hex", "")
            remote_suite = payload.get("crypto_suite") or ""
            remote_nid = payload.get("network_id") or ""
            remote_pv = payload.get("protocol_version") or ""
            remote_gh = payload.get("genesis_hash") or ""
            if isinstance(payload.get("capability_card"), dict):
                remote_card = payload.get("capability_card")
    except Exception as exc:
        logger.info("Could not fetch KEM key from %s: %s", url, exc)
        kem_public_hex = "00" * 32  # placeholder si le nœud n'est pas encore joignable

    # Enregistrer le pair
    try:
        peer = state.p2p_peers.add_peer(
            host=host,
            port=port,
            kem_public_key_hex=kem_public_hex,
            label=body.node_label or f"Node {peer_id[:8]}",
            peer_id=peer_id,
            crypto_suite=remote_suite,
            network_id=remote_nid,
            protocol_version=remote_pv,
            genesis_hash=remote_gh,
            capability_card=remote_card,
        )
        logger.info(
            "New node registered: peer_id=%s url=%s fingerprint=%s... repo=%s",
            peer_id, url, body.device_fingerprint[:16], body.github_repository,
        )
        return {
            "registered": True,
            "peer_id": peer_id,
            "message": f"Nœud {peer_id} enregistré sur le réseau ARTCB",
            "peer": peer.to_dict(),
            "network_id": body.network_id,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc




@router.get("/blocks/public")
def get_public_blocks(
    request: Request,
    from_index: int = Query(0, ge=0),
) -> dict:
    """Liste blocs publics locaux — endpoint pull devnet."""
    sync = _state(request).p2p_sync
    blocks = sync.get_public_blocks(from_index=from_index)
    return {"blocks": blocks, "count": len(blocks), "from_index": from_index}


@router.get("/blocks/incoming")
def list_incoming_public(request: Request, from_index: int = Query(0, ge=0)) -> dict:
    archive = _state(request).p2p_archive
    blocks = archive.list_blocks(from_index=from_index)
    return {"blocks": blocks, "count": len(blocks), "source": "p2p_incoming_public"}


@router.post("/blocks/receive")
def receive_encrypted_blocks(body: ReceiveBlocksRequest, request: Request) -> dict:
    """Reçoit un lot de blocs publics chiffré ML-KEM."""
    sync = _state(request).p2p_sync
    try:
        payload = sync.decrypt_envelope(body.envelope)
        blocks = payload.get("blocks", [])
        from_node = body.envelope.get("from_node_id", "unknown")
        imported = sync.import_public_blocks(blocks, from_node_id=from_node)
        return {"imported": imported, "received": len(blocks), "encrypted": True}
    except Exception as exc:
        logger.error("P2P receive failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync")
def sync_all(request: Request, from_index: int = Query(0, ge=0)) -> dict:
    """Pull + optional encrypted push for every peer.

    Per-peer crypto/push failures are recorded in ``results`` (HTTP 200).
    A broken secondary push must not turn the whole route into HTTP 500.
    """
    sync = _state(request).p2p_sync
    try:
        results = sync.sync_all_peers(from_index=from_index)
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_all unexpected")
        raise HTTPException(status_code=502, detail=type(exc).__name__) from exc
    return {"results": results, "peer_count": len(results), "http_meaning": "200=route_ok_inspect_per_peer"}


@router.post("/sync/{peer_id}")
def sync_peer(peer_id: str, request: Request, from_index: int = Query(0, ge=0)) -> dict:
    state = _state(request)
    peer = state.p2p_peers.get_peer(peer_id)
    if not peer:
        raise HTTPException(status_code=404, detail="Peer not found")
    sync = state.p2p_sync
    try:
        pulled = sync.pull_from_peer(peer, from_index=from_index)
        pushed = sync.push_to_peer(peer, from_index=from_index)
        sym = state.symbol_sync.sync_all_peers()
        return {"peer_id": peer_id, "pull": pulled, "push": pushed, "symbols": sym}
    except P2PSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/symbols/public")
def get_public_symbols(request: Request) -> dict:
    symbols = _state(request).symbol_sync.get_local_symbols()
    return {"symbols": symbols, "count": len(symbols), "node_id": _state(request).p2p_identity.node_id}


@router.post("/symbols/receive")
def receive_symbols(body: dict, request: Request) -> dict:
    state = _state(request)
    symbols = body.get("symbols", {})
    from_node = body.get("from_node_id", "unknown")
    merged = state.symbol_sync.import_remote_symbols(symbols, from_node_id=from_node)
    return {"merged": merged, "received": len(symbols)}


@router.post("/symbols/sync")
def sync_symbols(request: Request) -> dict:
    results = _state(request).symbol_sync.sync_all_peers()
    return {"results": results}


@router.get("/gossip/announcements")
def gossip_announcements(request: Request) -> dict:
    return {"announcements": _state(request).gossip.list_announcements()}


@router.post("/gossip/announce")
def gossip_announce(request: Request, host: str = "127.0.0.1") -> dict:
    """Annonce ce nœud sur le réseau gossip.
    Le paramètre ``host`` peut être passé en query string pour exposer
    l'adresse publique réelle (ex: IP OVH, domaine ngrok…) plutôt que
    127.0.0.1 qui n'est accessible qu'en local.
    """
    state = _state(request)
    identity = state.p2p_identity
    import os
    public_host = os.getenv("ARTCB_PUBLIC_HOST", host)
    entry = state.gossip.announce(
        node_id=identity.node_id,
        host=public_host,
        api_port=identity.api_port,
        p2p_port=identity.p2p_port,
        kem_public_key_hex=identity.kem_public_key_hex,
        symbol_count=len(state.symbol_registry.export()),
    )
    return {"announcement": entry, "network_id": "artcb-devnet-1", "p2p_port": identity.p2p_port}


@router.post("/gossip/receive")
def gossip_receive(body: dict, request: Request) -> dict:
    entry = body.get("announcement", body)
    ok = _state(request).gossip.merge_remote_announcement(entry)
    return {"merged": ok}
