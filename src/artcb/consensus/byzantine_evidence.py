"""Persistent evidence of active-Byzantine *offers* — not a PBFT view-change.

259 demonstrated honest-offline catch-up. This store records what a live
peer *sent* that honest nodes refused: bad hash, bad signature, two
different payloads at the same index.

It does not rewrite blocks.jsonl. It does not certify BFT append.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.artcb.trace.ns import now_wall_ns

logger = logging.getLogger("artcb.consensus.byzantine_evidence")

EVIDENCE_REL = Path("consensus") / "byzantine_evidence.jsonl"
# only these are "the peer lied" — wrong_index/prev happen on honest catch-up
FRAUD_KINDS = frozenset(
    {
        "invalid_signature",
        "hash_mismatch",
        "equivocation",
        "invalid_block",
    }
)


@dataclass(frozen=True)
class ByzantineEvidence:
    kind: str
    reason: str
    from_node_id: str
    index: int | None
    hash_offered: str
    hash_held: str
    ts: str
    ts_ns: int
    not_block_append_bft: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceStore:
    """Append-only JSONL under data/consensus/. Never touches the book."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / EVIDENCE_REL
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        kind: str,
        reason: str,
        from_node_id: str = "unknown",
        index: int | None = None,
        hash_offered: str = "",
        hash_held: str = "",
    ) -> ByzantineEvidence:
        row = ByzantineEvidence(
            kind=kind,
            reason=reason,
            from_node_id=from_node_id or "unknown",
            index=index,
            hash_offered=hash_offered or "",
            hash_held=hash_held or "",
            ts=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ts_ns=now_wall_ns(),
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
        if kind in FRAUD_KINDS and from_node_id and from_node_id != "unknown":
            try:
                from src.artcb.p2p.node_reputation import ReputationLedger

                ReputationLedger(self.data_dir).record_fraud(from_node_id)
            except Exception:
                logger.debug("reputation fraud skip", exc_info=True)
        return row

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        cap = max(1, min(int(limit or 100), 2000))
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[-cap:]:
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                out.append(parsed)
        return out

    def summary(self) -> dict[str, Any]:
        rows = self.list(limit=2000)
        by_kind: dict[str, int] = {}
        by_node: dict[str, int] = {}
        for row in rows:
            kind = str(row.get("kind") or "unknown")
            node = str(row.get("from_node_id") or "unknown")
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_node[node] = by_node.get(node, 0) + 1
        sha = ""
        nbytes = 0
        if self.path.is_file():
            raw = self.path.read_bytes()
            nbytes = len(raw)
            sha = hashlib.sha256(raw).hexdigest()
        return {
            "count": len(rows),
            "by_kind": by_kind,
            "by_node": by_node,
            "path": str(self.path),
            "sha256": sha,
            "bytes": nbytes,
            "persistent": self.path.is_file(),
            "signed_on_chain": False,
            "not_block_append_bft": True,
            "scope": "active_byzantine_offer_evidence",
        }


def store_for_chain(blocks_path: Path) -> EvidenceStore:
    return EvidenceStore(Path(blocks_path).parent.parent)


def record_reject(
    blocks_path: Path,
    *,
    reason: str,
    block: dict[str, Any] | None = None,
    from_node_id: str = "unknown",
    hash_held: str = "",
) -> None:
    block = block or {}
    kind = reason if reason in FRAUD_KINDS else "invalid_block"
    try:
        idx = int(block["index"]) if block.get("index") is not None else None
    except (TypeError, ValueError):
        idx = None
    store_for_chain(blocks_path).record(
        kind=kind,
        reason=reason,
        from_node_id=from_node_id,
        index=idx,
        hash_offered=str(block.get("hash") or ""),
        hash_held=hash_held,
    )
