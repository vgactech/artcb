"""EconomicRoot — settlement commitment in the block hash (162 + 164).

Native path (preferred): C ``artcb_build_canonical_v2`` includes EconomicRoot
when ``hash_version=2``. Historic blocks without a root still hash with the
six-field v1 preimage.

Hybrid fallback: if the loaded ``libartcb_chain.so`` is pre-v2, Python mixes
EconomicRoot into the merkle argument (rapport 163 workaround) so tamper still
changes BlockHash.
"""

from __future__ import annotations

import hashlib
import json
import logging

logger = logging.getLogger("artcb.economics.economic_root")

HASH_VERSION_V1 = 1
HASH_VERSION_V2 = 2


def economic_root(parts: dict) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    logger.debug("EconomicRoot=%s keys=%s", digest[:16], sorted(parts))
    return digest


def mix_merkle_with_economic_root(merkle_root: str, eco_root: str) -> str:
    """Python-only fallback when C ABI v2 is unavailable."""
    material = f"{merkle_root}|{eco_root}".encode("utf-8")
    mixed = hashlib.sha256(material).hexdigest()
    logger.debug(
        "HYBRID mix merkle %s + eco %s -> %s (C v2 missing)",
        merkle_root[:12],
        eco_root[:12],
        mixed[:16],
    )
    return mixed


def native_economic_root_available() -> bool:
    from src.artcb.chain import ffi

    return ffi.has_economic_root_abi()
