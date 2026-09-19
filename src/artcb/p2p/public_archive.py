"""Archive des blocs publics reçus via P2P (chaîne locale inchangée)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.p2p.public_archive")


class PublicBlockArchive:
    """Stocke les blocs publics distants — sans fusionner la chaîne locale."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "p2p" / "incoming_public.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self.path.write_text("", encoding="utf-8")

    def _read_all(self) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                blocks.append(json.loads(line))
        return blocks

    def list_blocks(self, *, from_index: int = 0) -> list[dict[str, Any]]:
        return [b for b in self._read_all() if int(b.get("origin_index", b.get("index", 0))) >= from_index]

    def store_blocks(self, blocks: list[dict[str, Any]], *, from_node_id: str) -> int:
        existing_hashes = {b.get("hash") for b in self._read_all()}
        stored = 0
        with self.path.open("a", encoding="utf-8") as handle:
            for block in blocks:
                if block.get("visibility") != "public":
                    continue
                h = block.get("hash")
                if h in existing_hashes:
                    continue
                entry = dict(block)
                entry["origin_index"] = block.get("index")
                entry["synced_from_node"] = from_node_id
                handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
                existing_hashes.add(h)
                stored += 1
        if stored:
            logger.info("Archived %d public blocks from %s", stored, from_node_id)
        return stored
