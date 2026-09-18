"""Tests TASK-006 — Creator-node / Primary failure policy (2026-09-18).

Tests A→P couvrant :
  A  : classify_failure_state — downtime=0 → ALIVE / WAIT
  B  : classify_failure_state — downtime < 24h → DEAD_TRANSIENT / WAIT
  C  : classify_failure_state — downtime 24h–7j → DEAD_RECOVERABLE / VIEW_CHANGE
  D  : classify_failure_state — downtime > 7j → DEAD_PERMANENT / OPERATOR_DECISION
  E  : classify_failure_state — seuils personnalisables
  F  : compute_quorum_after_removal — N=4 → N=3 Q=2 maintenu
  G  : compute_quorum_after_removal — N=3 → N=2 quorum perdu
  H  : compute_quorum_after_removal — nœud bloqué exclu
  I  : assess_primary_failure — ALIVE
  J  : assess_primary_failure — DEAD_TRANSIENT
  K  : assess_primary_failure — DEAD_RECOVERABLE → next_view_plan présent
  L  : assess_primary_failure — DEAD_PERMANENT → quorum après retrait calculé
  M  : assess_primary_failure — surviving_nodes exclut primary + bloqués
  N  : build_node_removal_plan — N=4 → N=3 quorum maintenu
  O  : build_node_removal_plan — N=3 → N=2 quorum perdu → step 0 = avertissement
  P  : to_dict() sérialisable JSON
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artcb.consensus.creator_node_policy import (
    PrimaryFailureState,
    NetworkResponseAction,
    PrimaryFailureReport,
    NodeRemovalPlan,
    classify_failure_state,
    compute_quorum_after_removal,
    assess_primary_failure,
    build_node_removal_plan,
    _TRANSIENT_THRESHOLD_S,
    _RECOVERABLE_THRESHOLD_S,
    _BLOCKED_NODES,
)

# Replica set fixe pour les tests (indépendant de l'environnement live)
_TEST_REPLICAS_4 = ("ovh-node-1", "aws-node-3", "ovh-node-2", "ovh-node-4")
_TEST_REPLICAS_3 = ("aws-node-3", "ovh-node-2", "ovh-node-4")
_TEST_BLOCKED    = frozenset()  # pas de bloqué pour simplifier les tests


# ─── Test A : ALIVE ───────────────────────────────────────────────────────────

def test_A_alive() -> None:
    """Test A : downtime=0 → ALIVE + WAIT."""
    state, action = classify_failure_state(0)
    assert state == PrimaryFailureState.ALIVE
    assert action == NetworkResponseAction.WAIT


def test_A2_negative_downtime_alive() -> None:
    """Test A2 : downtime négatif → ALIVE (même traitement que 0)."""
    state, action = classify_failure_state(-100)
    assert state == PrimaryFailureState.ALIVE


# ─── Test B : DEAD_TRANSIENT ──────────────────────────────────────────────────

def test_B_dead_transient_1h() -> None:
    """Test B : 1h d'indisponibilité → DEAD_TRANSIENT + WAIT."""
    state, action = classify_failure_state(3600)
    assert state == PrimaryFailureState.DEAD_TRANSIENT
    assert action == NetworkResponseAction.WAIT


def test_B2_dead_transient_just_before_threshold() -> None:
    """Test B2 : juste en-dessous du seuil transitoire → encore DEAD_TRANSIENT."""
    state, action = classify_failure_state(_TRANSIENT_THRESHOLD_S - 1)
    assert state == PrimaryFailureState.DEAD_TRANSIENT


# ─── Test C : DEAD_RECOVERABLE ────────────────────────────────────────────────

def test_C_dead_recoverable_48h() -> None:
    """Test C : 48h → DEAD_RECOVERABLE + TRIGGER_VIEW_CHANGE."""
    state, action = classify_failure_state(48 * 3600)
    assert state == PrimaryFailureState.DEAD_RECOVERABLE
    assert action == NetworkResponseAction.TRIGGER_VIEW_CHANGE


def test_C2_dead_recoverable_just_at_threshold() -> None:
    """Test C2 : exactement au seuil transitoire → DEAD_RECOVERABLE."""
    state, action = classify_failure_state(_TRANSIENT_THRESHOLD_S)
    assert state == PrimaryFailureState.DEAD_RECOVERABLE


# ─── Test D : DEAD_PERMANENT ─────────────────────────────────────────────────

def test_D_dead_permanent_8days() -> None:
    """Test D : 8 jours → DEAD_PERMANENT + OPERATOR_DECISION."""
    state, action = classify_failure_state(8 * 86400)
    assert state == PrimaryFailureState.DEAD_PERMANENT
    assert action == NetworkResponseAction.OPERATOR_DECISION


def test_D2_dead_permanent_at_threshold() -> None:
    """Test D2 : exactement au seuil récupérable → DEAD_PERMANENT."""
    state, action = classify_failure_state(_RECOVERABLE_THRESHOLD_S)
    assert state == PrimaryFailureState.DEAD_PERMANENT


# ─── Test E : seuils personnalisables ────────────────────────────────────────

def test_E_custom_thresholds() -> None:
    """Test E : seuils personnalisés permettent des tests rapides."""
    # Seuil court pour les tests
    state, action = classify_failure_state(
        100,
        transient_threshold=50,
        recoverable_threshold=200,
    )
    assert state == PrimaryFailureState.DEAD_RECOVERABLE

    state, _ = classify_failure_state(
        300,
        transient_threshold=50,
        recoverable_threshold=200,
    )
    assert state == PrimaryFailureState.DEAD_PERMANENT


# ─── Test F : quorum N=4 → N=3 maintenu ──────────────────────────────────────

def test_F_quorum_after_removal_n4_to_n3() -> None:
    """Test F : retirer 1 nœud de N=4 → N=3, Q=2, quorum maintenu."""
    q = compute_quorum_after_removal(
        "aws-node-3",
        all_replicas=_TEST_REPLICAS_4,
        blocked=_TEST_BLOCKED,
    )
    assert q["new_n"] == 3
    assert q["quorum_maintained"] is True
    assert "aws-node-3" not in q["effective_replicas"]


# ─── Test G : quorum N=3 → N=2 perdu ─────────────────────────────────────────

def test_G_quorum_lost_n3_to_n2() -> None:
    """Test G (adversarial) : retirer 1 nœud de N=3 → N=2, quorum perdu."""
    q = compute_quorum_after_removal(
        "aws-node-3",
        all_replicas=_TEST_REPLICAS_3,
        blocked=_TEST_BLOCKED,
    )
    assert q["new_n"] == 2
    assert q["quorum_maintained"] is False


# ─── Test H : nœud bloqué exclu du quorum ────────────────────────────────────

def test_H_blocked_node_excluded_from_quorum() -> None:
    """Test H : nœud bloqué opérateur exclu des replicas effectifs."""
    blocked = frozenset({"ovh-node-1"})
    q = compute_quorum_after_removal(
        "aws-node-3",
        all_replicas=_TEST_REPLICAS_4,
        blocked=blocked,
    )
    assert "ovh-node-1" not in q["effective_replicas"]
    assert "aws-node-3" not in q["effective_replicas"]
    assert q["new_n"] == 2   # 4 - 2 bloqués/retirés


# ─── Test I : assess ALIVE ───────────────────────────────────────────────────

def test_I_assess_primary_alive() -> None:
    """Test I : primary vivant (downtime=0) → rapport ALIVE."""
    report = assess_primary_failure(
        primary_node_id="aws-node-3",
        downtime_seconds=0,
        current_view=27,
    )
    assert report.failure_state == PrimaryFailureState.ALIVE
    assert report.recommended_action == NetworkResponseAction.WAIT
    assert report.certified_100 is False


# ─── Test J : assess DEAD_TRANSIENT ──────────────────────────────────────────

def test_J_assess_dead_transient() -> None:
    """Test J : 6h d'indisponibilité → DEAD_TRANSIENT."""
    report = assess_primary_failure(
        primary_node_id="aws-node-3",
        downtime_seconds=6 * 3600,
        current_view=27,
    )
    assert report.failure_state == PrimaryFailureState.DEAD_TRANSIENT
    assert report.recommended_action == NetworkResponseAction.WAIT
    assert report.downtime_seconds == 6 * 3600


# ─── Test K : assess DEAD_RECOVERABLE → next_view présent ────────────────────

def test_K_assess_dead_recoverable_has_view_plan() -> None:
    """Test K : DEAD_RECOVERABLE → next_view_plan est un dict avec from_view."""
    report = assess_primary_failure(
        primary_node_id="aws-node-3",
        downtime_seconds=48 * 3600,
        current_view=27,
    )
    assert report.failure_state == PrimaryFailureState.DEAD_RECOVERABLE
    assert isinstance(report.next_view_plan, dict)
    assert "from_view" in report.next_view_plan
    assert report.next_view_plan["from_view"] == 27


# ─── Test L : assess DEAD_PERMANENT → quorum calculé ─────────────────────────

def test_L_assess_dead_permanent_quorum_impact() -> None:
    """Test L : DEAD_PERMANENT → quorum_after_removal calculé et cohérent."""
    report = assess_primary_failure(
        primary_node_id="aws-node-3",
        downtime_seconds=8 * 86400,
        current_view=27,
    )
    assert report.failure_state == PrimaryFailureState.DEAD_PERMANENT
    assert report.recommended_action == NetworkResponseAction.OPERATOR_DECISION
    assert "new_n" in report.quorum_after_removal
    assert "quorum_maintained" in report.quorum_after_removal
    assert report.certified_100 is False


# ─── Test M : surviving_nodes exclut primary + bloqués ───────────────────────

def test_M_surviving_nodes_excludes_primary_and_blocked() -> None:
    """Test M : surviving_nodes n'inclut jamais le primary mort ni les bloqués."""
    report = assess_primary_failure(
        primary_node_id="aws-node-3",
        downtime_seconds=8 * 86400,
        current_view=27,
    )
    assert "aws-node-3" not in report.surviving_nodes
    for blocked in _BLOCKED_NODES:
        assert blocked not in report.surviving_nodes


# ─── Test N : removal plan N=4 → N=3 quorum maintenu ────────────────────────

def test_N_removal_plan_n4_quorum_maintained() -> None:
    """Test N : plan de retrait N=4 → N=3 — quorum maintenu, étapes listées."""
    plan = build_node_removal_plan(
        "aws-node-3",
        reason="permanent_failure",
        all_replicas=_TEST_REPLICAS_4,
        blocked=_TEST_BLOCKED,
    )
    assert plan.quorum_maintained is True
    assert plan.new_n == 3
    assert len(plan.action_steps) >= 7  # au moins 7 étapes
    # Vérifier que l'étape 2 mentionne node_registry.py
    assert any("node_registry" in s for s in plan.action_steps)
    assert plan.certified_100 is False


# ─── Test O : removal plan N=3 → N=2 avertissement ──────────────────────────

def test_O_removal_plan_n3_quorum_lost_warning() -> None:
    """Test O (adversarial) : plan de retrait N=3 → N=2 — premier step = avertissement."""
    plan = build_node_removal_plan(
        "aws-node-3",
        reason="permanent_failure",
        all_replicas=_TEST_REPLICAS_3,
        blocked=_TEST_BLOCKED,
    )
    assert plan.quorum_maintained is False
    assert plan.new_n == 2
    # Première étape = avertissement quorum insuffisant
    assert "QUORUM" in plan.action_steps[0] or "quorum" in plan.action_steps[0].lower()


# ─── Test P : sérialisation JSON ─────────────────────────────────────────────

def test_P_to_dict_json_serializable() -> None:
    """Test P : to_dict() des deux dataclasses est JSON-sérialisable."""
    report = assess_primary_failure(
        primary_node_id="aws-node-3",
        downtime_seconds=8 * 86400,
        current_view=27,
    )
    d = report.to_dict()
    j = json.dumps(d)
    assert len(j) > 100

    plan = build_node_removal_plan(
        "aws-node-3",
        all_replicas=_TEST_REPLICAS_4,
        blocked=_TEST_BLOCKED,
    )
    d2 = plan.to_dict()
    j2 = json.dumps(d2)
    assert len(j2) > 100
