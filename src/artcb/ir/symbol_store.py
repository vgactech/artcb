"""Registre persistant des symboles originaux IA — data/symbols/registry.json."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.artcb.ir.symbols import SymbolRegistry

logger = logging.getLogger("artcb.ir.symbol_store")

DEFAULT_REGISTRY_PATH = "symbols/registry.json"


class PersistentSymbolRegistry:
    """SymbolRegistry avec persistance disque et fusion P2P."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / DEFAULT_REGISTRY_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._registry = SymbolRegistry()
        self._metadata: dict[str, Any] = {
            "version": 1,
            "updated_at": None,
            "merge_count": 0,
        }
        self._load()

    @property
    def registry(self) -> SymbolRegistry:
        return self._registry

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            mapping = data.get("concepts", data.get("symbols", {}))
            if isinstance(mapping, dict):
                self._registry = SymbolRegistry.from_export(mapping)
            meta = data.get("metadata", {})
            if isinstance(meta, dict):
                self._metadata.update(meta)
            logger.debug("Loaded symbol registry entries=%d", len(self._registry.export()))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load symbol registry: %s", exc)

    def save(self) -> None:
        self._metadata["updated_at"] = datetime.now(UTC).isoformat()
        payload = {
            "metadata": self._metadata,
            "concepts": self._registry.export(),
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("Saved symbol registry entries=%d", len(self._registry.export()))

    def mint_original(self, concept: str) -> str:
        symbol = self._registry.mint_original(concept)
        self.save()
        return symbol

    def export(self) -> dict[str, str]:
        return self._registry.export()

    def merge_remote(
        self,
        remote: dict[str, str],
        *,
        from_node_id: str = "unknown",
        block_index: int | None = None,
    ) -> int:
        """Fusionne des symboles distants — meme concept garde le symbole local."""
        merged = 0
        for key, remote_sym in remote.items():
            local_sym = self._registry._concept_to_symbol.get(key)
            if local_sym is None:
                self._registry._concept_to_symbol[key] = remote_sym
                merged += 1
        if merged:
            self._metadata["merge_count"] = int(self._metadata.get("merge_count", 0)) + merged
            self._metadata["last_merge_from"] = from_node_id
            if block_index is not None:
                self._metadata["last_merge_block"] = block_index
            self.save()
            logger.info("Merged %d symbols from %s", merged, from_node_id)
        return merged

    def publish_from_graph(self, orig_symbols: dict[str, str]) -> dict[str, str]:
        """Enregistre les symboles d'un graphe dans le registre local."""
        if not orig_symbols:
            return {}
        for key in orig_symbols:
            concept = key.split("|")[0] if "|" in key else key
            if key not in self._registry._concept_to_symbol:
                self._registry.mint_original(concept)
        self.save()
        return self.export()
