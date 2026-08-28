"""Tests pré-filtrage Anti-Sybil avant attribution de job.

Principe vérifié : un wallet en cooldown ou suspendu ne doit JAMAIS
recevoir un job — ni travailler pour rien, ni faire annuler le bloc
des autres contributeurs éligibles.

Rapport 109.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from artcb.security.anti_sybil import AntiSybilValidator, ReputationScore
from artcb.mining.pipeline import build_contributors
from artcb.pool.service import PoolError, PoolService


# ── helpers ──────────────────────────────────────────────────────────────────

def _sybil(interval_s: int = 60) -> AntiSybilValidator:
    """Validator avec limite fixe (pas de mesure réseau en test)."""
    return AntiSybilValidator(
        min_pol_score=0.6,
        max_contributors_per_block=10,
        min_block_interval_seconds=interval_s,
    )


def _fresh(sybil: AntiSybilValidator, address: str, last_s_ago: int) -> None:
    """Simule qu'un wallet a miné il y a last_s_ago secondes."""
    if address not in sybil.reputation:
        sybil.reputation[address] = ReputationScore(address=address)
    sybil.reputation[address].last_block_time = (
        datetime.now(UTC) - timedelta(seconds=last_s_ago)
    )


# ── 1. is_eligible ────────────────────────────────────────────────────────────

def test_is_eligible_never_mined() -> None:
    """Un wallet qui n'a jamais miné est toujours éligible."""
    sybil = _sybil(60)
    ok, reason = sybil.is_eligible("artcb1alice")
    assert ok is True
    assert reason == "ok"


def test_is_eligible_after_cooldown() -> None:
    """Un wallet qui a miné il y a > 60s est éligible."""
    sybil = _sybil(60)
    _fresh(sybil, "artcb1alice", last_s_ago=90)
    ok, reason = sybil.is_eligible("artcb1alice")
    assert ok is True


def test_is_eligible_in_cooldown() -> None:
    """Un wallet qui a miné il y a < 60s est INÉLIGIBLE."""
    sybil = _sybil(60)
    _fresh(sybil, "artcb1bob", last_s_ago=30)
    ok, reason = sybil.is_eligible("artcb1bob")
    assert ok is False
    assert "cooldown" in reason
    assert "artcb1bob" in reason


def test_is_eligible_just_at_limit() -> None:
    """Exactement à la limite (60s) → inéligible (strict <)."""
    sybil = _sybil(60)
    _fresh(sybil, "artcb1carol", last_s_ago=60)
    ok, _ = sybil.is_eligible("artcb1carol")
    # 60s écoulées == 60s requises → elapsed (60) < limit (60) est False → éligible
    assert ok is True


def test_is_eligible_suspended() -> None:
    """Un wallet blacklisté est inéligible même si cooldown dépassé."""
    sybil = _sybil(60)
    sybil.blacklist_address("artcb1mallory", "attaque Sybil détectée")
    ok, reason = sybil.is_eligible("artcb1mallory")
    assert ok is False
    assert "blacklisté" in reason


# ── 2. filter_eligible_contributors ──────────────────────────────────────────

def test_filter_all_eligible() -> None:
    """Tous éligibles → liste inchangée, aucun exclu."""
    sybil = _sybil(60)
    candidates = [
        {"address": "artcb1alice", "pol_score": 0.8},
        {"address": "artcb1carol", "pol_score": 0.7},
    ]
    eligible, excluded = sybil.filter_eligible_contributors(candidates)
    assert len(eligible) == 2
    assert excluded == []


def test_filter_removes_cooldown_wallet() -> None:
    """Bob en cooldown est retiré — alice et carol restent."""
    sybil = _sybil(60)
    _fresh(sybil, "artcb1bob", last_s_ago=30)  # bob en cooldown
    candidates = [
        {"address": "artcb1alice", "pol_score": 0.8},
        {"address": "artcb1bob",   "pol_score": 0.7},   # ← inéligible
        {"address": "artcb1carol", "pol_score": 0.6},
    ]
    eligible, excluded = sybil.filter_eligible_contributors(candidates)
    assert len(eligible) == 2
    assert all(c["address"] != "artcb1bob" for c in eligible)
    assert len(excluded) == 1
    assert excluded[0]["address"] == "artcb1bob"
    assert "cooldown" in excluded[0]["reason"]


def test_filter_all_excluded_returns_empty() -> None:
    """Si tous en cooldown → liste vide (le pipeline gérera l'absence de contributeurs)."""
    sybil = _sybil(60)
    _fresh(sybil, "artcb1alice", last_s_ago=10)
    _fresh(sybil, "artcb1bob",   last_s_ago=20)
    candidates = [
        {"address": "artcb1alice", "pol_score": 0.8},
        {"address": "artcb1bob",   "pol_score": 0.7},
    ]
    eligible, excluded = sybil.filter_eligible_contributors(candidates)
    assert eligible == []
    assert len(excluded) == 2


# ── 3. build_contributors avec anti_sybil ────────────────────────────────────

def test_build_contributors_filters_cooldown() -> None:
    """build_contributors exclut le wallet en cooldown AVANT de retourner la liste."""
    sybil = _sybil(60)
    _fresh(sybil, "artcb1bob", last_s_ago=30)  # bob inéligible

    extras = [
        {"address": "artcb1bob",   "pol_score": 0.7, "role": "learner"},
        {"address": "artcb1carol", "pol_score": 0.65, "role": "learner"},
    ]
    result = build_contributors(
        actor_address="artcb1alice",
        pol_score=0.8,
        extra_contributors=extras,
        anti_sybil=sybil,
        source="mining",
    )
    addresses = [c["address"] for c in result]
    assert "artcb1bob" not in addresses, "bob en cooldown ne doit PAS être dans la liste"
    assert "artcb1alice" in addresses
    assert "artcb1carol" in addresses


def test_build_contributors_no_sybil_unchanged() -> None:
    """Sans anti_sybil, build_contributors se comporte comme avant (rétrocompat)."""
    result = build_contributors(
        actor_address="artcb1alice",
        pol_score=0.8,
        extra_contributors=[{"address": "artcb1bob", "pol_score": 0.7}],
    )
    # Sans anti_sybil → pas de filtrage
    assert any(c["address"] == "artcb1bob" for c in result)
    assert any(c["address"] == "artcb1alice" for c in result)


# ── 4. PoolService.create_job avec anti_sybil ────────────────────────────────

def test_pool_create_job_filters_cooldown_worker(tmp_path) -> None:
    """create_job exclut les workers en cooldown AVANT d'attribuer les chunks."""
    sybil = _sybil(60)
    _fresh(sybil, "addr_bob_node", last_s_ago=20)  # node de bob en cooldown

    service = PoolService(
        tmp_path,
        node_id="node_owner",
        kem_public_hex="a" * 64,
        kem_secret_hex="b" * 64,
        run_reasoning=lambda t: {
            "graph_id": "g_test", "pol_score": 0.7, "graph_root": "root", "node_count": 5
        },
    )
    workers = [
        {"node_id": "node_alice", "kem_public_hex": "c" * 64, "contributor_address": "artcb1alice"},
        {"node_id": "node_bob",   "kem_public_hex": "d" * 64, "contributor_address": "addr_bob_node"},
    ]
    job = service.create_job(
        "texte test",
        workers=workers,
        anti_sybil=sybil,
        source="mining",
    )
    # Tous les chunks doivent être assignés à alice uniquement
    for chunk in job.chunks:
        assert chunk.worker_node_id == "node_alice", (
            f"chunk attribué à {chunk.worker_node_id} — bob ne devait pas recevoir de job"
        )


def test_pool_create_job_raises_if_no_eligible_worker(tmp_path) -> None:
    """Si aucun worker éligible, PoolError explicite — pas de bloc vide."""
    sybil = _sybil(60)
    _fresh(sybil, "artcb1alice", last_s_ago=10)
    _fresh(sybil, "artcb1bob",   last_s_ago=20)

    service = PoolService(
        tmp_path,
        node_id="node_owner",
        kem_public_hex="a" * 64,
        kem_secret_hex="b" * 64,
        run_reasoning=lambda t: {},
    )
    workers = [
        {"node_id": "node_alice", "kem_public_hex": "c" * 64, "contributor_address": "artcb1alice"},
        {"node_id": "node_bob",   "kem_public_hex": "d" * 64, "contributor_address": "artcb1bob"},
    ]
    with pytest.raises(PoolError, match="Aucun worker éligible"):
        service.create_job("texte", workers=workers, anti_sybil=sybil)


def test_fleet_same_owner_different_machines_is_not_sybil() -> None:
    sybil = _sybil(0)
    ok, reason = sybil.validate_block(
        [
            {"address": "A", "pol_score": 0.8, "machine_id": "A:M1", "role": "worker"},
            {"address": "A", "pol_score": 0.8, "machine_id": "A:M2", "role": "worker"},
            {"address": "JP1", "pol_score": 0.8, "role": "provider"},
            {"address": "JP2", "pol_score": 0.8, "role": "provider"},
        ],
        0.8,
        0,
        source="mining",
    )
    assert ok is True
    assert reason is None


def test_true_duplicate_contributor_identity_rejected() -> None:
    sybil = _sybil(0)
    ok, reason = sybil.validate_block(
        [
            {"address": "A", "pol_score": 0.8, "machine_id": "A:M1", "role": "worker"},
            {"address": "A", "pol_score": 0.8, "machine_id": "A:M1", "role": "worker"},
        ],
        0.8,
        0,
        source="mining",
    )
    assert ok is False
    assert "Duplicate" in (reason or "")
