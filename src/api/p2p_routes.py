"""P2P artcb-devnet REST routes — sync blocs publics + transport ML-KEM."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
from src.artcb.p2p.node_identity import advertised_base_url
from src.artcb.p2p.public_url import (
    is_https_platform_host,
    peer_host_is_stale_link_local,
    public_register_url_ok,
)
from src.artcb.p2p.sync import P2PSyncError
from src.artcb.security.hardware_identity import public_machine_view
from src.api.api_keys_routes import require_operator_write

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


class OfferBlocksRequest(BaseModel):
    """Public plaintext offer — same decide_public_import as encrypted receive.

    A well-formed tip-extension still appends (visibility=public). The live
    Byzantine probe must only send payloads that the guard rejects.
    """

    blocks: list[dict] = Field(default_factory=list)
    from_node_id: str = Field(default="unknown", max_length=80)


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
        "anonymous_p2p_public_only": True,
        "official_replica_full_book": True,
        "pool_e2e_available": True,
        "pool_crypto": "ML-KEM-768",
        "protocol_version": PROTOCOL_VERSION,
        "genesis_hash": GENESIS_HASH,
        "crypto_suite": local_suite(pqc),
        "crypto_policy": capabilities(pqc),
        "capability_card": card,
        "public_state_digest": state.chain.public_state_digest(),
        "last_hash": state.chain.last_hash(),
        "node_public_url": identity.node_public_url,
        "advertised_base_url": advertised_base_url(identity.node_public_url, identity.api_port),
        "machine": public_machine_view(state.device_identity),
        "producer_failover": (
            state.producer_failover.status()
            if getattr(state, "producer_failover", None) is not None
            else {"wired": False, "will_append_blocks": False}
        ),
        # GO-N + GO-B : le header KEM ne garantit pas le chiffrement.
        # Clé absente, longueur ≠ 1184, KEM off, ou encrypt_payload KO → clair + encrypt_error.
        "message": (
            "Calcul local par défaut — pool opt-in E2E ML-KEM ; "
            "push P2P chiffré ML-KEM+AES-GCM ; "
            "pull : clair sans header KEM ; "
            "chiffré seulement si header KEM 1184 octets ET encapsulage OK "
            "(sinon encrypted=false + encrypt_error, fallback clair)"
        ),
    }


@router.get("/reputation")
def p2p_reputation(request: Request) -> dict:
    """Vue humaine JSON du ledger binaire GO-M. Le stockage reste ``index.bin``."""
    state = _state(request)
    ledger = getattr(state, "reputation_ledger", None)
    if ledger is None:
        return {"nodes": [], "count": 0, "storage": "absent", "format": "json_human_only"}
    nodes = [rec.to_dict() for rec in ledger.all_records()]
    return {
        "nodes": nodes,
        "count": len(nodes),
        "storage": "p2p/reputation/index.bin",
        "format": "json_human_only",
        "binary_record_bytes": 80,
    }


@router.get("/peers")
def list_peers(request: Request) -> dict:
    peers = _state(request).p2p_peers.list_peers()
    hidden = [p for p in peers if peer_host_is_stale_link_local(p.host)]
    visible = [p for p in peers if not peer_host_is_stale_link_local(p.host)]
    return {
        "peers": [p.to_dict() for p in visible],
        "count": len(visible),
        "stale_link_local_hidden": len(hidden),
        "note": (
            "169.254 metadata peers stay on disk (stale) but are hidden here. "
            "No live rewrite of peers.json."
        ),
    }


@router.post("/peers")
def add_peer(
    body: AddPeerRequest,
    request: Request,
    _auth: dict = Depends(require_operator_write),
) -> dict:
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
            scheme=(
                "https"
                if body.port == 443 or is_https_platform_host(body.host)
                else "http"
            ),
        )
        return {"peer": peer.to_dict(), "message": "Pair ajouté"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/peers/{peer_id}")
def remove_peer(
    peer_id: str,
    request: Request,
    _auth: dict = Depends(require_operator_write),
) -> dict:
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
    network_id: str = Field(default="", description="Réseau cible")


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
    ok_url, url_reason = public_register_url_ok(url)
    if not ok_url:
        raise HTTPException(status_code=400, detail=f"register_url_rejected:{url_reason}")

    # Vérifier que le réseau correspond
    nid = (body.network_id or "").strip() or NETWORK_ID
    if nid != NETWORK_ID:
        raise HTTPException(
            status_code=400,
            detail=f"Réseau inconnu: {nid} — ce nœud est sur {NETWORK_ID}",
        )

    # Extraire host:port depuis l'URL
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    peer_scheme = "https" if parsed.scheme == "https" else "http"

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
    remote_bootstrap = False
    try:
        import httpx
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{url}/api/v1/p2p/status")
            r.raise_for_status()
            payload = r.json()
            remote_bootstrap = bool(payload.get("bootstrap_mode"))
            kem_public_hex = payload.get("kem_public_key_hex", "") or ""
            remote_suite = payload.get("crypto_suite") or ""
            remote_nid = payload.get("network_id") or ""
            remote_pv = payload.get("protocol_version") or ""
            remote_gh = payload.get("genesis_hash") or ""
            if isinstance(payload.get("capability_card"), dict):
                remote_card = payload.get("capability_card")
    except Exception as exc:
        logger.info("Could not fetch KEM key from %s: %s", url, exc)
        kem_public_hex = ""

    from src.artcb.p2p.seed_discovery import DirectoryStore
    DirectoryStore(state.settings.data_dir).upsert(
        {
            "url": url,
            "label": body.node_label,
            "source": "register-public",
            "device_fingerprint_prefix": body.device_fingerprint[:16],
            "bootstrap_mode": remote_bootstrap,
        }
    )
    placeholder = (not kem_public_hex) or set(kem_public_hex) <= {"0"} or remote_bootstrap
    if placeholder:
        return {
            "registered": True,
            "observer": True,
            "peer_id": peer_id,
            "message": f"Observateur {peer_id} enregistré (pas de KEM — bootstrap ou clone)",
            "network_id": nid,
        }

    # Enregistrer le pair P2P seulement si une vraie clé KEM est là
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
            scheme=peer_scheme,
        )
        logger.info(
            "New node registered: peer_id=%s url=%s fingerprint=%s... repo=%s",
            peer_id, url, body.device_fingerprint[:16], body.github_repository,
        )
        return {
            "registered": True,
            "observer": False,
            "peer_id": peer_id,
            "message": f"Nœud {peer_id} enregistré sur le réseau ARTCB",
            "peer": peer.to_dict(),
            "network_id": nid,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc




@router.get("/blocks/public")
def get_public_blocks(
    request: Request,
    from_index: int = Query(0, ge=0),
) -> dict:
    """Liste blocs publics locaux — endpoint pull P2P.

    GO-B 2026-09-07 : header X-ARTCB-KEM-Public-Key **peut** produire une
    enveloppe ML-KEM-768 + AES-GCM. Ce n'est pas automatique.

    Sans header → clair (rétrocompat).
    Header + clé 1184 octets + encapsulage OK → ``encrypted=true``.
    Header mais clé invalide / KEM off / exception → clair + ``encrypt_error``.
    """
    from src.artcb.crypto.kem import encrypt_payload, KEMError, MLKEM768_PUBLIC_BYTES
    import json as _json

    sync = _state(request).p2p_sync
    blocks = sync.get_public_blocks(from_index=from_index)

    requester_kem_hex = request.headers.get("X-ARTCB-KEM-Public-Key", "").strip()
    requester_node_id = request.headers.get("X-ARTCB-Node-Id", "unknown").strip()

    if not requester_kem_hex:
        # Rétrocompatibilité : pull en clair (devnet / anciens nœuds)
        logger.debug("P2P pull GET /blocks/public en clair (pas de X-ARTCB-KEM-Public-Key)")
        return {"blocks": blocks, "count": len(blocks), "from_index": from_index, "encrypted": False}

    # GO-B : chiffrer la réponse avec la clé KEM du demandeur
    try:
        peer_pk = bytes.fromhex(requester_kem_hex)
        if len(peer_pk) != MLKEM768_PUBLIC_BYTES:
            raise ValueError(f"KEM public key invalide : {len(peer_pk)} bytes (attendu {MLKEM768_PUBLIC_BYTES})")
        state = _state(request)
        payload = _json.dumps({
            "blocks": blocks,
            "network_id": state.p2p_sync.identity.network_id,
            "from_node_id": state.p2p_sync.identity.node_id,
            "from_kem_public_key_hex": state.p2p_sync.identity.kem_public_key_hex,
        }, ensure_ascii=False).encode("utf-8")
        envelope = encrypt_payload(payload, peer_pk)
        # Lier from_node_id au demandeur (vérifiable via sa clé KEM)
        envelope["from_node_id"] = state.p2p_sync.identity.node_id
        envelope["requester_node_id"] = requester_node_id
        envelope["requester_kem_sha256"] = __import__("hashlib").sha256(peer_pk).hexdigest()[:16]
        logger.info(
            "P2P pull GET /blocks/public chiffré ML-KEM → requester_node=%s blocks=%d",
            requester_node_id[:20], len(blocks),
        )
        return {"envelope": envelope, "encrypted": True, "count": len(blocks), "from_index": from_index}
    except (KEMError, ValueError, Exception) as exc:
        logger.warning("P2P pull chiffrement échoué (%s) — fallback en clair", exc)
        return {"blocks": blocks, "count": len(blocks), "from_index": from_index, "encrypted": False, "encrypt_error": str(exc)[:80]}


@router.get("/blocks/incoming")
def list_incoming_public(request: Request, from_index: int = Query(0, ge=0)) -> dict:
    archive = _state(request).p2p_archive
    blocks = archive.list_blocks(from_index=from_index)
    return {"blocks": blocks, "count": len(blocks), "source": "p2p_incoming_public"}


@router.post("/blocks/offer")
def offer_public_blocks(body: OfferBlocksRequest, request: Request) -> dict:
    """Anonymous public offer. Verdicts are the same as receive/pull.

    Returns each decide_public_import reason. Does not wipe the book.
    Not a BFT commit vote.
    """
    sync = _state(request).p2p_sync
    from_node = (body.from_node_id or "unknown").strip() or "unknown"
    height_before = len(sync.chain._read_all_blocks())
    tip_before = sync.chain.last_hash()
    imported = sync.import_public_blocks(list(body.blocks or []), from_node_id=from_node)
    decisions = [
        {"action": d.action, "reason": d.reason} for d in (sync.last_import_decisions or [])
    ]
    if any(row["action"] == "append" for row in decisions):
        logger.warning("public offer appended from_node=%s n=%s", from_node[:24], imported)
    return {
        "imported": imported,
        "received": len(body.blocks or []),
        "decisions": decisions,
        "height_before": height_before,
        "height_after": len(sync.chain._read_all_blocks()),
        "tip_before": tip_before,
        "tip_after": sync.chain.last_hash(),
        "from_node_id": from_node,
        "not_block_append_bft": True,
        "encrypted": False,
    }


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
def sync_all(
    request: Request,
    from_index: int = Query(0, ge=0),
    _auth: dict = Depends(require_operator_write),
) -> dict:
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
def sync_peer(
    peer_id: str,
    request: Request,
    from_index: int = Query(0, ge=0),
    _auth: dict = Depends(require_operator_write),
) -> dict:
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
def sync_symbols(
    request: Request,
    _auth: dict = Depends(require_operator_write),
) -> dict:
    results = _state(request).symbol_sync.sync_all_peers()
    return {"results": results}


@router.get("/gossip/announcements")
def gossip_announcements(request: Request) -> dict:
    return {"announcements": _state(request).gossip.list_announcements()}


@router.post("/gossip/announce")
def gossip_announce(
    request: Request,
    host: str = "127.0.0.1",
    _auth: dict = Depends(require_operator_write),
) -> dict:
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
    return {"announcement": entry, "network_id": NETWORK_ID, "p2p_port": identity.p2p_port}


def _require_official_replica_peer(request: Request) -> str:
    from src.artcb.p2p.official_replica import replica_peer_allowed, request_peer_host

    host = request_peer_host(request)
    if not replica_peer_allowed(host):
        raise HTTPException(status_code=403, detail="official_replica_peers_only")
    return host


@router.get("/flux")
def p2p_flux(request: Request, limit: int = Query(200, ge=1, le=2000)) -> dict:
    """Real push/pull/replica timings. Empty until a real inter-node send runs."""
    from src.artcb.p2p.flux import list_flux, summarize_flux

    state = _state(request)
    rows = list_flux(state.settings.data_dir, limit=limit)
    return {
        "rows": rows,
        "summary": summarize_flux(rows),
        "path": "data/p2p/flux.jsonl",
        "ingest_1065_had_no_inter_node_flux": True,
    }


@router.get("/replica/blocks")
def replica_blocks(
    request: Request,
    from_index: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=80),
) -> dict:
    """Full-book slice for official compute IPv4s only. Not anonymous P2P."""
    _require_official_replica_peer(request)
    from src.artcb.p2p.official_replica import list_replica_blocks

    sync = _state(request).p2p_sync
    blocks = list_replica_blocks(sync, from_index=from_index, limit=limit)
    return {
        "kind": "official_replica",
        "blocks": blocks,
        "count": len(blocks),
        "from_index": from_index,
        "height": len(sync.chain._read_all_blocks()),
        "last_hash": sync.chain.last_hash(),
    }


@router.post("/replica/push")
def replica_push(body: ReceiveBlocksRequest, request: Request) -> dict:
    """Receive an encrypted official-replica chunk (any visibility)."""
    host = _require_official_replica_peer(request)
    from src.artcb.p2p.flux import append_flux
    from src.artcb.p2p.official_replica import import_replica_blocks

    sync = _state(request).p2p_sync
    t0 = time.perf_counter()
    try:
        payload = sync.decrypt_envelope(body.envelope)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"replica_decrypt_failed:{type(exc).__name__}") from exc
    if payload.get("kind") != "official_replica":
        raise HTTPException(status_code=400, detail="not_official_replica")
    blocks = payload.get("blocks") or []
    if not isinstance(blocks, list):
        raise HTTPException(status_code=400, detail="bad_replica_blocks")
    height_before = len(sync.chain._read_all_blocks())
    result = import_replica_blocks(
        sync,
        blocks,
        from_node_id=str(body.envelope.get("from_node_id") or "official-replica"),
    )
    append_flux(
        sync.chain.blocks_path.parent.parent,
        {
            "kind": "official_replica_blocks",
            "direction": "receive",
            "peer": body.envelope.get("from_node_id", "unknown"),
            "host": host,
            "chunk": f"{payload.get('from_index')}-{payload.get('to_index')}",
            "pushed": len(blocks),
            "imported": result.get("imported"),
            "http_ms": round((time.perf_counter() - t0) * 1000, 2),
            "height_before": height_before,
            "height_after": result.get("height"),
            "ok": not result.get("rejected"),
        },
    )
    return {**result, "encrypted": True, "from_host": host}


@router.post("/replica/files")
def replica_files(body: ReceiveBlocksRequest, request: Request) -> dict:
    """Receive encrypted graphs / KCG / ingest index for official peers."""
    host = _require_official_replica_peer(request)
    from src.artcb.p2p.flux import append_flux
    from src.artcb.p2p.official_replica import write_replica_files

    sync = _state(request).p2p_sync
    t0 = time.perf_counter()
    try:
        payload = sync.decrypt_envelope(body.envelope)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"replica_decrypt_failed:{type(exc).__name__}") from exc
    if payload.get("kind") != "official_replica_files":
        raise HTTPException(status_code=400, detail="not_official_replica_files")
    files = payload.get("files") or []
    if not isinstance(files, list):
        raise HTTPException(status_code=400, detail="bad_replica_files")
    result = write_replica_files(sync.chain.blocks_path.parent.parent, files)
    append_flux(
        sync.chain.blocks_path.parent.parent,
        {
            "kind": "official_replica_files",
            "direction": "receive",
            "peer": body.envelope.get("from_node_id", "unknown"),
            "host": host,
            "pushed": len(files),
            "imported": result.get("written"),
            "http_ms": round((time.perf_counter() - t0) * 1000, 2),
            "ok": result.get("rejected", 1) == 0,
        },
    )
    return {**result, "encrypted": True, "from_host": host}


@router.post("/replica/run")
def replica_run(
    request: Request,
    include_files: bool = Query(True),
    _auth: dict = Depends(require_operator_write),
) -> dict:
    """Operator: push the local book to the other official compute nodes."""
    from src.artcb.p2p.official_replica import run_official_replica

    return run_official_replica(_state(request).p2p_sync, include_files=include_files)


@router.post("/gossip/receive")
def gossip_receive(body: dict, request: Request) -> dict:
    entry = body.get("announcement", body)
    host = str(entry.get("host") or "")
    port = int(entry.get("api_port") or 80)
    scheme = "https" if is_https_platform_host(host) or port == 443 else "http"
    url = f"{scheme}://{host}:{port}"
    ok, reason = public_register_url_ok(url)
    if not ok:
        raise HTTPException(status_code=400, detail=f"gossip_host_rejected:{reason}")
    merged = _state(request).gossip.merge_remote_announcement(entry)
    return {"merged": merged}
