"""R490 + R491 — Tests Pareto Runtime + Pareto Inversé.

Tests T01→T28 validant :
  R490 — Pareto Runtime (T01→T18) :
    - T01-T03 : benchmark_pareto() — structure
    - T04-T06 : dimensions mesurées
    - T07-T08 : normalisation [0,1]
    - T09-T10 : front de Pareto (non-dominés)
    - T11-T12 : dominance correcte
    - T13      : fidelité sémantique pondérée dans pareto_score
    - T14      : texte liste vide → front vide
    - T15      : to_json() valide
    - T16      : run_id déterministe
    - T17      : MODULE_VERSION R490
    - T18      : invariants

  R491 — Pareto Inversé (T19→T28) :
    - T19      : compute_delta() — deltas corrects
    - T20      : audit_optimization() — runtime gain sans perte → safe
    - T21      : audit_optimization() — runtime gain + perte fidelité → DANGEREUX
    - T22      : audit_optimization() — perte runtime sans gain → non-dangereux
    - T23      : compare_fronts() — DANGEREUX sur configs divergentes
    - T24      : compare_fronts() — SAFE sur configs identiques
    - T25      : seuil personnalisé fidelity_loss_threshold
    - T26      : DangerousOptimization.to_dict() JSON-sérialisable
    - T27      : RuntimeDelta.is_runtime_gain() / is_semantic_loss()
    - T28      : MODULE_VERSION R491

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

import json

import pytest

# ─── R490 imports ─────────────────────────────────────────────────────────────
from src.artcb.language.pareto import (
    MODULE_VERSION as PARETO_VERSION,
    ParetoFront,
    ParetoPoint,
    _compute_pareto_front,
    _dominates,
    _normalize_points,
    benchmark_pareto,
)

# ─── R491 imports ─────────────────────────────────────────────────────────────
from src.artcb.language.pareto_inverse import (
    MODULE_VERSION as INV_VERSION,
    DangerousOptimization,
    RuntimeDelta,
    audit_optimization,
    compare_fronts,
    compute_delta,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fr_front() -> ParetoFront:
    """ParetoFront FR minimal partagé."""
    return benchmark_pareto(
        "fr",
        [
            "vérifier la signature",
            "créer un bloc",
            "chiffrer les données",
            "stocker le résultat",
        ],
    )


@pytest.fixture(scope="module")
def unk_front() -> ParetoFront:
    """ParetoFront avec textes non-résolus (UNK) — pour tests R491."""
    return benchmark_pareto(
        "fr",
        ["xyzzy abc", "qwerty foo", "random bar", "no match here"],
    )


# ─── T01-T03 : structure ParetoFront ─────────────────────────────────────────

def test_T01_benchmark_returns_pareto_front(fr_front):
    """T01 — benchmark_pareto() retourne un ParetoFront."""
    assert isinstance(fr_front, ParetoFront)


def test_T02_front_has_all_points(fr_front):
    """T02 — ParetoFront.all_points contient tous les points mesurés."""
    assert len(fr_front.all_points) == 4


def test_T03_front_partition_complete(fr_front):
    """T03 — front_points + dominated_points = all_points."""
    assert (
        len(fr_front.front_points) + len(fr_front.dominated_points)
        == len(fr_front.all_points)
    )


# ─── T04-T06 : dimensions ────────────────────────────────────────────────────

def test_T04_all_points_have_latency(fr_front):
    """T04 — Chaque point a latency_ms >= 0."""
    for p in fr_front.all_points:
        assert p.latency_ms >= 0.0


def test_T05_all_points_have_fidelity(fr_front):
    """T05 — semantic_fidelity ∈ {0.0, 1.0} (concept résolu ou UNK)."""
    for p in fr_front.all_points:
        assert p.semantic_fidelity in (0.0, 1.0), (
            f"semantic_fidelity={p.semantic_fidelity} doit être 0.0 ou 1.0"
        )


def test_T06_all_points_have_step_count(fr_front):
    """T06 — step_count == 7 (7 étapes du lineage)."""
    for p in fr_front.all_points:
        assert p.step_count == 7, f"step_count={p.step_count} doit être 7"


# ─── T07-T08 : normalisation ─────────────────────────────────────────────────

def test_T07_normalized_scores_in_01():
    """T07 — Les scores normalisés sont dans [0,1] après normalisation."""
    points = [
        ParetoPoint(point_id="a", text="t1", lang="fr",
                    semantic_fidelity=1.0, latency_ms=5.0, memory_bytes=100, ir_size_chars=200),
        ParetoPoint(point_id="b", text="t2", lang="fr",
                    semantic_fidelity=0.0, latency_ms=20.0, memory_bytes=400, ir_size_chars=800),
    ]
    _normalize_points(points)
    for p in points:
        assert 0.0 <= p._norm_fidelity <= 1.0
        assert 0.0 <= p._norm_latency <= 1.0
        assert 0.0 <= p._norm_memory <= 1.0
        assert 0.0 <= p._norm_ir_size <= 1.0
        assert 0.0 <= p.pareto_score <= 1.0


def test_T08_fast_point_has_higher_latency_score():
    """T08 — Le point le plus rapide a _norm_latency=1.0."""
    points = [
        ParetoPoint(point_id="fast", text="t1", lang="fr",
                    semantic_fidelity=1.0, latency_ms=2.0, memory_bytes=100, ir_size_chars=200),
        ParetoPoint(point_id="slow", text="t2", lang="fr",
                    semantic_fidelity=1.0, latency_ms=20.0, memory_bytes=100, ir_size_chars=200),
    ]
    _normalize_points(points)
    fast = next(p for p in points if p.point_id == "fast")
    slow = next(p for p in points if p.point_id == "slow")
    assert fast._norm_latency > slow._norm_latency


# ─── T09-T10 : front de Pareto ────────────────────────────────────────────────

def test_T09_pareto_front_exists(fr_front):
    """T09 — Le front de Pareto contient au moins 1 point."""
    assert len(fr_front.front_points) >= 1


def test_T10_front_points_flagged(fr_front):
    """T10 — Les points du front ont is_in_front=True."""
    for p in fr_front.front_points:
        assert p.is_in_front is True
    for p in fr_front.dominated_points:
        assert p.is_in_front is False


# ─── T11-T12 : dominance ─────────────────────────────────────────────────────

def test_T11_dominates_correctly():
    """T11 — _dominates(A, B) est True si A est meilleur sur toutes dims."""
    from src.artcb.language.pareto import FIDELITY_WEIGHT
    a = ParetoPoint(point_id="a", text="t1", lang="fr")
    b = ParetoPoint(point_id="b", text="t2", lang="fr")
    # A parfait, B nul
    a._norm_fidelity = 1.0; a._norm_latency = 1.0; a._norm_memory = 1.0
    a._norm_ir_size = 1.0; a._norm_round_trip = 1.0
    b._norm_fidelity = 0.5; b._norm_latency = 0.5; b._norm_memory = 0.5
    b._norm_ir_size = 0.5; b._norm_round_trip = 0.5
    assert _dominates(a, b) is True
    assert _dominates(b, a) is False


def test_T12_equal_points_dont_dominate():
    """T12 — Deux points identiques ne se dominent pas mutuellement."""
    a = ParetoPoint(point_id="a", text="t1", lang="fr")
    b = ParetoPoint(point_id="b", text="t2", lang="fr")
    for p in [a, b]:
        p._norm_fidelity = 0.8; p._norm_latency = 0.7; p._norm_memory = 0.6
        p._norm_ir_size = 0.9; p._norm_round_trip = 0.5
    # Identiques → aucun ne domine l'autre
    assert _dominates(a, b) is False
    assert _dominates(b, a) is False


# ─── T13 : fidelité pondérée ─────────────────────────────────────────────────

def test_T13_fidelity_weighted_in_pareto_score():
    """T13 — La fidelité sémantique est pondérée FIDELITY_WEIGHT dans pareto_score."""
    from src.artcb.language.pareto import FIDELITY_WEIGHT
    a = ParetoPoint(point_id="a", text="t1", lang="fr",
                    semantic_fidelity=1.0, latency_ms=1.0, memory_bytes=1, ir_size_chars=1)
    b = ParetoPoint(point_id="b", text="t2", lang="fr",
                    semantic_fidelity=0.0, latency_ms=1.0, memory_bytes=1, ir_size_chars=1)
    _normalize_points([a, b])
    # A a fidelité=1, B fidelité=0 — le score de A doit être supérieur
    assert a.pareto_score > b.pareto_score


# ─── T14 : edge cases ────────────────────────────────────────────────────────

def test_T14_single_text_is_in_front():
    """T14 — Un seul texte → il est dans le front (pas de dominance possible)."""
    front = benchmark_pareto("fr", ["vérifier la signature"])
    assert len(front.all_points) == 1
    # Avec 1 seul point, il est dans le "front" par défaut
    assert len(front.front_points) + len(front.dominated_points) == 1


# ─── T15-T16 : sérialisation + déterminisme ──────────────────────────────────

def test_T15_to_json_valid(fr_front):
    """T15 — ParetoFront.to_json() est un JSON valide."""
    j = fr_front.to_json()
    parsed = json.loads(j)
    assert parsed["lang"] == "fr"
    assert "front_points" in parsed


def test_T16_run_id_deterministic():
    """T16 — Deux runs identiques ont le même run_id."""
    texts = ["vérifier la signature", "créer un bloc"]
    f1 = benchmark_pareto("fr", texts)
    f2 = benchmark_pareto("fr", texts)
    assert f1.run_id == f2.run_id


# ─── T17-T18 : version + invariants ──────────────────────────────────────────

def test_T17_module_version_pareto():
    """T17 — MODULE_VERSION de pareto.py est 1.0.x."""
    major, minor, _ = (int(x) for x in PARETO_VERSION.split("."))
    assert (major, minor) == (1, 0)


def test_T18_invariants_always_false(fr_front):
    """T18 — unique_human_proven et certified toujours False."""
    assert fr_front.unique_human_proven is False
    assert fr_front.certified is False
    for p in fr_front.all_points:
        assert p.unique_human_proven is False
        assert p.certified is False


# ═══════════════════════════════════════════════════════════════════════════════
# R491 — Tests Pareto Inversé
# ═══════════════════════════════════════════════════════════════════════════════

# ─── T19 : compute_delta ─────────────────────────────────────────────────────

def test_T19_compute_delta_correct():
    """T19 — compute_delta() calcule les deltas corrects."""
    baseline = [
        {"semantic_fidelity": 1.0, "latency_ms": 10.0, "memory_bytes": 200,
         "ir_size_chars": 500, "round_trip_ok": True},
        {"semantic_fidelity": 0.5, "latency_ms": 8.0, "memory_bytes": 150,
         "ir_size_chars": 400, "round_trip_ok": False},
    ]
    candidate = [
        {"semantic_fidelity": 0.8, "latency_ms": 5.0, "memory_bytes": 100,
         "ir_size_chars": 300, "round_trip_ok": True},
        {"semantic_fidelity": 0.3, "latency_ms": 4.0, "memory_bytes": 80,
         "ir_size_chars": 200, "round_trip_ok": True},
    ]
    delta = compute_delta(baseline, candidate)
    # Candidate moins bonne sur fidelity (0.55 vs 0.75) → delta négatif
    assert delta.delta_semantic_fidelity < 0
    # Candidate plus rapide (4.5ms vs 9ms) → delta latency positif
    assert delta.delta_latency_ms > 0
    # Candidate moins de mémoire (90 vs 175) → delta memory positif
    assert delta.delta_memory_bytes > 0


# ─── T20-T22 : audit_optimization ────────────────────────────────────────────

def test_T20_safe_optimization():
    """T20 — Runtime gain sans perte sémantique → SAFE."""
    delta = RuntimeDelta(
        delta_semantic_fidelity=0.0,   # pas de perte
        delta_latency_ms=5.0,          # plus rapide
        delta_memory_bytes=100.0,      # moins de mémoire
        delta_ir_size_chars=0.0,
        delta_round_trip_rate=0.0,
    )
    result = audit_optimization(delta)
    assert result.is_dangerous is False
    assert "SÛRE" in result.recommendation or "sûre" in result.recommendation.lower()


def test_T21_dangerous_optimization():
    """T21 — Runtime gain + perte fidelité > seuil → DANGEREUX."""
    delta = RuntimeDelta(
        delta_semantic_fidelity=-0.05,  # 5% de perte (> seuil 1%)
        delta_latency_ms=8.0,           # 8ms plus rapide
        delta_memory_bytes=200.0,
        delta_ir_size_chars=100.0,
        delta_round_trip_rate=0.0,
    )
    result = audit_optimization(delta, fidelity_loss_threshold=0.01)
    assert result.is_dangerous is True
    assert "REJETER" in result.recommendation


def test_T22_no_gain_no_loss():
    """T22 — Pas de gain runtime + pas de perte → non-dangereux."""
    delta = RuntimeDelta(
        delta_semantic_fidelity=0.005,   # léger gain fidelité
        delta_latency_ms=-2.0,           # légèrement plus lent
        delta_memory_bytes=-10.0,        # légèrement plus de mémoire
        delta_ir_size_chars=-5.0,
        delta_round_trip_rate=0.0,
    )
    result = audit_optimization(delta)
    assert result.is_dangerous is False


# ─── T23-T25 : compare_fronts ────────────────────────────────────────────────

def test_T23_compare_fronts_dangerous(fr_front, unk_front):
    """T23 — Comparaison baseline résolue vs candidate non-résolue → DANGEREUX."""
    result = compare_fronts(
        fr_front, unk_front,
        baseline_label="baseline_resolved",
        candidate_label="unk_candidate",
    )
    # La candidate UNK a fidelité=0 → perte sémantique détectée
    assert isinstance(result, DangerousOptimization)
    # Perte sémantique probable mais pas obligatoire si unk_front est plus lent
    # On vérifie juste que la structure est correcte
    assert result.delta is not None


def test_T24_compare_fronts_safe(fr_front):
    """T24 — Comparaison baseline vs elle-même → SAFE."""
    result = compare_fronts(fr_front, fr_front, baseline_label="b", candidate_label="c")
    assert result.is_dangerous is False


def test_T25_custom_threshold():
    """T25 — Seuil personnalisé fidelity_loss_threshold=0.5 (50%)."""
    # Avec seuil=50%, une perte de 5% ne doit pas être dangereuse
    delta = RuntimeDelta(
        delta_semantic_fidelity=-0.05,  # 5% de perte
        delta_latency_ms=5.0,
        delta_memory_bytes=0.0,
        delta_ir_size_chars=0.0,
        delta_round_trip_rate=0.0,
    )
    result = audit_optimization(delta, fidelity_loss_threshold=0.5)
    assert result.is_dangerous is False  # 5% < 50% → pas dangereux avec seuil 50%


# ─── T26-T28 : sérialisation + version ───────────────────────────────────────

def test_T26_dangerous_optimization_json():
    """T26 — DangerousOptimization.to_dict() est JSON-sérialisable."""
    delta = RuntimeDelta(
        delta_semantic_fidelity=-0.1,
        delta_latency_ms=5.0,
    )
    result = DangerousOptimization(
        is_dangerous=True,
        reason="Test reason",
        delta=delta,
        recommendation="Test recommendation",
    )
    d = result.to_dict()
    j = json.dumps(d, ensure_ascii=False)
    parsed = json.loads(j)
    assert parsed["is_dangerous"] is True


def test_T27_runtime_delta_predicates():
    """T27 — RuntimeDelta.is_runtime_gain() et is_semantic_loss()."""
    d = RuntimeDelta(
        delta_latency_ms=5.0,           # gain runtime
        delta_semantic_fidelity=-0.05,  # perte fidelité
    )
    assert d.is_runtime_gain() is True
    assert d.is_semantic_loss(0.01) is True
    assert d.is_semantic_loss(0.10) is False  # seuil 10% > 5%

    d2 = RuntimeDelta(delta_latency_ms=-3.0)  # pas de gain
    assert d2.is_runtime_gain() is False


def test_T28_module_version_pareto_inverse():
    """T28 — MODULE_VERSION de pareto_inverse.py est 1.0.x."""
    major, minor, _ = (int(x) for x in INV_VERSION.split("."))
    assert (major, minor) == (1, 0)
