"""Inspect an offered block the way an honest node must.

This is *not* PBFT. It answers: should this payload ever touch the tip?
259 = node absent. V-XX = node present and lying.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from src.artcb.crypto.hybrid import (
    ED25519_PREFIX,
    HYBRID_PREFIX,
    MLDSA65_PREFIX,
    verify_hybrid_and_or_window,
)

logger = logging.getLogger("artcb.consensus.byzantine_guard")


def signature_envelope_ok(signature: str) -> bool:
    sig = (signature or "").strip()
    if not sig:
        return False
    return sig.startswith((ED25519_PREFIX, HYBRID_PREFIX, MLDSA65_PREFIX))


def embedded_producer_keys(block: dict[str, Any]) -> tuple[bytes | None, bytes | None]:
    """Optional keys shipped *with* the offer (not in the consensus hash)."""
    ed_raw = (
        block.get("producer_ed25519_b64")
        or block.get("producer_pubkey")
        or block.get("public_key")
        or ""
    )
    pqc_raw = block.get("producer_pqc_b64") or block.get("pqc_public_key") or ""
    ed_bytes = _b64(str(ed_raw)) if ed_raw else None
    pqc_bytes = _b64(str(pqc_raw)) if pqc_raw else None
    return ed_bytes, pqc_bytes


def verify_offered_signature(block: dict[str, Any]) -> bool | None:
    """True / False when a producer key is embedded; None = not checkable."""
    sig = str(block.get("signature") or "")
    message = str(block.get("hash") or "").encode("utf-8")
    if not sig or not message:
        return False
    ed_pk, pqc_pk = embedded_producer_keys(block)
    if ed_pk is None:
        return None
    try:
        return verify_hybrid_and_or_window(
            message=message,
            signature_value=sig,
            ed25519_public_key=ed_pk,
            pqc_public_key=pqc_pk,
        )
    except Exception:
        logger.debug("offered signature verify raised", exc_info=True)
        return False


def _b64(value: str) -> bytes | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return base64.b64decode(raw, validate=False)
    except Exception:
        return None
