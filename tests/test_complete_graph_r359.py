"""Tests R359 — graphe complet bidirectionnel.

Vérifie :
  - 5 nœuds → 20 arcs CONNECTS (N*(N-1))
  - TEMPORAL uniquement entre consécutifs (N-1 arcs)
  - CAUSES uniquement si marqueur détecté
  - Pas d'auto-boucle (i→i)
  - Sémantique préservée : CONNECTS ≠ TEMPORAL ≠ CAUSES
  - Croissance quadratique confirmée pour N=2,3,4,5
  - EdgeType.CONNECTS dans grammar
"""
from __future__ import annotations

import pytest

from src.artcb.ir.encoder import IREncoder
from src.artcb.ir.grammar import EdgeType


@pytest.fixture
def encoder() -> IREncoder:
    return IREncoder()


# ─── Formule N(N-1) ──────────────────────────────────────────────────────────

def _connects_count(graph) -> int:
    return sum(1 for e in graph.edges if e.rel == EdgeType.CONNECTS.value)

def _temporal_count(graph) -> int:
    return sum(1 for e in graph.edges if e.rel == EdgeType.TEMPORAL.value)

def _causes_count(graph) -> int:
    return sum(1 for e in graph.edges if e.rel == EdgeType.CAUSES.value)

def _n_nodes(graph) -> int:
    return len(graph.nodes)


def test_complete_graph_5_nodes_20_connects(encoder: IREncoder):
    """5 nœuds → exactement 20 arcs CONNECTS (5×4)."""
    text = "A. B. C. D. E."
    graph = encoder.encode(text)
    n = _n_nodes(graph)
    assert n == 5, f"attendu 5 nœuds, obtenu {n}"
    connects = _connects_count(graph)
    assert connects == n * (n - 1), (
        f"attendu {n*(n-1)} arcs CONNECTS pour {n} nœuds, obtenu {connects}"
    )


def test_complete_graph_2_nodes(encoder: IREncoder):
    """2 nœuds → 2 arcs CONNECTS."""
    text = "Première affirmation. Deuxième affirmation."
    graph = encoder.encode(text)
    n = _n_nodes(graph)
    connects = _connects_count(graph)
    assert connects == n * (n - 1)


def test_complete_graph_3_nodes(encoder: IREncoder):
    """3 nœuds → 6 arcs CONNECTS."""
    text = "Premier. Deuxième. Troisième."
    graph = encoder.encode(text)
    n = _n_nodes(graph)
    connects = _connects_count(graph)
    assert connects == n * (n - 1)


def test_complete_graph_4_nodes(encoder: IREncoder):
    """4 nœuds → 12 arcs CONNECTS."""
    text = "Un. Deux. Trois. Quatre."
    graph = encoder.encode(text)
    n = _n_nodes(graph)
    connects = _connects_count(graph)
    assert connects == n * (n - 1)


def test_complete_graph_formula_quadratic(encoder: IREncoder):
    """Croissance N(N-1) vérifiée pour N=2..5."""
    sentences = ["Phrase un.", "Phrase deux.", "Phrase trois.", "Phrase quatre.", "Phrase cinq."]
    for k in range(2, 6):
        text = " ".join(sentences[:k])
        graph = encoder.encode(text)
        n = len(graph.nodes)
        connects = _connects_count(graph)
        expected = n * (n - 1)
        assert connects == expected, (
            f"N={n}: attendu {expected} CONNECTS, obtenu {connects}"
        )


# ─── Pas d'auto-boucle ───────────────────────────────────────────────────────

def test_no_self_loop(encoder: IREncoder):
    """Aucun arc d'un nœud vers lui-même."""
    text = "A. B. C. D. E."
    graph = encoder.encode(text)
    for edge in graph.edges:
        assert edge.fr != edge.to, (
            f"Auto-boucle détectée : {edge.fr} → {edge.to} rel={edge.rel}"
        )


# ─── TEMPORAL uniquement entre consécutifs ───────────────────────────────────

def test_temporal_only_consecutive(encoder: IREncoder):
    """TEMPORAL uniquement entre nœuds consécutifs (i→i+1), N-1 arcs."""
    text = "Alpha. Beta. Gamma. Delta. Epsilon."
    graph = encoder.encode(text)
    temporal = [e for e in graph.edges if e.rel == EdgeType.TEMPORAL.value]
    n = len(graph.nodes)
    # Exactement N-1 arcs temporaux
    assert len(temporal) == n - 1, (
        f"attendu {n-1} arcs TEMPORAL, obtenu {len(temporal)}"
    )
    # Chaque arc temporal relie deux nœuds consécutifs
    node_ids = [nd.id for nd in graph.nodes]
    for e in temporal:
        i = node_ids.index(e.fr)
        j = node_ids.index(e.to)
        assert j == i + 1, (
            f"TEMPORAL non-consécutif : {e.fr}(i={i}) → {e.to}(j={j})"
        )


def test_temporal_not_for_all_pairs(encoder: IREncoder):
    """TEMPORAL N'EST PAS créé pour toutes les paires — seulement N-1."""
    text = "Un. Deux. Trois. Quatre. Cinq."
    graph = encoder.encode(text)
    temporal = _temporal_count(graph)
    n = len(graph.nodes)
    # Si TEMPORAL était pour toutes les paires : N*(N-1) = 20
    # Il doit y en avoir exactement N-1 = 4
    assert temporal < n * (n - 1), "TEMPORAL ne doit pas couvrir toutes les paires"
    assert temporal == n - 1


# ─── CAUSES uniquement si marqueur ───────────────────────────────────────────

def test_causes_not_invented(encoder: IREncoder):
    """CAUSES n'est pas ajouté sans marqueur causal."""
    text = "Il fait beau. Les oiseaux chantent. La mer est calme."
    graph = encoder.encode(text)
    causes = _causes_count(graph)
    # Aucun marqueur causal ("donc", "ainsi", etc.) → 0 arc CAUSES
    assert causes == 0, f"CAUSES inventé sans marqueur : {causes} arcs"


def test_causes_added_with_marker(encoder: IREncoder):
    """CAUSES ajouté uniquement entre consécutifs avec marqueur."""
    text = "Il pleut. Donc les routes sont mouillées. La circulation est ralentie."
    graph = encoder.encode(text)
    causes = _causes_count(graph)
    # "Donc" entre phrase 1 et 2 → 1 arc CAUSES
    assert causes >= 1, "CAUSES attendu avec marqueur 'Donc'"
    # CAUSES uniquement entre consécutifs
    node_ids = [nd.id for nd in graph.nodes]
    for e in graph.edges:
        if e.rel == EdgeType.CAUSES.value:
            i = node_ids.index(e.fr)
            j = node_ids.index(e.to)
            assert j == i + 1, (
                f"CAUSES entre non-consécutifs : {e.fr}(i={i}) → {e.to}(j={j})"
            )


# ─── Sémantique des arcs ──────────────────────────────────────────────────────

def test_connects_semantics(encoder: IREncoder):
    """CONNECTS = co-présence, poids 1.0, pas TEMPORAL ni CAUSES."""
    text = "A. B. C."
    graph = encoder.encode(text)
    for e in graph.edges:
        if e.rel == EdgeType.CONNECTS.value:
            assert e.w == 1.0
            # Un arc CONNECTS ne doit pas être aussi TEMPORAL ou CAUSES
            # (ce sont des types distincts)
            assert e.rel != EdgeType.TEMPORAL.value
            assert e.rel != EdgeType.CAUSES.value


def test_edge_type_connects_in_grammar():
    """EdgeType.CONNECTS existe dans la grammaire."""
    assert hasattr(EdgeType, "CONNECTS")
    assert EdgeType.CONNECTS.value == "↔"


def test_bidirectional_both_directions(encoder: IREncoder):
    """Pour chaque paire (i,j), les arcs i→j ET j→i existent."""
    text = "Alpha. Beta. Gamma."
    graph = encoder.encode(text)
    connects = {(e.fr, e.to) for e in graph.edges if e.rel == EdgeType.CONNECTS.value}
    nodes = [nd.id for nd in graph.nodes]
    for i in range(len(nodes)):
        for j in range(len(nodes)):
            if i == j:
                continue
            assert (nodes[i], nodes[j]) in connects, (
                f"Arc CONNECTS manquant : {nodes[i]} → {nodes[j]}"
            )

# ─── R360 — scalabilité : fenêtre glissante au-delà du seuil ─────────────────

def test_r360_complete_below_threshold():
    """Sous le seuil (N≤20) → graphe complet N(N-1)."""
    enc = IREncoder(max_complete_nodes=20)
    text = " ".join(f"Phrase {i}." for i in range(1, 11))
    graph = enc.encode(text)
    n = len(graph.nodes)
    assert n <= 20
    connects = _connects_count(graph)
    assert connects == n * (n - 1), f"N={n}: attendu {n*(n-1)}, obtenu {connects}"


def test_r360_sliding_window_above_threshold():
    """Au-delà du seuil (N>20) → fenêtre glissante, linéaire."""
    k = 3
    enc = IREncoder(max_complete_nodes=5, sliding_window_k=k)
    # Forcer N > seuil
    text = " ".join(f"Phrase {i}." for i in range(1, 12))
    graph = enc.encode(text)
    n = len(graph.nodes)
    assert n > 5, f"attendu N>5 pour déclencher la fenêtre, N={n}"
    connects = _connects_count(graph)
    # Maximum théorique avec fenêtre ±K
    max_connects = 2 * k * n
    assert connects <= max_connects, (
        f"N={n}, K={k}: connects={connects} > max_fenêtre={max_connects}"
    )
    # Nettement inférieur au graphe complet
    assert connects < n * (n - 1), (
        f"fenêtre glissante ne réduit pas les arcs : connects={connects}, N(N-1)={n*(n-1)}"
    )


def test_r360_no_self_loop_sliding():
    """Pas d'auto-boucle en mode fenêtre glissante."""
    enc = IREncoder(max_complete_nodes=3, sliding_window_k=2)
    text = " ".join(f"Concept {i}." for i in range(1, 10))
    graph = enc.encode(text)
    for e in graph.edges:
        assert e.fr != e.to, f"Auto-boucle en mode fenêtre : {e.fr} → {e.to}"


def test_r360_temporal_preserved_in_sliding():
    """TEMPORAL reste N-1 arcs en mode fenêtre glissante."""
    enc = IREncoder(max_complete_nodes=3, sliding_window_k=2)
    text = " ".join(f"Phrase {i}." for i in range(1, 8))
    graph = enc.encode(text)
    n = len(graph.nodes)
    temporal = _temporal_count(graph)
    assert temporal == n - 1, f"TEMPORAL={temporal}, attendu N-1={n-1}"


def test_r360_window_connects_both_directions():
    """En mode fenêtre, les arcs sont bidirectionnels dans la fenêtre."""
    k = 2
    enc = IREncoder(max_complete_nodes=3, sliding_window_k=k)
    text = " ".join(f"X{i}." for i in range(1, 8))
    graph = enc.encode(text)
    connects = {(e.fr, e.to) for e in graph.edges if e.rel == "↔"}
    nodes = [nd.id for nd in graph.nodes]
    # Pour chaque paire dans la fenêtre : les deux directions doivent exister
    n = len(nodes)
    for i in range(n):
        for j in range(max(0, i - k), min(n, i + k + 1)):
            if i == j:
                continue
            assert (nodes[i], nodes[j]) in connects, (
                f"Arc manquant dans fenêtre : {nodes[i]} → {nodes[j]}"
            )


def test_r360_threshold_configurable():
    """Le seuil est configurable — deux encodeurs différents produisent des structures différentes."""
    text = " ".join(f"N{i}." for i in range(1, 9))
    enc_full = IREncoder(max_complete_nodes=50)   # graphe complet
    enc_win = IREncoder(max_complete_nodes=3, sliding_window_k=2)  # fenêtre
    g_full = enc_full.encode(text)
    g_win = enc_win.encode(text)
    n = len(g_full.nodes)
    assert _connects_count(g_full) == n * (n - 1)
    assert _connects_count(g_win) < n * (n - 1)


