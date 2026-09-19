"""Archive P2P des symboles publics recus."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.p2p.symbol_archive")


class PublicSymbolArchive:
    """Stocke les publications de symboles depuis blocs publics distants."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "p2p" / "incoming_symbols.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self.path.write_text("", encoding="utf-8")

    def _read_all(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        return entries

    def store_entry(
        self,
        symbols: dict[str, str],
        *,
        from_node_id: str,
        block_index: int | None = None,
        graph_id: str | None = None,
    ) -> bool:
        if not symbols:
            return False
        entry = {
            "symbols": symbols,
            "from_node_id": from_node_id,
            "block_index": block_index,
            "graph_id": graph_id,
        }
        existing = {
            (e.get("from_node_id"), e.get("block_index"), e.get("graph_id"))
            for e in self._read_all()
        }
        key = (from_node_id, block_index, graph_id)
        if key in existing:
            return False
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        logger.info("Archived %d symbols from %s", len(symbols), from_node_id)
        return True

    def list_entries(self) -> list[dict[str, Any]]:
        return self._read_all()

    def all_symbols(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for entry in self._read_all():
            for k, v in entry.get("symbols", {}).items():
                merged.setdefault(k, v)
        return merged
