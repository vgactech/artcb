"""R333/R334 — Canonical reasoning identity (language-independent).

2026-09-12T23:45:00Z — initial R333 (~~set-dedup + premises=conclusion~~).
2026-09-13T00:15:00Z — R334-A: true ConceptID **multiset**, distinct
premises/conclusions, relation triples. Human text remains a *view*.

Limits (honest):
  - Surfaced agent text ≠ private model CoT.
  - Round-trip FR→EN→canonical without a controlled translator is NOT claimed.
  - Same final answer with different premises → different ReasoningID.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from src.artcb.ir.concept import concept_id_from_node
from src.artcb.ir.encoder import IREncoder
from src.artcb.ir.grammar import EdgeType, NodeType

# ~~PROTOCOL = "r333-canonical-reasoning-v1"~~ barred 2026-09-13T00:15:00Z (set bug)
PROTOCOL = "r334-canonical-reasoning-v2"

_CONCLUSION_TYPES = frozenset(
    {
        str(NodeType.DECISION),
        str(NodeType.GOAL),
        str(NodeType.PROOF),
        "D",
        "G",
        "P",
    }
)
_PREMISE_TYPES = frozenset(
    {
        str(NodeType.FACT),
        str(NodeType.EVENT),
        str(NodeType.HYPOTHESIS),
        str(NodeType.CONTEXT),
        str(NodeType.REASON),
        "F",
        "E",
        "H",
        "C",
        "R",
    }
)
_IMPLIES_RELS = frozenset(
    {
        str(EdgeType.IMPLIES),
        str(EdgeType.SUPPORTS),
        "⇒",
        "⊢",
        "implies",
        "supports",
    }
)


@dataclass(frozen=True)
class CanonicalReasoning:
    """Language-independent reasoning fingerprint (structural)."""

    protocol: str
    # Multisets: sorted tuples that may contain duplicate ConceptIDs
    concept_ids: tuple[str, ...]
    node_types: tuple[str, ...]
    edge_types: tuple[str, ...]
    premise_concept_ids: tuple[str, ...]
    conclusion_concept_ids: tuple[str, ...]
    # (from_cid, rel, to_cid) with multiplicity preserved via repeated triples
    relation_triples: tuple[tuple[str, str, str], ...] = ()

    def canonical_bytes(self) -> bytes:
        payload = {
            "protocol": self.protocol,
            "concept_ids": list(self.concept_ids),
            "node_types": list(self.node_types),
            "edge_types": list(self.edge_types),
            "premise_concept_ids": list(self.premise_concept_ids),
            "conclusion_concept_ids": list(self.conclusion_concept_ids),
            "relation_triples": [list(t) for t in self.relation_triples],
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


def _edge_rel(e: Any) -> str:
    return str(getattr(e, "rel", None) or getattr(e, "t", None) or getattr(e, "type", None) or "")


def _edge_ends(e: Any) -> tuple[str, str]:
    fr = str(getattr(e, "fr", None) or getattr(e, "from", None) or getattr(e, "from_", None) or "")
    to = str(getattr(e, "to", None) or "")
    return fr, to


def canonicalize_structured(
    *,
    premise_concept_ids: list[str] | tuple[str, ...],
    conclusion_concept_ids: list[str] | tuple[str, ...],
    relation_triples: list[tuple[str, str, str]] | tuple[tuple[str, str, str], ...] = (),
    node_types: list[str] | tuple[str, ...] = (),
    edge_types: list[str] | tuple[str, ...] = (),
) -> CanonicalReasoning:
    """Build identity from explicit structural parts (multiset-preserving)."""
    prem = tuple(sorted(str(x) for x in premise_concept_ids))
    conc = tuple(sorted(str(x) for x in conclusion_concept_ids))
    rels = tuple(sorted((str(a), str(b), str(c)) for a, b, c in relation_triples))
    # Full multiset = premises + conclusions (order-normalized via sort of concat)
    cids = tuple(sorted(list(prem) + list(conc)))
    ntypes = tuple(sorted(str(x) for x in node_types))
    etypes = tuple(sorted(str(x) for x in edge_types)) if edge_types else tuple(sorted({r[1] for r in rels}))
    return CanonicalReasoning(
        protocol=PROTOCOL,
        concept_ids=cids,
        node_types=ntypes,
        edge_types=etypes,
        premise_concept_ids=prem,
        conclusion_concept_ids=conc,
        relation_triples=rels,
    )


def canonicalize_text(text: str, *, encoder: IREncoder | None = None) -> CanonicalReasoning:
    """Encode human text → IR → structural CanonicalReasoning (not text hash)."""
    enc = encoder or IREncoder()
    g = enc.encode(text)
    nodes = list(getattr(g, "nodes", None) or [])
    edges = list(getattr(g, "edges", None) or [])

    # Multiset of ConceptIDs (duplicates preserved)
    cids_list = [concept_id_from_node(n) for n in nodes]
    id_to_cid = {str(getattr(n, "id", "") or ""): concept_id_from_node(n) for n in nodes}

    ntypes = [_node_type(n) for n in nodes]
    etypes = [_edge_rel(e) for e in edges]

    prem: list[str] = []
    conc: list[str] = []
    for n, cid in zip(nodes, cids_list, strict=False):
        t = _node_type(n)
        if t in _CONCLUSION_TYPES:
            conc.append(cid)
        elif t in _PREMISE_TYPES:
            prem.append(cid)
        else:
            prem.append(cid)

    rel_triples: list[tuple[str, str, str]] = []
    for e in edges:
        fr, to = _edge_ends(e)
        rel = _edge_rel(e)
        a = id_to_cid.get(fr, "")
        b = id_to_cid.get(to, "")
        if a and b and rel:
            rel_triples.append((a, rel, b))
            if rel in _IMPLIES_RELS:
                prem.append(a)
                conc.append(b)

    # If encoder produced no typed conclusions, treat last node as conclusion role
    if not conc and cids_list:
        conc = [cids_list[-1]]
        if prem and prem[-1] == conc[0] and len(prem) == len(cids_list):
            # avoid total collapse: premises = all but last when possible
            prem = cids_list[:-1] or list(cids_list)

    return canonicalize_structured(
        premise_concept_ids=prem,
        conclusion_concept_ids=conc,
        relation_triples=rel_triples,
        node_types=ntypes,
        edge_types=etypes,
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


def _multiset_intersection(*bags: tuple[str, ...]) -> list[str]:
    if not bags:
        return []
    acc = Counter(bags[0])
    for b in bags[1:]:
        acc &= Counter(b)
    out: list[str] = []
    for k in sorted(acc):
        out.extend([k] * acc[k])
    return out


def semantic_identity_report(texts: dict[str, str]) -> dict[str, Any]:
    """Compare CanonicalReasoning across languages (T3-style)."""
    rows = {lang: canonicalize_text(t) for lang, t in texts.items()}
    ids = {lang: rows[lang].reasoning_id() for lang in rows}
    unique = sorted(set(ids.values()))
    bags = [rows[lang].concept_ids for lang in rows]
    inter = _multiset_intersection(*bags) if bags else []
    return {
        "reasoning_ids": ids,
        "unique_reasoning_ids": unique,
        "same_reasoning_id": len(unique) == 1,
        "concept_intersection": inter,
        "intersection_nonempty": bool(inter),
        "protocol": PROTOCOL,
        "rows": {lang: rows[lang].to_dict() for lang in rows},
    }
