"""Sidecar binary log for NEW blocks — never rewrites blocks.jsonl.

Rapport 253: JSON remains the canonical historical book. A transition
era may add binary without mutating committed lines.

Format (append-only):
  file header (once): magic ABLK (4) + version u8 + reserved 3
  record: u32le payload_len + payload (UTF-8 JSON, compact)

Readers that do not understand ABLK ignore the file. verify() still
uses blocks.jsonl. This is a write-ahead compact copy for streaming.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, Iterator

MAGIC = b"ABLK"
VERSION = 1
HEADER = MAGIC + bytes([VERSION, 0, 0, 0])
_LEN = struct.Struct("<I")


def log_path(blocks_path: Path) -> Path:
    return Path(blocks_path).with_name("blocks.bin")


def ensure_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size >= len(HEADER):
        return
    path.write_bytes(HEADER)


def append_record(blocks_path: Path, block: dict[str, Any]) -> int:
    """Append one block. Returns bytes written (header excluded)."""
    path = log_path(blocks_path)
    ensure_header(path)
    payload = json.dumps(block, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    blob = _LEN.pack(len(payload)) + payload
    with path.open("ab") as handle:
        handle.write(blob)
    return len(blob)


def iter_records(blocks_path: Path, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
    path = log_path(blocks_path)
    if not path.is_file():
        return
    yielded = 0
    with path.open("rb") as handle:
        head = handle.read(len(HEADER))
        if head[:4] != MAGIC:
            return
        while True:
            raw_len = handle.read(_LEN.size)
            if len(raw_len) < _LEN.size:
                break
            n = _LEN.unpack(raw_len)[0]
            if n > 8_000_000:
                break
            payload = handle.read(n)
            if len(payload) < n:
                break
            try:
                row = json.loads(payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(row, dict):
                yield row
                yielded += 1
                if limit is not None and yielded >= limit:
                    return


def record_count(blocks_path: Path) -> int:
    return sum(1 for _ in iter_records(blocks_path))
