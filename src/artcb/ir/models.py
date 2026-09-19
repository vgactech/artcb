"""Modèles de données IR ARTCB v0.1."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from src.artcb.ir.grammar import IR_VERSION


def sha256_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class IRNode(BaseModel):
    id: str
    t: str
    sym: str
    txt: str
    checksum: str
    start: int = 0
    end: int = 0
    vec: list[float] = Field(default_factory=list)


class IREdge(BaseModel):
    fr: str = Field(alias="from")
    to: str
    rel: str
    w: float = 1.0

    model_config = {"populate_by_name": True}


class IRMacro(BaseModel):
    expansion: list[str]
    sym: str


class IRGraph(BaseModel):
    v: str = IR_VERSION
    graph_id: str
    source_text: str
    nodes: list[IRNode]
    edges: list[IREdge]
    macros: dict[str, IRMacro] = Field(default_factory=dict)
    orig_symbols: dict[str, str] = Field(default_factory=dict)
    checksum: str
    join_sep: str = " "

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = {
            "v": self.v,
            "graph_id": self.graph_id,
            "source_text": self.source_text,
            "nodes": [n.model_dump() for n in self.nodes],
            "edges": [e.model_dump(by_alias=True) for e in self.edges],
            "macros": {k: v.model_dump() for k, v in self.macros.items()},
            "orig_symbols": self.orig_symbols,
            "checksum": self.checksum,
            "join_sep": self.join_sep,
        }
        return payload

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_canonical_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IRGraph:
        nodes = [IRNode(**n) for n in data["nodes"]]
        edges = []
        for e in data["edges"]:
            edges.append(IREdge(**e))
        macros = {k: IRMacro(**v) for k, v in data.get("macros", {}).items()}
        return cls(
            v=data.get("v", IR_VERSION),
            graph_id=data["graph_id"],
            source_text=data["source_text"],
            nodes=nodes,
            edges=edges,
            macros=macros,
            orig_symbols=data.get("orig_symbols", {}),
            checksum=data["checksum"],
            join_sep=data.get("join_sep", " "),
        )

    @classmethod
    def from_json(cls, raw: str) -> IRGraph:
        return cls.from_dict(json.loads(raw))

    def verify_integrity(self) -> bool:
        if self.checksum != sha256_text(self.source_text):
            return False
        return all(node.checksum == sha256_text(node.txt) for node in self.nodes)
