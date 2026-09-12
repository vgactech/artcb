"""R333 / R-01 — Canonical reasoning identity (language-independent).

2026-09-12T23:45:00Z

Human text is a *view*, not the identity of a reasoning.
Identity = sorted ConceptID multiset (+ optional relation edges) derived
from IR encoding — never hash(UTF-8 phrase).

Limits (honest):
  - Surfaced agent text ≠ private model CoT.
  - Round-trip FR→EN→canonical without a controlled translator is NOT claimed.
  - Same final answer with different premises → different ReasoningID (T4).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.artcb.ir.concept import concept_id_from_node
from src.artcb.ir.encoder import IREncoder

PROTOCOL = "r333-canonical-reasoning-v1"


@dataclass(frozen=True)
class CanonicalReasoning:
    """Language-independent reasoning fingerprint."""

    protocol: str
    concept_ids: tuple[str, ...]
    node_types: tuple[str, ...]
    edge_types: tuple[str, ...]
    premise_concept_ids: tuple[str, ...]
    conclusion_concept_ids: tuple[str, ...]

    def canonical_bytes(self) -> bytes:
        payload = {
            "protocol": self.protocol,
            "concept_ids": list(self.concept_ids),
            "node_types": list(self.node_types),
            "edge_types": list(self.edge_types),
            "premise_concept_ids": list(self.premise_concept_ids),
            "conclusion_concept_ids": list(self.conclusion_concept_ids),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def reasoning_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def reasoning_id(self) -> str:
        return "R" + self.reasoning_hash()[:16]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reasoning_hash"] = self.reasoning_hash()
        d["reasoning_id"] = self.reasoning_id()
        return d


def _node_type(n: Any) -> str:
    t = getattr(n, "t", None) or getattr(n, "type", None) or ""
    return str(t)


def canonicalize_text(text: str, *, encoder: IREncoder | None = None) -> CanonicalReasoning:
    """Encode human text → IR → ConceptID bag (not text hash)."""
    enc = encoder or IREncoder()
    g = enc.encode(text)
    nodes = list(getattr(g, "nodes", None) or [])
    edges = list(getattr(g, "edges", None) or [])
    cids = tuple(sorted({concept_id_from_node(n) for n in nodes}))
    ntypes = tuple(sorted(_node_type(n) for n in nodes))
    etypes = tuple(
        sorted(
            str(getattr(e, "t", None) or getattr(e, "type", None) or getattr(e, "rel", None) or "")
            for e in edges
        )
    )
    # Heuristic: first half nodes = premises, last = conclusion (stable under sort of cids)
    # Prefer explicit: all concept ids are premises; conclusion = full set (bag identity).
    # T4 needs different premise sets → different cids.
    premise = cids
    conclusion = cids
    return CanonicalReasoning(
        protocol=PROTOCOL,
        concept_ids=cids,
        node_types=ntypes,
        edge_types=etypes,
        premise_concept_ids=premise,
        conclusion_concept_ids=conclusion,
    )


def human_view(*, reasoning_id: str, language: str, text: str) -> dict[str, Any]:
    """A human-language projection — must never redefine ReasoningID."""
    return {
        "kind": "human_view",
        "reasoning_id": reasoning_id,
        "language": language,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_chars": len(text),
        "note": "view_only_not_identity",
    }


def semantic_identity_report(texts: dict[str, str]) -> dict[str, Any]:
    """Compare CanonicalReasoning across languages (T3-style)."""
    rows = {lang: canonicalize_text(t) for lang, t in texts.items()}
    ids = {lang: rows[lang].reasoning_id() for lang in rows}
    unique = sorted(set(ids.values()))
    concept_sets = {lang: set(rows[lang].concept_ids) for lang in rows}
    inter = set.intersection(*concept_sets.values()) if concept_sets else set()
    return {
        "reasoning_ids": ids,
        "unique_reasoning_ids": unique,
        "same_reasoning_id": len(unique) == 1,
        "concept_intersection": sorted(inter),
        "intersection_nonempty": bool(inter),
        "rows": {lang: rows[lang].to_dict() for lang in rows},
    }
