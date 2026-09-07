"""Tests GO-H — PoUC Challenge/Stake/Escrow.

Vérifie :
- Émission d'un challenge + dépôt stake en escrow
- Résolution PASS → stake retourné intégralement
- Résolution FAIL → pénalité partielle brûlée
- Résolution TIMEOUT → stake retourné (pas de pénalité)
- Invariant GO-H : fee_type jamais "mint"
- Double résolution → erreur
- Escrow solde insuffisant → erreur
"""

from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta

from artcb.kcg.pouc import (
    ChallengeStatus,
    EscrowStatus,
    PoUCEscrow,
    PoUCEngine,
)

ALICE = "artcb1alice_producer"
VERIF = "artcb1verifier"
K_ID  = "K_abc123def456"
G_ID  = "g_test_pouc"


def _engine(alice_stake: int = 10_000) -> tuple[PoUCEngine, PoUCEscrow]:
    escrow = PoUCEscrow()
    escrow.fund(ALICE, alice_stake)
    return PoUCEngine(escrow), escrow


# ── Émission challenge ────────────────────────────────────────────────────────

def test_issue_challenge_creates_locked_stake() -> None:
    engine, escrow = _engine(alice_stake=5_000)
    challenge, stake = engine.issue_challenge(
        K_ID, G_ID, ALICE, stake_satoshi=1_000, verifier_address=VERIF
    )
    assert challenge.challenge_id.startswith("CH_")
    assert challenge.status == ChallengeStatus.PENDING
    assert stake.escrow_status == EscrowStatus.LOCKED
    assert stake.amount_satoshi == 1_000
    # Le stake a été débité du compte Alice
    assert escrow.balance(ALICE) == 4_000


def test_issue_challenge_insufficient_escrow() -> None:
    engine, _ = _engine(alice_stake=100)
    with pytest.raises(ValueError, match="insuffisant"):
        engine.issue_challenge(K_ID, G_ID, ALICE, stake_satoshi=1_000)


# ── Résolution PASS ───────────────────────────────────────────────────────────

def test_resolve_pass_returns_stake(monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_POUC_DEFAULT_STAKE_SATOSHI", "1000")
    engine, escrow = _engine(alice_stake=5_000)
    challenge, stake = engine.issue_challenge(K_ID, G_ID, ALICE)
    result = engine.resolve(challenge.challenge_id, stake.stake_id, reproduction_score=0.85)
    assert result.status == ChallengeStatus.PASS
    assert result.stake_released_satoshi == 1_000
    assert result.penalty_satoshi == 0
    assert result.fee_type == "transfer_back"  # GO-H invariant : jamais "mint"
    # Le stake est retourné au producteur
    assert escrow.balance(ALICE) == 5_000


def test_resolve_pass_challenge_status_updated() -> None:
    engine, _ = _engine(5_000)
    challenge, stake = engine.issue_challenge(K_ID, G_ID, ALICE, stake_satoshi=500)
    engine.resolve(challenge.challenge_id, stake.stake_id, 0.9)
    resolved = engine.get_challenge(challenge.challenge_id)
    assert resolved.status == ChallengeStatus.PASS
    assert resolved.reproduction_score == pytest.approx(0.9)


# ── Résolution FAIL ───────────────────────────────────────────────────────────

def test_resolve_fail_penalizes_stake(monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_POUC_PENALTY_PCT", "0.1")
    engine, escrow = _engine(alice_stake=5_000)
    challenge, stake = engine.issue_challenge(K_ID, G_ID, ALICE, stake_satoshi=1_000)
    result = engine.resolve(challenge.challenge_id, stake.stake_id, reproduction_score=0.3)
    assert result.status == ChallengeStatus.FAIL
    assert result.penalty_satoshi == 100        # 10% de 1000
    assert result.stake_released_satoshi == 900  # 900 retournés
    assert result.fee_type == "penalty_partial"  # GO-H invariant : jamais "mint"
    # Alice récupère 900 (4000 + 900 = 4900)
    assert escrow.balance(ALICE) == 4_900


def test_resolve_fail_does_not_mint(monkeypatch) -> None:
    """Après FAIL, la supply totale (escrow+balances) ne doit pas augmenter."""
    monkeypatch.setenv("ARTCB_POUC_PENALTY_PCT", "0.2")
    engine, escrow = _engine(alice_stake=2_000)
    total_before = escrow.balance(ALICE)
    challenge, stake = engine.issue_challenge(K_ID, G_ID, ALICE, stake_satoshi=1_000)
    engine.resolve(challenge.challenge_id, stake.stake_id, reproduction_score=0.1)
    # total après = balance alice + stake brûlé (perdu) ≤ total avant
    total_after = escrow.balance(ALICE)
    assert total_after < total_before, "FAIL : Alice perd une partie de son stake"


# ── Résolution TIMEOUT ────────────────────────────────────────────────────────

def test_resolve_timeout_returns_full_stake(monkeypatch) -> None:
    """Un challenge expiré est résolu comme TIMEOUT — stake retourné sans pénalité."""
    monkeypatch.setenv("ARTCB_POUC_CHALLENGE_TIMEOUT_SECONDS", "1")
    engine, escrow = _engine(alice_stake=5_000)
    challenge, stake = engine.issue_challenge(K_ID, G_ID, ALICE, stake_satoshi=1_000)
    # Simuler expiration en modifiant expires_at
    from datetime import UTC, timedelta, datetime
    challenge.expires_at = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()

    result = engine.resolve(challenge.challenge_id, stake.stake_id, reproduction_score=0.0)
    assert result.status == ChallengeStatus.TIMEOUT
    assert result.penalty_satoshi == 0
    assert result.stake_released_satoshi == 1_000
    assert result.fee_type == "transfer_back"
    assert escrow.balance(ALICE) == 5_000  # intégralement retourné


# ── Double résolution ─────────────────────────────────────────────────────────

def test_double_resolution_raises(monkeypatch) -> None:
    engine, _ = _engine(5_000)
    challenge, stake = engine.issue_challenge(K_ID, G_ID, ALICE, stake_satoshi=500)
    engine.resolve(challenge.challenge_id, stake.stake_id, 0.9)
    with pytest.raises(ValueError, match="déjà résolu"):
        engine.resolve(challenge.challenge_id, stake.stake_id, 0.5)


# ── Invariant GO-H fee_type jamais "mint" ─────────────────────────────────────

def test_go_h_fee_type_never_mint(monkeypatch) -> None:
    engine, _ = _engine(5_000)
    challenge, stake = engine.issue_challenge(K_ID, G_ID, ALICE, stake_satoshi=1_000)
    result = engine.resolve(challenge.challenge_id, stake.stake_id, 0.8)
    assert result.fee_type != "mint", "GO-H invariant : fee_type ne doit jamais être 'mint'"
