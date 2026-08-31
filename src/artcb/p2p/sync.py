"""Synchronisation P2P — blocs publics uniquement (jamais private en clair)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.artcb.chain import ffi
from src.artcb.chain.ffi import HASH_VERSION_V1, HASH_VERSION_V2
from src.artcb.chain.manager import ChainManager
from src.artcb.crypto.kem import KEMError, decrypt_payload, encrypt_payload
from src.artcb.p2p.node_identity import NodeIdentity
from src.artcb.p2p.peers import PeerManager, PeerRecord
from src.artcb.p2p.public_archive import PublicBlockArchive
from src.artcb.p2p.symbol_sync import SymbolSyncService

logger = logging.getLogger("artcb.p2p.sync")


class P2PSyncError(Exception):
    """P2P sync failed."""


class P2PSyncService:
    """
    Sync artcb-devnet : propagation des blocs ``visibility=public`` seulement.
    Transport chiffré ML-KEM + AES-GCM entre pairs.
    """

    def __init__(
        self,
        *,
        chain: ChainManager,
        peers: PeerManager,
        identity: NodeIdentity,
        archive: PublicBlockArchive | None = None,
        symbol_sync: SymbolSyncService | None = None,
    ) -> None:
        self.chain = chain
        self.peers = peers
        self.identity = identity
        self.archive = archive or PublicBlockArchive(chain.blocks_path.parent.parent)
        self.symbol_sync = symbol_sync

    def get_public_blocks(self, *, from_index: int = 0) -> list[dict[str, Any]]:
        blocks = self.chain.list_blocks(visibility="public")
        return [b for b in blocks if int(b.get("index", 0)) >= from_index]

    def import_public_blocks(
        self,
        blocks: list[dict[str, Any]],
        *,
        from_node_id: str = "unknown",
        extend_tip: bool = False,
    ) -> int:
        """Archive blocs publics reçus — vérifie hash structure (signature nœud distant)."""
        valid: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("visibility") != "public":
                logger.warning("Rejected non-public block index=%s in P2P sync", block.get("index"))
                continue
            if not self.verify_block_structure(block):
                logger.warning("Rejected invalid public block structure index=%s", block.get("index"))
                continue
            valid.append(block)
        stored = 0
        if self.archive:
            stored = self.archive.store_blocks(valid, from_node_id=from_node_id)
        extended = 0
        if extend_tip:
            for block in valid:
                try:
                    if self.chain.import_extending_public_block(block):
                        extended += 1
                except Exception as exc:
                    logger.debug("public block did not extend local tip: %s", exc)
        if self.symbol_sync:
            self.symbol_sync.extract_from_blocks(valid, from_node_id=from_node_id)
        return stored + extended

    @staticmethod
    def verify_block_structure(block: dict) -> bool:
        """Vérifie cohérence hash — signature = clé du nœud émetteur (pas vérifiable localement)."""
        try:
            eco = None
            version = int(block.get("hash_version") or HASH_VERSION_V1)
            if version >= HASH_VERSION_V2:
                eco = str(
                    block.get("economic_root")
                    or (block.get("economics") or {}).get("economic_root")
                    or ""
                )
            expected = ffi.build_block_hash(
                int(block["index"]),
                str(block["timestamp"]),
                str(block["prev_hash"]),
                str(block["graph_root"]),
                str(block.get("merkle_root") or block["graph_root"]),
                float(block["pol_score"]),
                economic_root=eco,
            )
        except (KeyError, TypeError, ValueError):
            return False
        return block.get("hash") == expected

    def build_encrypted_envelope(self, blocks: list[dict[str, Any]], peer: PeerRecord) -> dict[str, str]:
        payload = json.dumps({"blocks": blocks, "network_id": self.identity.network_id}, ensure_ascii=False).encode(
            "utf-8"
        )
        peer_pk = bytes.fromhex(peer.kem_public_key_hex)
        envelope = encrypt_payload(payload, peer_pk)
        envelope["from_node_id"] = self.identity.node_id
        envelope["from_kem_public_key_hex"] = self.identity.kem_public_key_hex
        return envelope

    def decrypt_envelope(self, envelope: dict[str, str]) -> dict[str, Any]:
        secret = bytes.fromhex(self.identity.kem_secret_key_hex)
        plaintext = decrypt_payload(envelope, secret)
        return json.loads(plaintext.decode("utf-8"))

    def push_to_peer(self, peer: PeerRecord, *, from_index: int = 0) -> dict[str, Any]:
        blocks = self.get_public_blocks(from_index=from_index)
        if not blocks:
            return {"peer_id": peer.peer_id, "pushed": 0, "message": "Aucun bloc public à envoyer"}
        try:
            envelope = self.build_encrypted_envelope(blocks, peer)
        except (KEMError, ValueError, RuntimeError) as exc:
            logger.error("P2P push envelope to %s failed: %s", peer.peer_id, type(exc).__name__)
            self.peers.update_peer_status(peer.peer_id, last_sync_ok=False)
            raise P2PSyncError(f"push_encrypt_failed:{type(exc).__name__}") from exc
        url = f"{peer.base_url}/api/v1/p2p/blocks/receive"
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, json={"envelope": envelope})
                r.raise_for_status()
                data = r.json()
            self.peers.update_peer_status(peer.peer_id, last_sync_ok=True, blocks_received_delta=0)
            return {
                "peer_id": peer.peer_id,
                "pushed": len(blocks),
                "imported_remote": data.get("imported", 0),
                "encrypted": True,
                "kem": "ML-KEM-768",
            }
        except Exception as exc:
            logger.error("P2P push to %s failed: %s", peer.peer_id, exc)
            self.peers.update_peer_status(peer.peer_id, last_sync_ok=False)
            raise P2PSyncError(str(exc)) from exc

    def pull_from_peer(self, peer: PeerRecord, *, from_index: int = 0) -> dict[str, Any]:
        """Demande les blocs publics au pair (GET clair pour liste, puis import local)."""
        url = f"{peer.base_url}/api/v1/p2p/blocks/public"
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.get(url, params={"from_index": from_index})
                r.raise_for_status()
                blocks = r.json().get("blocks", [])
            imported = self.import_public_blocks(
                blocks,
                from_node_id=peer.peer_id,
                extend_tip=bool(getattr(peer, "protocol_compatible", False)),
            )
            self.peers.update_peer_status(
                peer.peer_id,
                last_sync_ok=True,
                blocks_received_delta=imported,
            )
            return {"peer_id": peer.peer_id, "received": len(blocks), "imported": imported}
        except Exception as exc:
            logger.error("P2P pull from %s failed: %s", peer.peer_id, exc)
            self.peers.update_peer_status(peer.peer_id, last_sync_ok=False)
            raise P2PSyncError(str(exc)) from exc

    def sync_all_peers(self, *, from_index: int = 0) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for peer in self.peers.list_peers():
            pulled: dict[str, Any] | None = None
            try:
                pulled = self.pull_from_peer(peer, from_index=from_index)
                pushed = self.push_to_peer(peer, from_index=from_index)
                results.append({"peer_id": peer.peer_id, "pull": pulled, "push": pushed, "ok": True})
            except P2PSyncError as exc:
                results.append(
                    {
                        "peer_id": peer.peer_id,
                        "ok": False,
                        "error": str(exc),
                        "pull": pulled,
                        "push_ok": False,
                    }
                )
            except Exception as exc:  # noqa: BLE001 — never turn a secondary path into HTTP 500
                logger.error("P2P sync peer %s unexpected: %s", peer.peer_id, type(exc).__name__)
                results.append(
                    {
                        "peer_id": peer.peer_id,
                        "ok": False,
                        "error": type(exc).__name__,
                        "pull": pulled,
                    }
                )
        return results
