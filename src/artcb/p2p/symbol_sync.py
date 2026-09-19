"""Synchronisation P2P des symboles publics (blockchain publique + gossip HTTP)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import Any

import httpx

from src.artcb.ir.symbol_store import PersistentSymbolRegistry
from src.artcb.p2p.peers import PeerManager, PeerRecord
from src.artcb.p2p.symbol_archive import PublicSymbolArchive

logger = logging.getLogger("artcb.p2p.symbol_sync")


class SymbolSyncError(Exception):
    pass


class SymbolSyncService:
    """Pull/push symboles via API P2P — complement gossip devnet."""

    def __init__(
        self,
        *,
        registry: PersistentSymbolRegistry,
        archive: PublicSymbolArchive,
        peers: PeerManager,
        node_id: str,
    ) -> None:
        self.registry = registry
        self.archive = archive
        self.peers = peers
        self.node_id = node_id

    def get_local_symbols(self) -> dict[str, str]:
        return self.registry.export()

    def publish_public_symbols(
        self,
        symbols: dict[str, str],
        *,
        block_index: int | None = None,
        graph_id: str | None = None,
    ) -> dict[str, str]:
        published = self.registry.publish_from_graph(symbols)
        self.archive.store_entry(
            published,
            from_node_id=self.node_id,
            block_index=block_index,
            graph_id=graph_id,
        )
        return published

    def import_remote_symbols(
        self,
        symbols: dict[str, str],
        *,
        from_node_id: str = "unknown",
        block_index: int | None = None,
    ) -> int:
        if not symbols:
            return 0
        self.archive.store_entry(
            symbols,
            from_node_id=from_node_id,
            block_index=block_index,
        )
        return self.registry.merge_remote(symbols, from_node_id=from_node_id, block_index=block_index)

    def extract_from_blocks(self, blocks: list[dict[str, Any]], *, from_node_id: str) -> int:
        total = 0
        for block in blocks:
            if block.get("visibility") != "public":
                continue
            symbols = block.get("public_symbols") or {}
            if symbols:
                total += self.import_remote_symbols(
                    symbols,
                    from_node_id=from_node_id,
                    block_index=int(block.get("index", 0)),
                )
        return total

    def pull_from_peer(self, peer: PeerRecord) -> dict[str, Any]:
        url = f"{peer.base_url}/api/v1/p2p/symbols/public"
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.get(url)
                r.raise_for_status()
                symbols = r.json().get("symbols", {})
            merged = self.import_remote_symbols(symbols, from_node_id=peer.peer_id)
            return {"peer_id": peer.peer_id, "received": len(symbols), "merged": merged}
        except Exception as exc:
            logger.error("Symbol pull from %s failed: %s", peer.peer_id, exc)
            raise SymbolSyncError(str(exc)) from exc

    def push_to_peer(self, peer: PeerRecord) -> dict[str, Any]:
        symbols = self.get_local_symbols()
        if not symbols:
            return {"peer_id": peer.peer_id, "pushed": 0}
        url = f"{peer.base_url}/api/v1/p2p/symbols/receive"
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.post(
                    url,
                    json={"symbols": symbols, "from_node_id": self.node_id},
                )
                r.raise_for_status()
                data = r.json()
            return {
                "peer_id": peer.peer_id,
                "pushed": len(symbols),
                "merged_remote": data.get("merged", 0),
            }
        except Exception as exc:
            logger.error("Symbol push to %s failed: %s", peer.peer_id, exc)
            raise SymbolSyncError(str(exc)) from exc

    def sync_all_peers(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for peer in self.peers.list_peers():
            try:
                pulled = self.pull_from_peer(peer)
                pushed = self.push_to_peer(peer)
                results.append({"peer_id": peer.peer_id, "pull": pulled, "push": pushed, "ok": True})
            except SymbolSyncError as exc:
                results.append({"peer_id": peer.peer_id, "ok": False, "error": str(exc)})
        return results
