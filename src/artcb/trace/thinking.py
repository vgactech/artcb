"""Thinking states: model-CoT acquisition ≠ ARTCB visibility=private.

A. Model thinking = internal reasoning. Recordable only if the runtime
   actually gives it to the agent. Cursor does not inject it into this VM.
B. visibility=private = ARTCB confidentiality: store fully, no public/P2P body.

``thinking_recorded`` is an ambiguous alias. Prefer the five booleans.
It is True only when private storage AND byte-for-byte integrity both hold.
A private lane existing never sets it True.
"""

from __future__ import annotations

import hashlib
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


THINKING_STATE_KEYS: tuple[str, ...] = (
    "thinking_available_from_runtime",
    "thinking_received",
    "thinking_private_stored",
    "thinking_public_hash_recorded",
    "thinking_integrity_verified",
)

INTEGRITY_STAGES: tuple[str, ...] = ("raw", "payload", "received", "stored")


def empty_thinking_states(*, reason: str = "runtime_did_not_provide_thinking") -> dict[str, Any]:
    """Cursor-default: private lane exists, nothing was acquired."""
    return {
        "thinking_available_from_runtime": False,
        "thinking_received": False,
        "thinking_private_stored": False,
        "thinking_public_hash_recorded": False,
        "thinking_integrity_verified": False,
        "thinking_recorded": False,
        "acquisition": "NOT_PROVEN",
        "reason": reason,
        "inject_context": False,
        "visibility_lane": "private",
        "note": (
            "visibility=private is a confidentiality lane, not proof that "
            "model thinking arrived. acquisition ≠ storage."
        ),
    }


def derive_thinking_recorded(states: dict[str, Any]) -> bool:
    """Legacy alias. Never True just because a private memo slot exists."""
    return bool(states.get("thinking_private_stored") and states.get("thinking_integrity_verified"))


def thinking_states(
    *,
    available_from_runtime: bool = False,
    received: bool = False,
    private_stored: bool = False,
    public_hash_recorded: bool = False,
    integrity_verified: bool = False,
    reason: str = "",
    hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    out = empty_thinking_states(reason=reason or "unset")
    out["thinking_available_from_runtime"] = bool(available_from_runtime)
    out["thinking_received"] = bool(received)
    out["thinking_private_stored"] = bool(private_stored)
    out["thinking_public_hash_recorded"] = bool(public_hash_recorded)
    out["thinking_integrity_verified"] = bool(integrity_verified)
    out["thinking_recorded"] = derive_thinking_recorded(out)
    if not received:
        out["acquisition"] = "NOT_PROVEN"
    elif integrity_verified:
        out["acquisition"] = "RECEIVED_AND_INTEGRITY_VERIFIED"
    elif private_stored:
        out["acquisition"] = "RECEIVED_STORED_INTEGRITY_NOT_PROVEN"
    else:
        out["acquisition"] = "RECEIVED_NOT_STORED"
    if hashes:
        out["hashes"] = hashes
    return out


def verify_thinking_integrity_chain(
    *,
    raw: bytes | None = None,
    payload: bytes | None = None,
    received_sha256: str = "",
    stored_sha256: str = "",
) -> dict[str, Any]:
    """True only when SHA256(raw)==SHA256(payload)==received==stored.

    HTTP 200 is not integrity. Missing any stage → NOT_PROVEN.
    """
    hashes: dict[str, str] = {}
    if raw is not None:
        hashes["raw"] = sha256_bytes(raw)
    if payload is not None:
        hashes["payload"] = sha256_bytes(payload)
    recv = (received_sha256 or "").strip().lower()
    stored = (stored_sha256 or "").strip().lower()
    if recv:
        hashes["received"] = recv
    if stored:
        hashes["stored"] = stored
    missing = [name for name in INTEGRITY_STAGES if name not in hashes]
    if missing:
        return {
            "ok": False,
            "verified": False,
            "reason": "missing_stage",
            "missing": missing,
            "hashes": hashes,
        }
    values = set(hashes.values())
    if len(values) != 1:
        return {
            "ok": False,
            "verified": False,
            "reason": "hash_mismatch",
            "missing": [],
            "hashes": hashes,
        }
    return {
        "ok": True,
        "verified": True,
        "reason": "byte_for_byte",
        "missing": [],
        "hashes": hashes,
        "sha256": hashes["raw"],
    }
