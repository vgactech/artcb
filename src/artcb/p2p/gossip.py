"""Gossip devnet artcb — couche compatible port 18444 (transport HTTP)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.artcb.crypto_policy import NETWORK_ID

logger = logging.getLogger("artcb.p2p.gossip")

GOSSIP_MAGIC = "0xARTC0001"


class GossipRegistry:
    """
    Registre gossip local — annonces de pairs et symboles.
    Transport reel : endpoints REST /api/v1/p2p/gossip/* (port API).
    Port P2P documente 18444 = identifiant reseau devnet (node_identity.p2p_port).
    """

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "p2p" / "gossip_registry.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._entries = list(data.get("announcements", []))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Gossip registry load failed: %s", exc)

    def _save(self) -> None:
        payload = {
            "network_id": NETWORK_ID,
            "magic": GOSSIP_MAGIC,
            "announcements": self._entries[-500:],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def announce(
        self,
        *,
        node_id: str,
        host: str,
        api_port: int,
        p2p_port: int,
        kem_public_key_hex: str,
        symbol_count: int = 0,
    ) -> dict[str, Any]:
        entry = {
            "node_id": node_id,
            "host": host,
            "api_port": api_port,
            "p2p_port": p2p_port,
            "kem_public_key_hex": kem_public_key_hex,
            "symbol_count": symbol_count,
            "network_id": NETWORK_ID,
            "magic": GOSSIP_MAGIC,
            "ts": datetime.now(UTC).isoformat(),
        }
        self._entries = [e for e in self._entries if e.get("node_id") != node_id]
        self._entries.append(entry)
        self._save()
        return entry

    def list_announcements(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def merge_remote_announcement(self, entry: dict[str, Any]) -> bool:
        node_id = entry.get("node_id")
        if not node_id:
            return False
        self._entries = [e for e in self._entries if e.get("node_id") != node_id]
        self._entries.append(entry)
        self._save()
        return True
