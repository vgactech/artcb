"""Hashing utilities — SHA-256 (legacy chain) + SHA-3-256 (post-quantum friendly)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha3_256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha3_256(data).hexdigest()


def dual_hash_hex(data: bytes | str) -> dict[str, str]:
    """Return both hashes for migration / audit."""
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "sha3_256": hashlib.sha3_256(payload).hexdigest(),
    }
