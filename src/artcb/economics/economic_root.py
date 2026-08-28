"""EconomicRoot — settlement commitment mixed into the block hash (162).

C ``build_block_hash`` is unchanged (no libartcb ABI fork). Python mixes
``EconomicRoot`` into the merkle argument so any settlement edit changes
BlockHash. Existing blocks without economics keep the historic C hash.
"""

from __future__ import annotations

import hashlib
import json
import logging

logger = logging.getLogger("artcb.economics.economic_root")


def economic_root(parts: dict) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    logger.debug("EconomicRoot=%s keys=%s", digest[:16], sorted(parts))
    return digest


def mix_merkle_with_economic_root(merkle_root: str, eco_root: str) -> str:
    material = f"{merkle_root}|{eco_root}".encode("utf-8")
    mixed = hashlib.sha256(material).hexdigest()
    logger.debug("mixed merkle %s + eco %s -> %s", merkle_root[:12], eco_root[:12], mixed[:16])
    return mixed
