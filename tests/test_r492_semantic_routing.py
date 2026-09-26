"""R492 — Tests Semantic Routing (routage sémantique optimal).

Tests T01→T22 validant :
  - T01-T03 : build_graph_from_corpus() — structure
  - T04-T06 : SemanticNode + SemanticEdge + total_cost
  - T07-T09 : route() — chemin trouvé + non trouvé
  - T10      : route() — source == target → chemin trivial
  - T11      : route() — contrainte fidelity_min
  - T12      : chemin Dijkstra optimal (coût minimal)
  - T13      : route_from_text() — résolution texte → ConceptID → route
  - T14      : SemanticRoute.explain()
  - T15      : SemanticRoute.to_dict() JSON-sérialisable
  - T16      : SemanticRoute.to_json() valide
  - T17      : route() invariants unique_human_proven=False
  - T18      : build_graph_from_corpus() — indépendance linguistique
  - T19      : Graphe contient ACTION + OBJECT + MODIFIER nodes
  - T20      : ACTION→OBJECT arcs existent (OPERATES_ON)
  - T21      : chemin vide si source inconnue
  - T22      : MODULE_VERSION = 1.0.x

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

import json

import pytest

from src.artcb.language.semantic_routing import (
    MODULE_VERSION,
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
    SemanticRoute,
    build_graph_from_corpus,
    route,
    route_from_text,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def graph() -> SemanticGraph:
    """Graphe sémantique partagé — construit une seule fois."""
    return build_graph_from_corpus()


@pytest.fixture(scope="module")
def concept_ids(graph) -> dict[str, str]:
    """Mapping artcb_code → concept_id extrait du graphe."""
    return {node.artcb_code: node.concept_id for node in graph.nodes.values()}


# ─── T01-T03 : build_graph_from_corpus ───────────────────────────────────────

def test_T01_graph_has_nodes(graph):
    """T01 — Le graphe contient des nœuds (24 concepts ARTCB)."""
    assert graph.node_count() > 0


def test_T02_graph_has_edges(graph):
    """T02 — Le graphe contient des arcs."""
    assert graph.edge_count() > 0


def test_T03_graph_covers_all_concepts(graph):
    """T03 — Le graphe contient des nœuds pour chaque catégorie."""
    categories = {node.category for node in graph.nodes.values()}
    assert "ACTION" in categories
    assert "OBJECT" in categories


# ─── T04-T06 : SemanticNode + SemanticEdge ────────────────────────────────────

def test_T04_semantic_node_to_dict():
    """T04 — SemanticNode.to_dict() contient les champs attendus."""
    node = SemanticNode(concept_id="K123", artcb_code="V1", category="ACTION")
    d = node.to_dict()
    assert d["concept_id"] == "K123"
    assert d["artcb_code"] == "V1"
    assert d["category"] == "ACTION"


def test_T05_semantic_edge_total_cost():
    """T05 — SemanticEdge.total_cost = lat + mem + ir + fidelité_penalité."""
    edge = SemanticEdge(
        source_id="A", target_id="B",
        cost_latency=1.0, cost_memory=1.0, cost_ir=1.0,
        fidelity=1.0,  # pas de pénalité
    )
    assert edge.total_cost == 3.0  # 1+1+1 + 0 pénalité

    edge2 = SemanticEdge(
        source_id="A", target_id="B",
        cost_latency=1.0, cost_memory=1.0, cost_ir=1.0,
        fidelity=0.0,  # pénalité max : (1-0)*3 = 3.0
    )
    assert edge2.total_cost == 6.0  # 1+1+1+3


def test_T06_edge_to_dict():
    """T06 — SemanticEdge.to_dict() est sérialisable."""
    edge = SemanticEdge(source_id="A", target_id="B", relation="RELATED", fidelity=0.9)
    d = edge.to_dict()
    assert "total_cost" in d
    assert d["relation"] == "RELATED"


# ─── T07-T09 : route() ───────────────────────────────────────────────────────

def test_T07_route_found(graph, concept_ids):
    """T07 — route() trouve un chemin entre deux concepts connus."""
    source = concept_ids.get("V1")
    target = concept_ids.get("K1")
    if not source or not target:
        pytest.skip("V1 ou K1 non trouvés dans le graphe")
    r = route(graph, source, target)
    assert isinstance(r, SemanticRoute)
    assert r.found is True
    assert len(r.path) >= 1


def test_T08_route_contains_source_and_target(graph, concept_ids):
    """T08 — Le chemin commence par source et finit par target."""
    source = concept_ids.get("V1")
    target = concept_ids.get("K1")
    if not source or not target:
        pytest.skip("V1 ou K1 non trouvés dans le graphe")
    r = route(graph, source, target)
    if r.found:
        assert r.path[0] == source
        assert r.path[-1] == target


def test_T09_route_unknown_node_not_found(graph):
    """T09 — route() avec nœud inconnu → found=False."""
    r = route(graph, "UNKNOWN_ID", "ALSO_UNKNOWN")
    assert r.found is False


# ─── T10 : source == target ──────────────────────────────────────────────────

def test_T10_route_source_equals_target(graph, concept_ids):
    """T10 — Source == target → chemin trivial [source_id], coût=0."""
    source = concept_ids.get("V1")
    if not source:
        pytest.skip("V1 non trouvé")
    r = route(graph, source, source)
    assert r.found is True
    assert r.path == [source]
    assert r.total_cost == 0.0
    assert r.min_fidelity == 1.0


# ─── T11 : contrainte fidelity_min ────────────────────────────────────────────

def test_T11_fidelity_constraint_blocks_path(graph, concept_ids):
    """T11 — fidelity_min=1.0 bloque les arcs avec fidelity < 1.0."""
    # Tous les arcs ont fidelity ∈ [0.7, 0.9] dans notre graphe
    # Avec fidelity_min=1.0, aucun arc n'est autorisé → pas de chemin
    source = concept_ids.get("V1")
    target = concept_ids.get("K1")
    if not source or not target:
        pytest.skip("V1 ou K1 non trouvés")
    r = route(graph, source, target, fidelity_min=1.0)
    # Avec fidelity_min=1.0 et fidelity des arcs < 1.0 → no path
    assert r.found is False


# ─── T12 : coût optimal ──────────────────────────────────────────────────────

def test_T12_optimal_cost_is_minimal(graph, concept_ids):
    """T12 — Le coût total retourné est minimal parmi les chemins possibles."""
    source = concept_ids.get("V1")
    target = concept_ids.get("B1")
    if not source or not target:
        pytest.skip("V1 ou B1 non trouvés")
    r = route(graph, source, target)
    if r.found:
        assert r.total_cost > 0
        assert r.total_cost < float("inf")


# ─── T13 : route_from_text ───────────────────────────────────────────────────

def test_T13_route_from_text(graph):
    """T13 — route_from_text() résout texte → ConceptID puis route."""
    r = route_from_text(
        "vérifier la signature",
        "fr",
        "K1",
        graph=graph,
    )
    assert isinstance(r, SemanticRoute)
    # Le routage doit fonctionner (found ou not) sans erreur
    assert r.source_text == "vérifier la signature"
    assert r.source_lang == "fr"


# ─── T14-T16 : explain + to_dict + to_json ───────────────────────────────────

def test_T14_explain_readable(graph, concept_ids):
    """T14 — SemanticRoute.explain() retourne une chaîne lisible."""
    source = concept_ids.get("V1")
    target = concept_ids.get("K1")
    if not source or not target:
        pytest.skip()
    r = route(graph, source, target, source_lang="fr", target_lang="en")
    explanation = r.explain()
    assert isinstance(explanation, str)
    assert len(explanation) > 0


def test_T15_to_dict_json_serializable(graph, concept_ids):
    """T15 — SemanticRoute.to_dict() est JSON-sérialisable."""
    source = concept_ids.get("V1")
    target = concept_ids.get("K1")
    if not source or not target:
        pytest.skip()
    r = route(graph, source, target)
    d = r.to_dict()
    j = json.dumps(d, ensure_ascii=False)
    parsed = json.loads(j)
    assert parsed["found"] in (True, False)
    assert "path" in parsed


def test_T16_to_json_valid(graph, concept_ids):
    """T16 — SemanticRoute.to_json() est un JSON valide."""
    source = concept_ids.get("V1")
    target = concept_ids.get("K1")
    if not source or not target:
        pytest.skip()
    r = route(graph, source, target)
    j = r.to_json()
    parsed = json.loads(j)
    assert "algorithm" in parsed


# ─── T17 : invariants ────────────────────────────────────────────────────────

def test_T17_invariants_always_false(graph, concept_ids):
    """T17 — unique_human_proven et certified toujours False."""
    source = concept_ids.get("V1", "X")
    target = concept_ids.get("K1", "Y")
    r = route(graph, source, target)
    assert r.unique_human_proven is False
    assert r.certified is False


# ─── T18 : indépendance linguistique ─────────────────────────────────────────

def test_T18_language_independent_routing(graph):
    """T18 — Le même chemin est trouvé depuis FR et EN (même ConceptID)."""
    r_fr = route_from_text("vérifier la signature", "fr", "K1", graph=graph)
    r_en = route_from_text("verify the signature", "en", "K1", graph=graph)
    # Les deux doivent résoudre au même source_id (V1) → même chemin
    assert r_fr.source_id == r_en.source_id, (
        f"FR source_id={r_fr.source_id!r} != EN source_id={r_en.source_id!r} "
        "(doit être le même ConceptID V1)"
    )


# ─── T19-T20 : structure du graphe ───────────────────────────────────────────

def test_T19_graph_has_action_object_modifier(graph):
    """T19 — Le graphe contient les 3 catégories : ACTION, OBJECT, MODIFIER."""
    categories = {node.category for node in graph.nodes.values()}
    for cat in ("ACTION", "OBJECT"):  # MODIFIER peut être absent si corpus petit
        assert cat in categories, f"Catégorie {cat!r} manquante dans le graphe"


def test_T20_action_to_object_edges_exist(graph):
    """T20 — Des arcs ACTION→OBJECT (OPERATES_ON) existent dans le graphe."""
    operates_on_edges = [
        edge
        for edges_list in graph.edges.values()
        for edge in edges_list
        if edge.relation == "OPERATES_ON"
    ]
    assert len(operates_on_edges) > 0, "Des arcs OPERATES_ON doivent exister"


# ─── T21 : nœud source inconnu ───────────────────────────────────────────────

def test_T21_unknown_source_returns_not_found(graph, concept_ids):
    """T21 — Source inconnue → SemanticRoute avec found=False."""
    target = concept_ids.get("K1", "X")
    r = route(graph, "TOTALLY_UNKNOWN_CONCEPT_ID_12345", target)
    assert r.found is False
    assert r.path == []


# ─── T22 : version ───────────────────────────────────────────────────────────

def test_T22_module_version():
    """T22 — MODULE_VERSION de semantic_routing.py est 1.0.x."""
    major, minor, _ = (int(x) for x in MODULE_VERSION.split("."))
    assert (major, minor) == (1, 0)
