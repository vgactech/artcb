"""Tests GO-E / V-01-B — Producteur live failover sans fork.

Scénario :
  - Réseau de N nœuds CONSENSUS
  - Le producteur primaire tombe (plus de heartbeat)
  - Un seul backup est élu (déterministe XOR)
  - Le backup ne commence à produire qu'après la grace period
  - L'ancien producteur revenant en ligne ne crée pas de fork
  - Un nœud non CONSENSUS ne peut pas s'élire

Invariants critiques :
  I1 — Jamais deux producteurs simultanés sur le même tip
  I2 — L'élection est déterministe : même résultat sur tous les nœuds
  I3 — Grace period active → pas de production immédiate
  I4 — Pas d'élection si producteur encore vivant
  I5 — Nœuds insuffisants → ProducerElectionError
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from artcb.p2p.producer_election import (
    ELECTION_GRACE_SECONDS,
    HEARTBEAT_TIMEOUT,
    MIN_CONSENSUS_NODES,
    ElectionResult,
    ProducerElectionError,
    ProducerHeartbeat,
    ProducerMonitor,
    elect_producer,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

CONSENSUS_NODES = [
    "artcb1node_primary",
    "artcb1node_backup_a",
    "artcb1node_backup_b",
    "artcb1node_backup_c",
]

TIP_HASH = "a3f7c2e1b0d5" * 5  # 60 chars


# ── elect_producer — déterminisme ────────────────────────────────────────────

def test_election_is_deterministic() -> None:
    """Tous les nœuds voient le même tip → même élu."""
    r1 = elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
    r2 = elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
    assert r1.elected_node_id == r2.elected_node_id, "L'élection doit être déterministe"


def test_election_different_tip_may_differ() -> None:
    """Tips différents peuvent produire des élus différents (pas un invariant fort)."""
    r1 = elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash="aaa" * 20)
    r2 = elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash="bbb" * 20)
    # Les deux sont valides — on vérifie juste qu'ils sont dans la liste
    assert r1.elected_node_id in CONSENSUS_NODES
    assert r2.elected_node_id in CONSENSUS_NODES


def test_election_excludes_dead_producer() -> None:
    """Le nœud mort (excluded) n'est jamais élu."""
    dead = CONSENSUS_NODES[0]
    result = elect_producer(
        consensus_nodes=CONSENSUS_NODES,
        tip_hash=TIP_HASH,
        exclude_node_id=dead,
    )
    assert result.elected_node_id != dead
    assert dead not in result.candidates


def test_election_elected_in_candidates() -> None:
    """L'élu fait partie des candidats retournés."""
    result = elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
    assert result.elected_node_id in result.candidates


def test_election_single_candidate() -> None:
    """Avec un seul candidat valide, il est forcément élu."""
    nodes = ["artcb1node_primary", "artcb1node_only_backup"]
    result = elect_producer(
        consensus_nodes=nodes,
        tip_hash=TIP_HASH,
        exclude_node_id="artcb1node_primary",
    )
    assert result.elected_node_id == "artcb1node_only_backup"


def test_election_no_candidates_raises() -> None:
    """Tous les nœuds exclus → ProducerElectionError (I5)."""
    with pytest.raises(ProducerElectionError, match="candidat"):
        elect_producer(
            consensus_nodes=["artcb1node_only"],
            tip_hash=TIP_HASH,
            exclude_node_id="artcb1node_only",
        )


def test_election_below_min_consensus_raises() -> None:
    """Réseau trop petit → ProducerElectionError (I5)."""
    # MIN_CONSENSUS_NODES = 2 ; on passe 1 nœud
    with pytest.raises(ProducerElectionError, match="insuffisant"):
        elect_producer(
            consensus_nodes=["artcb1node_a"],
            tip_hash=TIP_HASH,
        )


# ── Grace period ──────────────────────────────────────────────────────────────

def test_grace_period_active_right_after_election() -> None:
    """Juste après l'élection, la grace period est active (I3)."""
    result = elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
    assert result.grace_period_active() is True


def test_grace_period_expired_after_wait() -> None:
    """Après la grace period, can_produce devient True."""
    result = ElectionResult(
        elected_node_id="artcb1node_backup_a",
        tip_hash=TIP_HASH,
        rank_score=0,
        candidates=["artcb1node_backup_a"],
        election_time=time.time() - ELECTION_GRACE_SECONDS - 1,
        grace_expires_at=time.time() - 1,  # expiré
    )
    assert result.grace_period_active() is False


def test_grace_period_prevents_immediate_production() -> None:
    """am_i_elected retourne False si grace active, même si on est l'élu."""
    monitor = ProducerMonitor(local_node_id="artcb1node_backup_a")
    result = elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
    # Forcer l'élu à être ce nœud
    object.__setattr__(result, "elected_node_id", "artcb1node_backup_a")
    # Grace active → am_i_elected False
    assert result.grace_period_active() is True
    assert monitor.am_i_elected(result) is False


# ── ProducerMonitor ────────────────────────────────────────────────────────────

def test_monitor_no_producer_initially() -> None:
    """Pas de producteur connu → producer_is_dead=False."""
    monitor = ProducerMonitor(local_node_id="artcb1node_local")
    assert monitor.current_producer() is None
    assert monitor.producer_is_dead() is False


def test_monitor_record_block_sets_producer() -> None:
    """record_block met à jour le producteur courant."""
    monitor = ProducerMonitor(local_node_id="artcb1node_local")
    monitor.record_block(
        node_id="artcb1node_primary",
        block_hash="abc123",
        block_index=5,
    )
    assert monitor.current_producer() == "artcb1node_primary"


def test_monitor_alive_producer_not_dead() -> None:
    """Producteur ayant battu récemment → producer_is_dead=False (I4)."""
    monitor = ProducerMonitor(local_node_id="artcb1node_local", heartbeat_timeout=120.0)
    monitor.record_block(
        node_id="artcb1node_primary",
        block_hash="abc123",
        block_index=5,
    )
    assert monitor.producer_is_dead() is False


def test_monitor_dead_producer_detected() -> None:
    """Producteur inactif > heartbeat_timeout → producer_is_dead=True."""
    monitor = ProducerMonitor(local_node_id="artcb1node_local", heartbeat_timeout=0.01)
    monitor.record_block(
        node_id="artcb1node_primary",
        block_hash="abc123",
        block_index=5,
    )
    time.sleep(0.05)  # Attendre que le heartbeat expire
    assert monitor.producer_is_dead() is True


def test_monitor_trigger_election_only_when_dead() -> None:
    """trigger_election retourne None si le producteur est vivant (I4)."""
    monitor = ProducerMonitor(local_node_id="artcb1node_backup_a", heartbeat_timeout=120.0)
    monitor.record_block(
        node_id="artcb1node_primary",
        block_hash="abc123",
        block_index=5,
    )
    result = monitor.trigger_election(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
    assert result is None


def test_monitor_trigger_election_when_dead() -> None:
    """trigger_election retourne ElectionResult quand le producteur est mort."""
    monitor = ProducerMonitor(local_node_id="artcb1node_backup_a", heartbeat_timeout=0.01)
    monitor.record_block(
        node_id="artcb1node_primary",
        block_hash="abc123",
        block_index=5,
    )
    time.sleep(0.05)
    result = monitor.trigger_election(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
    assert result is not None
    assert result.elected_node_id in CONSENSUS_NODES
    assert result.elected_node_id != "artcb1node_primary"


def test_monitor_new_producer_set_after_election() -> None:
    """Après l'élection, current_producer = nœud élu."""
    monitor = ProducerMonitor(local_node_id="artcb1node_backup_a", heartbeat_timeout=0.01)
    monitor.record_block(node_id="artcb1node_primary", block_hash="abc", block_index=1)
    time.sleep(0.05)
    result = monitor.trigger_election(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
    assert result is not None
    assert monitor.current_producer() == result.elected_node_id


# ── Invariant I1 — pas de double producteur ────────────────────────────────────

def test_no_double_producer_same_tip() -> None:
    """I1 : Deux nœuds faisant l'élection sur le même tip élisent le même nœud."""
    # Nœud A calcule l'élection
    result_a = elect_producer(
        consensus_nodes=CONSENSUS_NODES,
        tip_hash=TIP_HASH,
        exclude_node_id="artcb1node_primary",
    )
    # Nœud B calcule l'élection indépendamment
    result_b = elect_producer(
        consensus_nodes=CONSENSUS_NODES,
        tip_hash=TIP_HASH,
        exclude_node_id="artcb1node_primary",
    )
    # Les deux arrivent au même résultat → un seul producteur
    assert result_a.elected_node_id == result_b.elected_node_id, (
        "I1 VIOLÉ : deux nœuds ont élu des producteurs différents sur le même tip"
    )


def test_no_double_producer_different_exclusions() -> None:
    """I1 : même exclusion → même élu (les deux nœuds voient le même mort)."""
    dead = "artcb1node_primary"
    results = [
        elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH, exclude_node_id=dead)
        for _ in range(5)
    ]
    elected_set = {r.elected_node_id for r in results}
    assert len(elected_set) == 1, f"I1 VIOLÉ : plusieurs élus différents : {elected_set}"


# ── Invariant I2 — reproductibilité ──────────────────────────────────────────

def test_election_reproducible_with_same_inputs() -> None:
    """I2 : inputs identiques → résultat identique (100 itérations)."""
    first = elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
    for _ in range(99):
        r = elect_producer(consensus_nodes=CONSENSUS_NODES, tip_hash=TIP_HASH)
        assert r.elected_node_id == first.elected_node_id


# ── status() ─────────────────────────────────────────────────────────────────

def test_monitor_status_structure() -> None:
    """status() retourne la structure attendue."""
    monitor = ProducerMonitor(local_node_id="artcb1node_local", heartbeat_timeout=60.0)
    monitor.record_block(node_id="artcb1node_primary", block_hash="xyz", block_index=10)
    s = monitor.status()
    assert "local_node_id" in s
    assert "current_producer" in s
    assert "producer_alive" in s
    assert "known_producers" in s
    assert "artcb1node_primary" in s["known_producers"]


def test_monitor_last_heartbeat() -> None:
    """last_heartbeat retourne le dernier battement enregistré."""
    monitor = ProducerMonitor(local_node_id="artcb1node_local")
    monitor.record_block(node_id="artcb1node_primary", block_hash="abc", block_index=3)
    hb = monitor.last_heartbeat("artcb1node_primary")
    assert hb is not None
    assert hb.last_block_hash == "abc"
    assert hb.last_block_index == 3
    assert hb.is_alive(120.0) is True
