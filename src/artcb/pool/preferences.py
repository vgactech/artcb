"""Préférences utilisateur pool — persistance locale."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class PoolPreferences:
    use_distributed_pool: bool = False
    encrypt_transport: bool = True
    default_visibility: str = "private"
    default_group_id: str | None = None
    chunk_chars: int = 400
    auto_dispatch: bool = True
    auto_process_incoming: bool = True
    auto_finalize: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PoolPreferences:
        return cls(
            use_distributed_pool=bool(data.get("use_distributed_pool", False)),
            encrypt_transport=bool(data.get("encrypt_transport", True)),
            default_visibility=str(data.get("default_visibility", "private")),
            default_group_id=data.get("default_group_id"),
            chunk_chars=int(data.get("chunk_chars", 400)),
            auto_dispatch=bool(data.get("auto_dispatch", True)),
            auto_process_incoming=bool(data.get("auto_process_incoming", True)),
            auto_finalize=bool(data.get("auto_finalize", False)),
        )


class PoolPreferencesStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "pool" / "preferences.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> PoolPreferences:
        if not self.path.is_file():
            return PoolPreferences()
        return PoolPreferences.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, prefs: PoolPreferences) -> PoolPreferences:
        self.path.write_text(json.dumps(prefs.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        self.path.chmod(0o600)
        return prefs
