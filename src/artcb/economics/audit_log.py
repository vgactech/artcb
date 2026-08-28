"""Append-only binary audit log chained into AuditRoot (rapport 162)."""

from __future__ import annotations

import hashlib
import json
import logging
import struct
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("artcb.economics.audit_log")

MAGIC = b"ARTCBAUD1"


class AuditLog:
    """Length-prefixed records: magic | prev_hash | payload_json | event_hash."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_bytes(MAGIC)

    def last_hash(self) -> str:
        if self.path.stat().st_size <= len(MAGIC):
            return "0" * 64
        data = self.path.read_bytes()
        # walk records
        off = len(MAGIC)
        last = "0" * 64
        while off + 4 <= len(data):
            (n,) = struct.unpack_from(">I", data, off)
            off += 4
            rec = data[off : off + n]
            off += n
            last = hashlib.sha256(rec).hexdigest()
        return last

    def append(self, event_type: str, payload: dict) -> str:
        prev = self.last_hash()
        body = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": event_type,
            "payload": payload,
            "prev": prev,
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        event_hash = hashlib.sha256(prev.encode() + encoded).hexdigest()
        record = prev.encode() + b"\x00" + encoded + b"\x00" + event_hash.encode()
        with self.path.open("ab") as handle:
            handle.write(struct.pack(">I", len(record)))
            handle.write(record)
        logger.debug("audit append type=%s hash=%s", event_type, event_hash[:16])
        return event_hash

    def audit_root(self) -> str:
        return self.last_hash()

    def to_json_records(self) -> list[dict]:
        data = self.path.read_bytes()
        off = len(MAGIC)
        out: list[dict] = []
        while off + 4 <= len(data):
            (n,) = struct.unpack_from(">I", data, off)
            off += 4
            rec = data[off : off + n]
            off += n
            parts = rec.split(b"\x00")
            if len(parts) >= 3:
                try:
                    out.append(json.loads(parts[1].decode("utf-8")))
                except json.JSONDecodeError:
                    logger.error("corrupt audit record skipped")
        return out
