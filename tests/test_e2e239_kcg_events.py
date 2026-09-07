"""Tests GO-F — KCG événements CONSULT/USE sans fee.

Vérifie :
- Publication d'une entrée de connaissance (KnowledgeEntry)
- Enregistrement d'un événement CONSULT
- Enregistrement d'un événement USE avec mesure de delta
- Idempotence publication (pas de doublon)
- Stats globales KCG
- knowledge_id dérivé depuis graph_id (stable)
- round-trip JSONL (persist → reload)
"""

from __future__ import annotations

import pytest
from pathlib import Path

from artcb.kcg.events import (
    ConsultEvent,
    KnowledgeEntry,
    UseEvent,
    knowledge_id,
)
from artcb.kcg.store import KCGIndex, KCGStore


def _store(tmp_path: Path) -> KCGStore:
    return KCGStore(tmp_path)


def _index(tmp_path: Path) -> KCGIndex:
    return KCGIndex(_store(tmp_path))


# ── knowledge_id ─────────────────────────────────────────────────────────────

def test_knowledge_id_stable() -> None:
    """knowledge_id est déterministe depuis graph_id."""
    kid = knowledge_id("g_abc123")
    assert kid.startswith("K_")
    assert knowledge_id("g_abc123") == kid  # stable


def test_knowledge_id_distinct() -> None:
    assert knowledge_id("g_abc") != knowledge_id("g_def")


# ── KnowledgeEntry ────────────────────────────────────────────────────────────

def test_publish_knowledge(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    entry = KnowledgeEntry(
        knowledge_id=knowledge_id("g_test1"),
        graph_id="g_test1",
        producer_address="artcb1alice",
        pol_block_index=3,
        pol_score=0.75,
        title="Test knowledge 1",
    )
    saved = idx.publish(entry)
    assert saved.knowledge_id == knowledge_id("g_test1")
    assert saved.producer_address == "artcb1alice"
    assert saved.pol_score == 0.75


def test_publish_idempotent(tmp_path: Path) -> None:
    """Publier deux fois le même knowledge_id ne crée pas de doublon."""
    idx = _index(tmp_path)
    kid = knowledge_id("g_idem")
    entry = KnowledgeEntry(
        knowledge_id=kid,
        graph_id="g_idem",
        producer_address="artcb1bob",
        pol_block_index=1,
        pol_score=0.6,
    )
    idx.publish(entry)
    idx.publish(entry)  # doublon ignoré
    all_k = idx.all()
    assert len([e for e in all_k if e.knowledge_id == kid]) == 1


# ── ConsultEvent ──────────────────────────────────────────────────────────────

def test_consult_event(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    kid = knowledge_id("g_consult_test")
    idx.publish(KnowledgeEntry(
        knowledge_id=kid, graph_id="g_consult_test",
        producer_address="artcb1alice", pol_block_index=1, pol_score=0.7,
    ))
    event = ConsultEvent(
        knowledge_id=kid,
        graph_id="g_consult_test",
        consultant_address="artcb1bob",
        agent_id="bob_agent_235",
        session_id="sess_235",
        fee_pending=False,       # GO-F : pas de fee
        fee_amount_satoshi=0,
    )
    saved = idx.consult(event)
    assert saved.consult_id.startswith("C_")
    assert saved.fee_pending is False        # GO-F : jamais True
    assert saved.fee_amount_satoshi == 0     # GO-F : pas de fee


def test_consult_increments_count(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    kid = knowledge_id("g_count_test")
    idx.publish(KnowledgeEntry(
        knowledge_id=kid, graph_id="g_count_test",
        producer_address="artcb1alice", pol_block_index=2, pol_score=0.8,
    ))
    assert idx.get(kid).consult_count == 0
    idx.consult(ConsultEvent(knowledge_id=kid, graph_id="g_count_test",
                             consultant_address="artcb1bob"))
    idx.consult(ConsultEvent(knowledge_id=kid, graph_id="g_count_test",
                             consultant_address="artcb1claire"))
    assert idx.get(kid).consult_count == 2


# ── UseEvent ──────────────────────────────────────────────────────────────────

def test_use_event_with_delta(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    kid = knowledge_id("g_use_delta")
    idx.publish(KnowledgeEntry(
        knowledge_id=kid, graph_id="g_use_delta",
        producer_address="artcb1alice", pol_block_index=1, pol_score=0.7,
    ))
    event = UseEvent(
        knowledge_id=kid,
        graph_id="g_use_delta",
        consumer_address="artcb1bob",
        score_before=70.0,
        score_after=90.0,
    )
    saved = idx.use(event)
    assert saved.usage_id.startswith("U_")
    assert saved.delta_utility == pytest.approx(20.0)
    assert saved.utility_measured is True


def test_use_event_without_delta(tmp_path: Path) -> None:
    """USE sans mesure — delta=0, utility_measured=False."""
    idx = _index(tmp_path)
    kid = knowledge_id("g_use_nodelta")
    idx.publish(KnowledgeEntry(
        knowledge_id=kid, graph_id="g_use_nodelta",
        producer_address="artcb1alice", pol_block_index=1, pol_score=0.6,
    ))
    event = UseEvent(
        knowledge_id=kid,
        graph_id="g_use_nodelta",
        consumer_address="artcb1bob",
    )
    saved = idx.use(event)
    assert saved.delta_utility == 0.0
    assert saved.utility_measured is False


def test_reputation_update_after_use(tmp_path: Path) -> None:
    """Réputation = total_delta_utility / use_count."""
    idx = _index(tmp_path)
    kid = knowledge_id("g_rep_test")
    idx.publish(KnowledgeEntry(
        knowledge_id=kid, graph_id="g_rep_test",
        producer_address="artcb1alice", pol_block_index=1, pol_score=0.7,
    ))
    idx.use(UseEvent(knowledge_id=kid, graph_id="g_rep_test",
                     consumer_address="artcb1bob",
                     score_before=60.0, score_after=80.0))   # delta=20
    idx.use(UseEvent(knowledge_id=kid, graph_id="g_rep_test",
                     consumer_address="artcb1claire",
                     score_before=70.0, score_after=90.0))   # delta=20
    entry = idx.get(kid)
    assert entry.use_count == 2
    assert entry.total_delta_utility == pytest.approx(40.0)
    assert entry.reputation_score == pytest.approx(20.0)


# ── Persistence JSONL ─────────────────────────────────────────────────────────

def test_persistence_reload(tmp_path: Path) -> None:
    """Les événements survivent à un rechargement depuis disque."""
    idx = _index(tmp_path)
    kid = knowledge_id("g_persist")
    idx.publish(KnowledgeEntry(
        knowledge_id=kid, graph_id="g_persist",
        producer_address="artcb1alice", pol_block_index=1, pol_score=0.7,
    ))
    idx.consult(ConsultEvent(knowledge_id=kid, graph_id="g_persist",
                             consultant_address="artcb1bob"))
    idx.use(UseEvent(knowledge_id=kid, graph_id="g_persist",
                     consumer_address="artcb1bob",
                     score_before=50.0, score_after=75.0))

    # Rechargement depuis disque
    idx2 = _index(tmp_path)
    entry = idx2.get(kid)
    assert entry is not None
    assert entry.consult_count == 1
    assert entry.use_count == 1
    assert entry.total_delta_utility == pytest.approx(25.0)


# ── Stats globales ────────────────────────────────────────────────────────────

def test_global_stats(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    for i in range(3):
        gid = f"g_stats_{i}"
        kid = knowledge_id(gid)
        idx.publish(KnowledgeEntry(
            knowledge_id=kid, graph_id=gid,
            producer_address=f"artcb1producer{i}", pol_block_index=i, pol_score=0.6 + i * 0.1,
        ))
        idx.consult(ConsultEvent(knowledge_id=kid, graph_id=gid,
                                 consultant_address="artcb1user"))
    stats = idx.stats()
    assert stats["knowledge_count"] == 3
    assert stats["total_consults"] == 3
    assert stats["total_uses"] == 0


# ── GO-F invariant : fee toujours nul ─────────────────────────────────────────

def test_go_f_no_fee(tmp_path: Path) -> None:
    """GO-F garantit que fee_pending=False et fee_amount_satoshi=0."""
    idx = _index(tmp_path)
    kid = knowledge_id("g_nofee")
    idx.publish(KnowledgeEntry(
        knowledge_id=kid, graph_id="g_nofee",
        producer_address="artcb1alice", pol_block_index=1, pol_score=0.7,
    ))
    event = ConsultEvent(
        knowledge_id=kid, graph_id="g_nofee",
        consultant_address="artcb1bob",
    )
    saved = idx.consult(event)
    assert saved.fee_pending is False, "GO-F : fee_pending doit être False (GO-G activera)"
    assert saved.fee_amount_satoshi == 0, "GO-F : aucun fee tant que GO-G n'est pas actif"
