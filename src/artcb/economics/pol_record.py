"""Native PoL record — rapport 162. LLM tokens are a cost, not a proof."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field

logger = logging.getLogger("artcb.economics.pol_record")

POL_VERSION = 1


@dataclass
class PoLRecord:
    pol_version: int = POL_VERSION
    job_id: str = ""
    work_id: str = ""
    parent_work_root: str = ""
    input_commitment: str = ""
    execution_proof: str = ""
    output_commitment: str = ""
    validation_proof: str = ""
    useful_work_score: float = 0.0
    contribution_score: float = 0.0
    capacity_metrics: dict = field(default_factory=dict)
    worker_id: str = ""
    provider_id: str = ""
    settlement_reference: str = ""
    llm_token_count: int = 0  # cost only

    def to_dict(self) -> dict:
        return asdict(self)

    def digest(self) -> str:
        payload = self.to_dict()
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        logger.debug("PoLRecord work=%s digest=%s tokens_ignored_as_proof=%s", self.work_id, digest[:16], self.llm_token_count)
        return digest


def pol_merkle_root(records: list[PoLRecord]) -> str:
    digests = [rec.digest() for rec in records]
    material = "".join(digests).encode("utf-8")
    return hashlib.sha256(material).hexdigest() if digests else "0" * 64
