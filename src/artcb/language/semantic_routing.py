"""R492 — ARTCB Semantic Routing — routage sémantique optimal dans le graphe.

Brique finale du langage ARTCB (R486 ordre expert) :

  R492 : TSP / Semantic Routing — trouver le chemin sémantique optimal
         dans l'espace des ConceptIDs, avec contrainte de fidelité minimale.

Problème résolu :
    Étant donné :
    - Un texte source (converti en ConceptID via R488 Lineage)
    - Un ConceptID cible
    - Un graphe de relations sémantiques entre concepts ARTCB
    - Des coûts de traversée (latence, mémoire, IR size)
    - Une contrainte : semantic_fidelity ≥ FIDELITY_MIN_THRESHOLD

    Trouver le chemin de moindre coût total qui :
    1. Relie le concept source au concept cible
    2. Maintient la fidelité sémantique ≥ seuil à chaque étape
    3. Minimise le coût multi-objectifs (en utilisant les scores Pareto de R490)

Architecture :
    ┌──────────────────────────────────────────────────────┐
    │  SemanticRouter                                      │
    │                                                      │
    │  build_graph(concepts)                               │
    │    → SemanticGraph (adjacence ConceptID → ConceptID) │
    │                                                      │
    │  route(source_concept, target_concept)               │
    │    → SemanticRoute : chemin + coût + fidelité        │
    │    → Algorithme : Dijkstra pondéré multi-objectifs   │
    └──────────────────────────────────────────────────────┘

Indépendance linguistique :
    Le routage opère dans l'espace des ConceptIDs — pas dans l'espace
    des textes en langue naturelle. C'est cohérent avec R486 :
    "les 16 langues sont des interfaces vers 1 sémantique canonique".

    Un chemin A→B→C dans le graphe sémantique est IDENTIQUE quel que soit
    la langue d'entrée (FR, EN, JA, AR...) — seule la traduction vers
    la langue cible change.

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R492

import hashlib
import heapq
import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.language.semantic_routing")

DEBUG_MODE = True  # PROTOCOLE ARTCB — mode DEBUG permanent

# Invariants absolus
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False

# Seuil de fidelité minimale sur chaque arc du chemin
FIDELITY_MIN_THRESHOLD = 0.0  # 0 = toutes les transitions autorisées
# En production, mettre à 0.5 ou 0.8 selon les exigences


# ─── Nœud et arc du graphe sémantique ────────────────────────────────────────

@dataclass
class SemanticNode:
    """Nœud dans le graphe sémantique ARTCB.

    Correspond à un ConceptID (K{sha256[:12]}) ou un artcb_code (V1, K1...).
    """

    concept_id: str         # ex: K45438c1fb97f
    artcb_code: str         # ex: V1
    category: str           # ACTION | OBJECT | MODIFIER | UNKNOWN
    label: str = ""         # forme canonique en anglais
    fidelity: float = 1.0   # fidelité associée à ce nœud

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "artcb_code": self.artcb_code,
            "category": self.category,
            "label": self.label,
            "fidelity": self.fidelity,
        }


@dataclass
class SemanticEdge:
    """Arc orienté entre deux nœuds sémantiques.

    Le coût est multi-dimensionnel (en accord avec R490 Pareto).
    """

    source_id: str           # concept_id source
    target_id: str           # concept_id cible
    relation: str = "RELATED"  # type de relation sémantique
    cost_latency: float = 1.0   # coût en latence (ms normalisé)
    cost_memory: float = 1.0    # coût en mémoire (bytes normalisé)
    cost_ir: float = 1.0        # coût IR size (chars normalisé)
    fidelity: float = 1.0       # fidelité de la transition

    @property
    def total_cost(self) -> float:
        """Coût total pondéré de l'arc.

        Fidelité sémantique a un poids 3× (cohérent avec R490 FIDELITY_WEIGHT).
        """
        fidelity_penalty = (1.0 - self.fidelity) * 3.0  # pénalité si perte fidelité
        return self.cost_latency + self.cost_memory + self.cost_ir + fidelity_penalty

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "cost_latency": self.cost_latency,
            "cost_memory": self.cost_memory,
            "cost_ir": self.cost_ir,
            "fidelity": self.fidelity,
            "total_cost": self.total_cost,
        }


# ─── Graphe sémantique ────────────────────────────────────────────────────────

@dataclass
class SemanticGraph:
    """Graphe de relations sémantiques entre ConceptIDs ARTCB.

    Construit depuis le corpus sémantique (SemanticCorpus de R486).
    Les arcs représentent des relations entre concepts (RELATED, IMPLIES,
    SUBTYPE, CONTEXT...).
    """

    nodes: dict[str, SemanticNode] = field(default_factory=dict)  # concept_id → nœud
    edges: dict[str, list[SemanticEdge]] = field(default_factory=dict)  # source_id → arcs

    def add_node(self, node: SemanticNode) -> None:
        self.nodes[node.concept_id] = node
        if node.concept_id not in self.edges:
            self.edges[node.concept_id] = []

    def add_edge(self, edge: SemanticEdge) -> None:
        if edge.source_id not in self.edges:
            self.edges[edge.source_id] = []
        self.edges[edge.source_id].append(edge)

    def neighbors(self, concept_id: str) -> list[SemanticEdge]:
        """Retourne les arcs sortants depuis un nœud."""
        return self.edges.get(concept_id, [])

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return sum(len(edges) for edges in self.edges.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count(),
            "edge_count": self.edge_count(),
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
        }


# ─── Résultat du routage ──────────────────────────────────────────────────────

@dataclass
class SemanticRoute:
    """Résultat du routage sémantique (chemin optimal).

    Contient le chemin (séquence de ConceptIDs), le coût total,
    la fidelité minimale sur le chemin, et le statut.
    """

    source_id: str
    target_id: str
    path: list[str] = field(default_factory=list)   # ConceptIDs du chemin
    edges: list[SemanticEdge] = field(default_factory=list)
    total_cost: float = float("inf")
    min_fidelity: float = 0.0
    found: bool = False
    algorithm: str = "dijkstra_weighted"
    computation_ms: float = 0.0

    # Méta
    source_lang: str = ""
    target_lang: str = ""
    source_text: str = ""

    # Invariants
    unique_human_proven: bool = False
    certified: bool = False

    def path_length(self) -> int:
        """Nombre d'arcs dans le chemin."""
        return len(self.edges)

    def explain(self) -> str:
        if not self.found:
            return f"Aucun chemin trouvé de {self.source_id!r} → {self.target_id!r}"
        steps = " → ".join(self.path)
        return (
            f"Chemin [{self.source_lang or '?'}→{self.target_lang or '?'}]: "
            f"{steps} "
            f"(coût={self.total_cost:.3f}, fidelité_min={self.min_fidelity:.3f}, "
            f"arcs={self.path_length()})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "path": self.path,
            "total_cost": round(self.total_cost, 6) if math.isfinite(self.total_cost) else None,
            "min_fidelity": round(self.min_fidelity, 6),
            "found": self.found,
            "path_length": self.path_length(),
            "algorithm": self.algorithm,
            "computation_ms": round(self.computation_ms, 3),
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "source_text": self.source_text,
            "unique_human_proven": self.unique_human_proven,
            "certified": self.certified,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ─── Construction du graphe depuis le corpus ──────────────────────────────────

def build_graph_from_corpus(semantic_corpus=None) -> SemanticGraph:
    """Construit un SemanticGraph depuis le SemanticCorpus de R486.

    Les arcs sont générés automatiquement entre concepts de même catégorie
    (RELATED) et entre catégories (ACTION→OBJECT : OPERATES_ON).

    Args:
        semantic_corpus: instance SemanticCorpus (créée si None).

    Returns:
        SemanticGraph avec nœuds + arcs.
    """
    from src.artcb.language.adapter import SemanticCorpus  # noqa: PLC0415

    if semantic_corpus is None:
        semantic_corpus = SemanticCorpus()

    graph = SemanticGraph()

    # Ajouter les nœuds depuis le corpus
    for code, concept in semantic_corpus._concepts.items():
        cid = semantic_corpus.get_concept_id(code)
        node = SemanticNode(
            concept_id=cid,
            artcb_code=code,
            category=concept.category,
            label=concept.canonical_form,
            fidelity=1.0,
        )
        graph.add_node(node)

    # Générer les arcs : relations sémantiques entre concepts
    all_nodes = list(graph.nodes.values())

    for i, source in enumerate(all_nodes):
        for j, target in enumerate(all_nodes):
            if source.concept_id == target.concept_id:
                continue

            # Même catégorie → RELATED (coût faible)
            if source.category == target.category:
                edge = SemanticEdge(
                    source_id=source.concept_id,
                    target_id=target.concept_id,
                    relation="RELATED",
                    cost_latency=1.0,
                    cost_memory=1.0,
                    cost_ir=1.0,
                    fidelity=0.9,
                )
                graph.add_edge(edge)

            # ACTION → OBJECT : OPERATES_ON (coût moyen)
            elif source.category == "ACTION" and target.category == "OBJECT":
                edge = SemanticEdge(
                    source_id=source.concept_id,
                    target_id=target.concept_id,
                    relation="OPERATES_ON",
                    cost_latency=1.5,
                    cost_memory=1.5,
                    cost_ir=1.5,
                    fidelity=0.8,
                )
                graph.add_edge(edge)

            # OBJECT → MODIFIER : HAS_PROPERTY (coût élevé)
            elif source.category == "OBJECT" and target.category == "MODIFIER":
                edge = SemanticEdge(
                    source_id=source.concept_id,
                    target_id=target.concept_id,
                    relation="HAS_PROPERTY",
                    cost_latency=2.0,
                    cost_memory=2.0,
                    cost_ir=2.0,
                    fidelity=0.7,
                )
                graph.add_edge(edge)

    logger.debug(
        "build_graph_from_corpus: %d nœuds, %d arcs",
        graph.node_count(), graph.edge_count(),
    )
    return graph


# ─── Algorithme de routage (Dijkstra pondéré) ────────────────────────────────

def route(
    graph: SemanticGraph,
    source_id: str,
    target_id: str,
    *,
    fidelity_min: float = FIDELITY_MIN_THRESHOLD,
    source_lang: str = "",
    target_lang: str = "",
    source_text: str = "",
) -> SemanticRoute:
    """Trouve le chemin sémantique optimal via Dijkstra pondéré.

    Contrainte : chaque arc du chemin doit avoir fidelity ≥ fidelity_min.
    Les arcs avec fidelité insuffisante sont ignorés.

    Coût de chaque arc = edge.total_cost (latence + mémoire + IR + pénalité fidelité).
    Le chemin optimal minimise la somme des coûts.

    Args:
        graph: SemanticGraph construit par build_graph_from_corpus().
        source_id: ConceptID de départ.
        target_id: ConceptID d'arrivée.
        fidelity_min: seuil de fidelité minimale sur les arcs [0,1].
        source_lang / target_lang : pour le rapport.
        source_text: texte source original.

    Returns:
        SemanticRoute avec path, total_cost, min_fidelity, found.
    """
    t0 = time.perf_counter()

    if source_id not in graph.nodes or target_id not in graph.nodes:
        return SemanticRoute(
            source_id=source_id,
            target_id=target_id,
            found=False,
            computation_ms=(time.perf_counter() - t0) * 1000,
        )

    if source_id == target_id:
        return SemanticRoute(
            source_id=source_id,
            target_id=target_id,
            path=[source_id],
            total_cost=0.0,
            min_fidelity=1.0,
            found=True,
            computation_ms=(time.perf_counter() - t0) * 1000,
            source_lang=source_lang,
            target_lang=target_lang,
            source_text=source_text,
        )

    # Dijkstra : (coût_cumulé, concept_id, chemin, arcs_utilisés, fidelité_min)
    heap: list[tuple[float, str, list[str], list[SemanticEdge], float]] = [
        (0.0, source_id, [source_id], [], 1.0)
    ]
    visited: set[str] = set()

    while heap:
        cost, current_id, path, path_edges, min_fid = heapq.heappop(heap)

        if current_id in visited:
            continue
        visited.add(current_id)

        if current_id == target_id:
            result = SemanticRoute(
                source_id=source_id,
                target_id=target_id,
                path=path,
                edges=path_edges,
                total_cost=cost,
                min_fidelity=min_fid,
                found=True,
                computation_ms=(time.perf_counter() - t0) * 1000,
                source_lang=source_lang,
                target_lang=target_lang,
                source_text=source_text,
            )
            logger.debug("route: %s", result.explain())
            return result

        # Explorer les voisins
        for edge in graph.neighbors(current_id):
            if edge.target_id in visited:
                continue
            # Contrainte fidelité
            if edge.fidelity < fidelity_min:
                continue
            new_cost = cost + edge.total_cost
            new_min_fid = min(min_fid, edge.fidelity)
            heapq.heappush(heap, (
                new_cost,
                edge.target_id,
                path + [edge.target_id],
                path_edges + [edge],
                new_min_fid,
            ))

    # Aucun chemin trouvé
    return SemanticRoute(
        source_id=source_id,
        target_id=target_id,
        found=False,
        computation_ms=(time.perf_counter() - t0) * 1000,
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=source_text,
    )


# ─── Routage depuis un texte ──────────────────────────────────────────────────

def route_from_text(
    source_text: str,
    source_lang: str,
    target_concept_code: str,
    *,
    graph: SemanticGraph | None = None,
    fidelity_min: float = FIDELITY_MIN_THRESHOLD,
    adapter=None,
    semantic_corpus=None,
) -> SemanticRoute:
    """Routage sémantique depuis un texte brut vers un ConceptID cible.

    Résout d'abord le texte en ConceptID (via trace_lineage R488),
    puis route dans le graphe sémantique.

    Args:
        source_text: texte brut d'entrée.
        source_lang: langue du texte source.
        target_concept_code: artcb_code cible (ex: "K1", "V1").
        graph: SemanticGraph (construit si None).
        fidelity_min: seuil fidelité minimale.
        adapter / semantic_corpus: partagés pour éviter recompilation.

    Returns:
        SemanticRoute.
    """
    from src.artcb.language.adapter import SemanticCorpus  # noqa: PLC0415
    from src.artcb.language.lineage import trace_lineage  # noqa: PLC0415

    if semantic_corpus is None:
        semantic_corpus = SemanticCorpus()

    if graph is None:
        graph = build_graph_from_corpus(semantic_corpus)

    # Résoudre le texte source
    lin = trace_lineage(source_text, source_lang, adapter=adapter, semantic_corpus=semantic_corpus)
    source_id = lin.concept_id or "K_UNK"

    # Résoudre le concept cible
    target_id = semantic_corpus.get_concept_id(target_concept_code)

    return route(
        graph,
        source_id,
        target_id,
        fidelity_min=fidelity_min,
        source_lang=source_lang,
        source_text=source_text,
    )
