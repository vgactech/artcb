"""Compression macro récursive (Φ, Ψ, Ω…) — ARTCB v0.1."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

from collections import Counter

from src.artcb.ir.grammar import EdgeType, NodeType
from src.artcb.ir.models import IREdge, IRGraph, IRMacro, IRNode, sha256_text

MACRO_SYMBOLS = ["Ω", "Φ", "Ψ", "Γ", "Δ", "Σ", "Π"]
MIN_PATTERN_OCCURRENCES = 3
MIN_PATTERN_LENGTH = 2


def detect_macros(graph: IRGraph) -> dict[str, IRMacro]:
    """Crée des macros si une séquence de symboles se répète au moins 3 fois."""
    content_nodes = [n for n in graph.nodes if n.t != NodeType.MACRO.value]
    if len(content_nodes) < MIN_PATTERN_LENGTH * MIN_PATTERN_OCCURRENCES:
        return {}

    sym_list = [n.sym for n in content_nodes]
    pattern_counts: Counter[tuple[str, ...]] = Counter()

    max_len = min(6, len(sym_list) // MIN_PATTERN_OCCURRENCES + 1)
    for length in range(MIN_PATTERN_LENGTH, max_len + 1):
        for i in range(len(sym_list) - length + 1):
            pattern = tuple(sym_list[i : i + length])
            pattern_counts[pattern] += 1

    macros: dict[str, IRMacro] = {}
    macro_index = 1

    for pattern, count in sorted(pattern_counts.items(), key=lambda x: (-x[1], -len(x[0]))):
        if count < MIN_PATTERN_OCCURRENCES:
            continue
        symbol = f"{MACRO_SYMBOLS[(macro_index - 1) % len(MACRO_SYMBOLS)]}{macro_index}"
        combined_sym = "".join(pattern)
        expansion: list[str] = []
        for i in range(len(content_nodes) - len(pattern) + 1):
            window = [content_nodes[i + j].sym for j in range(len(pattern))]
            if window == list(pattern):
                expansion = [content_nodes[i + j].id for j in range(len(pattern))]
                break
        if not expansion:
            continue
        macros[symbol] = IRMacro(expansion=expansion, sym=combined_sym)
        macro_index += 1
        if macro_index > len(MACRO_SYMBOLS):
            break

    return macros


def apply_macros_to_graph(graph: IRGraph) -> IRGraph:
    """Ajoute les macros détectées sans supprimer les nœuds (réversibilité conservée)."""
    macros = detect_macros(graph)
    if not macros:
        return graph

    updated = graph.model_copy(deep=True)
    updated.macros = macros
    new_edges = list(updated.edges)

    for name, macro in macros.items():
        macro_node_id = f"m_{name}"
        updated.nodes.append(
            IRNode(
                id=macro_node_id,
                t=NodeType.MACRO.value,
                sym=name,
                txt=f"MACRO:{name}={macro.sym}",
                checksum=sha256_text(f"MACRO:{name}={macro.sym}"),
            )
        )
        for node_id in macro.expansion:
            new_edges.append(
                IREdge(
                    **{
                        "from": macro_node_id,
                        "to": node_id,
                        "rel": EdgeType.COMPRESSES.value,
                        "w": 1.0,
                    }
                )
            )

    updated.edges = new_edges
    return updated
