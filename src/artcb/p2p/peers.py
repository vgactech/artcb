"""P2P artcb-devnet — gestion des pairs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.p2p.peers")


@dataclass
class PeerRecord:
    peer_id: str
    host: str
    port: int
    kem_public_key_hex: str
    label: str = ""
    added_at: str = ""
    last_seen: str | None = None
    last_sync_ok: bool | None = None
    blocks_received: int = 0
    crypto_suite: str = ""

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "host": self.host,
            "port": self.port,
            "kem_public_key_hex": self.kem_public_key_hex,
            "label": self.label,
            "added_at": self.added_at,
            "last_seen": self.last_seen,
            "last_sync_ok": self.last_sync_ok,
            "blocks_received": self.blocks_received,
            "crypto_suite": self.crypto_suite,
            "base_url": self.base_url,
        }


class PeerManager:
    """Registre local des nœuds pairs artcb-devnet."""

    def __init__(self, data_dir: Path) -> None:
        self.store_path = Path(data_dir) / "p2p" / "peers.json"
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.is_file():
            self._write({"peers": []})

    def _read(self) -> dict:
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.store_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.store_path.chmod(0o600)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def list_peers(self) -> list[PeerRecord]:
        return [self._load(p) for p in self._read().get("peers", [])]

    def get_peer(self, peer_id: str) -> PeerRecord | None:
        for peer in self.list_peers():
            if peer.peer_id == peer_id:
                return peer
        return None

    def _load(self, item: dict) -> PeerRecord:
        return PeerRecord(
            peer_id=item["peer_id"],
            host=item["host"],
            port=int(item["port"]),
            kem_public_key_hex=item["kem_public_key_hex"],
            label=item.get("label", ""),
            added_at=item.get("added_at", ""),
            last_seen=item.get("last_seen"),
            last_sync_ok=item.get("last_sync_ok"),
            blocks_received=int(item.get("blocks_received", 0)),
            crypto_suite=str(item.get("crypto_suite") or ""),
        )

    def add_peer(
        self,
        *,
        host: str,
        port: int,
        kem_public_key_hex: str,
        label: str = "",
        peer_id: str | None = None,
        crypto_suite: str = "",
    ) -> PeerRecord:
        from src.artcb.crypto.pqc import pqc_available
        from src.artcb.crypto_policy import accept_peer_suite

        if len(kem_public_key_hex) < 32:
            raise ValueError("kem_public_key_hex invalide")
        pid = peer_id or f"peer_{host.replace('.', '_')}_{port}"
        previous = None
        for existing in self.list_peers():
            if existing.peer_id == pid:
                previous = existing.crypto_suite
                break
        ok, reason = accept_peer_suite(
            advertised=crypto_suite or None,
            previously_seen=previous,
            pqc_available_here=pqc_available(),
        )
        if not ok:
            raise ValueError(f"crypto_policy_reject:{reason}")
        now = self._now()
        raw = self._read()
        items = raw.get("peers", [])
        record = {
            "peer_id": pid,
            "host": host.strip(),
            "port": port,
            "kem_public_key_hex": kem_public_key_hex.strip(),
            "label": label,
            "added_at": now,
            "last_seen": None,
            "last_sync_ok": None,
            "blocks_received": 0,
            "crypto_suite": crypto_suite or reason,
        }
        items = [p for p in items if p["peer_id"] != pid]
        items.append(record)
        raw["peers"] = items
        self._write(raw)
        logger.info("Added P2P peer %s@%s:%d", pid, host, port)
        return self._load(record)

    def remove_peer(self, peer_id: str) -> bool:
        raw = self._read()
        before = len(raw.get("peers", []))
        raw["peers"] = [p for p in raw.get("peers", []) if p["peer_id"] != peer_id]
        if len(raw["peers"]) == before:
            return False
        self._write(raw)
        return True

    def update_peer_status(
        self,
        peer_id: str,
        *,
        last_sync_ok: bool | None = None,
        blocks_received_delta: int = 0,
    ) -> None:
        raw = self._read()
        for item in raw.get("peers", []):
            if item["peer_id"] == peer_id:
                item["last_seen"] = self._now()
                if last_sync_ok is not None:
                    item["last_sync_ok"] = last_sync_ok
                if blocks_received_delta:
                    item["blocks_received"] = int(item.get("blocks_received", 0)) + blocks_received_delta
                break
        self._write(raw)
