"""Byte-offset index over blocks.jsonl — O(1) tip / height / get_block.

Rapport 256: never scan the whole book to answer a read. Stream lines,
keep offsets, read one record. Rebuilds if the jsonl size drifted.

Nanosecond traces on rebuild / targeted read / ranged scan (operator GO:
latency is the measurement, not a reason to skip a log).
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, Iterator

_OFF = struct.Struct("<Q")


def _data_dir(blocks_path: Path) -> Path:
    # data/chain/blocks.jsonl → data
    return Path(blocks_path).parent.parent


def _emit(blocks_path: Path, row: dict[str, Any]) -> None:
    try:
        from src.artcb.trace.ns import emit

        emit(_data_dir(blocks_path), row)
    except Exception:
        return


class BookIndex:
    def __init__(self, blocks_path: Path) -> None:
        self.blocks_path = Path(blocks_path)
        self.off_path = self.blocks_path.with_name(self.blocks_path.name + ".off")
        self.meta_path = self.blocks_path.with_name(self.blocks_path.name + ".off.meta")
        self._offsets: list[int] = []
        self._graph_index: dict[str, int] = {}
        self._meta: dict[str, Any] = {}
        self._issued_satoshi = 0
        self._recent_ts: list[str] = []
        self.ensure()

    def ensure(self) -> None:
        size = self.blocks_path.stat().st_size if self.blocks_path.is_file() else 0
        if (
            self._offsets
            and self._meta.get("size") == size
            and len(self._offsets) == int(self._meta.get("count") or 0)
        ):
            return
        meta = self._load_meta()
        if meta.get("size") == size and self.off_path.is_file() and size > 0:
            raw = self.off_path.read_bytes()
            offsets = [_OFF.unpack_from(raw, i)[0] for i in range(0, len(raw), _OFF.size)]
            if len(offsets) == int(meta.get("count") or 0):
                self._offsets = offsets
                self._graph_index = {str(k): int(v) for k, v in (meta.get("graphs") or {}).items()}
                self._meta = meta
                self._issued_satoshi = int(meta.get("issued_satoshi") or 0)
                self._recent_ts = [str(t) for t in (meta.get("recent_ts") or [])][-13:]
                return
        self.rebuild()

    def rebuild(self) -> None:
        from src.artcb.trace.ns import now_mono_ns

        t0 = now_mono_ns()
        self._offsets = []
        self._graph_index = {}
        self._issued_satoshi = 0
        self._recent_ts = []
        last: dict[str, Any] = {}
        if self.blocks_path.is_file():
            with self.blocks_path.open("rb") as handle:
                while True:
                    pos = handle.tell()
                    raw = handle.readline()
                    if not raw:
                        break
                    line = raw.strip()
                    if not line:
                        continue
                    self._offsets.append(pos)
                    try:
                        row = json.loads(line.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if not isinstance(row, dict):
                        continue
                    last = row
                    gid = str(row.get("graph_id") or "")
                    if gid and gid not in self._graph_index:
                        self._graph_index[gid] = int(row.get("index") or len(self._offsets) - 1)
                    self._issued_satoshi += int(row.get("block_reward") or 0)
                    ts = row.get("timestamp")
                    if ts:
                        self._recent_ts.append(str(ts))
                        self._recent_ts = self._recent_ts[-13:]
        self._persist(last)
        _emit(
            self.blocks_path,
            {
                "kind": "book_rebuild",
                "count": len(self._offsets),
                "size": self._meta.get("size"),
                "dur_ns": now_mono_ns() - t0,
                "ok": True,
            },
        )

    def _load_meta(self) -> dict[str, Any]:
        if not self.meta_path.is_file():
            return {}
        try:
            parsed = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _persist(self, last: dict[str, Any]) -> None:
        self.off_path.parent.mkdir(parents=True, exist_ok=True)
        self.off_path.write_bytes(b"".join(_OFF.pack(o) for o in self._offsets))
        size = self.blocks_path.stat().st_size if self.blocks_path.is_file() else 0
        self._meta = {
            "size": size,
            "count": len(self._offsets),
            "last_hash": last.get("hash"),
            "last_index": last.get("index"),
            "last_timestamp": last.get("timestamp"),
            "issued_satoshi": self._issued_satoshi,
            "recent_ts": self._recent_ts[-13:],
            "graphs": self._graph_index,
        }
        self.meta_path.write_text(json.dumps(self._meta, ensure_ascii=False), encoding="utf-8")

    def height(self) -> int:
        return len(self._offsets)

    def issued_satoshi(self) -> int:
        return int(self._issued_satoshi)

    def recent_timestamps(self, n: int = 13) -> list[str]:
        return list(self._recent_ts[-max(0, int(n)) :])

    def tip(self) -> dict[str, Any]:
        if not self._offsets:
            return {"height": 0, "last_hash": "0" * 64, "last_index": -1, "last_timestamp": None}
        last = self.read_index(len(self._offsets) - 1) or {}
        return {
            "height": len(self._offsets),
            "last_hash": last.get("hash") or "0" * 64,
            "last_index": last.get("index", len(self._offsets) - 1),
            "last_timestamp": last.get("timestamp"),
        }

    def read_index(self, index: int) -> dict[str, Any] | None:
        from src.artcb.trace.ns import now_mono_ns

        t0 = now_mono_ns()
        if index < 0 or index >= len(self._offsets):
            _emit(
                self.blocks_path,
                {
                    "kind": "book_get",
                    "index": index,
                    "hit": False,
                    "dur_ns": now_mono_ns() - t0,
                    "ok": False,
                },
            )
            return None
        with self.blocks_path.open("rb") as handle:
            handle.seek(self._offsets[index])
            raw = handle.readline()
        try:
            row = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            row = None
        rec = row if isinstance(row, dict) else None
        _emit(
            self.blocks_path,
            {
                "kind": "book_get",
                "index": index,
                "hit": rec is not None,
                "dur_ns": now_mono_ns() - t0,
                "ok": rec is not None,
            },
        )
        return rec

    def get_block(self, index: int) -> dict[str, Any] | None:
        return self.read_index(index)

    def block_index_for_graph(self, graph_id: str) -> int | None:
        if graph_id in self._graph_index:
            return self._graph_index[graph_id]
        return None

    def iter_blocks(self, *, from_index: int = 0, limit: int | None = None) -> Iterator[dict[str, Any]]:
        from src.artcb.trace.ns import now_mono_ns

        t0 = now_mono_ns()
        start = max(0, int(from_index or 0))
        end = len(self._offsets) if limit is None else min(len(self._offsets), start + max(0, int(limit)))
        yielded = 0
        if start >= end or not self.blocks_path.is_file():
            _emit(
                self.blocks_path,
                {
                    "kind": "book_iter",
                    "from_index": start,
                    "limit": limit,
                    "count": 0,
                    "dur_ns": now_mono_ns() - t0,
                    "ok": True,
                },
            )
            return
        with self.blocks_path.open("rb") as handle:
            for i in range(start, end):
                handle.seek(self._offsets[i])
                raw = handle.readline()
                try:
                    row = json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if isinstance(row, dict):
                    yielded += 1
                    yield row
        _emit(
            self.blocks_path,
            {
                "kind": "book_iter",
                "from_index": start,
                "limit": limit,
                "count": yielded,
                "dur_ns": now_mono_ns() - t0,
                "ok": True,
            },
        )

    def note_appended(self, line: str, block: dict[str, Any]) -> None:
        from src.artcb.trace.ns import now_mono_ns

        t0 = now_mono_ns()
        offset = (self.blocks_path.stat().st_size if self.blocks_path.is_file() else 0) - (
            len(line.encode("utf-8")) + 1
        )
        if offset < 0:
            self.rebuild()
            return
        self._offsets.append(offset)
        gid = str(block.get("graph_id") or "")
        if gid and gid not in self._graph_index:
            self._graph_index[gid] = int(block.get("index") or len(self._offsets) - 1)
        self._issued_satoshi += int(block.get("block_reward") or 0)
        ts = block.get("timestamp")
        if ts:
            self._recent_ts.append(str(ts))
            self._recent_ts = self._recent_ts[-13:]
        self._persist(block)
        _emit(
            self.blocks_path,
            {
                "kind": "book_index_append",
                "index": block.get("index"),
                "offset": offset,
                "dur_ns": now_mono_ns() - t0,
                "ok": True,
            },
        )
