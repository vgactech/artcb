"""Tests GO-G — Reasoning Fee (transfert wallet→wallet, jamais mint).

Vérifie :
- BaseAccessFee au CONSULT : transfert consultant → producteur
- UsageBonus au USE : proportionnel au delta, plafonné
- fee_type = "transfer" toujours (invariant GO-G)
- Supply totale conservée (pas de mint)
- InsufficientFundsError si solde insuffisant
- delta <= 0 → pas de bonus
- Paramètres configurables via env
"""

from __future__ import annotations

import pytest

from artcb.kcg.fee import (
    KCGFeeEngine,
    KCGLedger,
    FeeResult,
    InsufficientFundsError,
)


ALICE = "artcb1alice_producer"
BOB   = "artcb1bob_consultant"


def _engine() -> KCGFeeEngine:
    return KCGFeeEngine()


def _ledger(alice_bal: int = 0, bob_bal: int = 10_000) -> KCGLedger:
    return KCGLedger({ALICE: alice_bal, BOB: bob_bal})


# ── Invariant GO-G : fee_type = "transfer" ───────────────────────────────────

def test_fee_type_is_always_transfer() -> None:
    engine = _engine()
    ledger = _ledger(bob_bal=10_000)
    result = engine.apply_consult_fee("C_001", "K_abc", BOB, ALICE, ledger)
    assert result.fee_type == "transfer", "GO-G : fee_type doit être 'transfer', jamais 'mint'"


# ── Supply conservée ──────────────────────────────────────────────────────────

def test_supply_conserved_after_consult_fee(monkeypatch) -> None:
    """La somme des soldes est identique avant et après le transfert."""
    monkeypatch.setenv("ARTCB_KCG_BASE_ACCESS_FEE_SATOSHI", "100")
    engine = _engine()
    ledger = _ledger(alice_bal=0, bob_bal=1_000)
    total_before = sum(ledger.all_balances().values())
    result = engine.apply_consult_fee("C_supply", "K_abc", BOB, ALICE, ledger)
    assert result.ok is True
    total_after = sum(ledger.all_balances().values())
    assert total_before == total_after, "Supply conservée : pas de mint GO-G"


def test_supply_conserved_after_use_bonus(monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_KCG_USAGE_BONUS_PER_DELTA_SATOSHI", "10")
    engine = _engine()
    ledger = _ledger(alice_bal=0, bob_bal=5_000)
    total_before = sum(ledger.all_balances().values())
    engine.apply_use_bonus("U_supply", "K_abc", BOB, ALICE, 20.0, ledger)
    total_after = sum(ledger.all_balances().values())
    assert total_before == total_after


# ── BaseAccessFee ─────────────────────────────────────────────────────────────

def test_consult_fee_transfers_correct_amount(monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_KCG_BASE_ACCESS_FEE_SATOSHI", "100")
    engine = _engine()
    ledger = _ledger(alice_bal=0, bob_bal=1_000)
    result = engine.apply_consult_fee("C_001", "K_abc", BOB, ALICE, ledger)
    assert result.ok is True
    assert result.amount_satoshi == 100
    assert ledger.balance(BOB) == 900
    assert ledger.balance(ALICE) == 100


def test_consult_fee_insufficient_funds(monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_KCG_BASE_ACCESS_FEE_SATOSHI", "500")
    engine = _engine()
    ledger = _ledger(alice_bal=0, bob_bal=10)  # solde insuffisant
    result = engine.apply_consult_fee("C_broke", "K_abc", BOB, ALICE, ledger)
    assert result.ok is False
    assert "insuffisant" in result.reason.lower()
    # Aucun transfert effectué
    assert ledger.balance(BOB) == 10
    assert ledger.balance(ALICE) == 0


def test_consult_fee_zero_config(monkeypatch) -> None:
    """Si fee configuré à 0, le CONSULT passe sans transfert."""
    monkeypatch.setenv("ARTCB_KCG_BASE_ACCESS_FEE_SATOSHI", "0")
    engine = _engine()
    ledger = _ledger(alice_bal=0, bob_bal=1_000)
    result = engine.apply_consult_fee("C_free", "K_abc", BOB, ALICE, ledger)
    assert result.ok is True
    assert result.amount_satoshi == 0
    assert ledger.balance(BOB) == 1_000  # pas de transfert


# ── UsageBonus ────────────────────────────────────────────────────────────────

def test_use_bonus_proportional_to_delta(monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_KCG_USAGE_BONUS_PER_DELTA_SATOSHI", "10")
    monkeypatch.setenv("ARTCB_KCG_MAX_FEE_SATOSHI", "100000")
    engine = _engine()
    ledger = _ledger(alice_bal=0, bob_bal=5_000)
    result = engine.apply_use_bonus("U_001", "K_abc", BOB, ALICE, 20.0, ledger)
    assert result.ok is True
    assert result.amount_satoshi == 200  # 20 * 10


def test_use_bonus_zero_for_no_delta(monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_KCG_USAGE_BONUS_PER_DELTA_SATOSHI", "10")
    engine = _engine()
    ledger = _ledger(alice_bal=0, bob_bal=5_000)
    result = engine.apply_use_bonus("U_nodelta", "K_abc", BOB, ALICE, 0.0, ledger)
    assert result.ok is True
    assert result.amount_satoshi == 0
    assert result.reason == "no_utility_delta"


def test_use_bonus_negative_delta_no_transfer(monkeypatch) -> None:
    """delta négatif = pas de bonus (utilisation contre-productive)."""
    engine = _engine()
    ledger = _ledger(alice_bal=0, bob_bal=5_000)
    result = engine.apply_use_bonus("U_neg", "K_abc", BOB, ALICE, -5.0, ledger)
    assert result.ok is True
    assert result.amount_satoshi == 0


def test_use_bonus_capped_at_max(monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_KCG_USAGE_BONUS_PER_DELTA_SATOSHI", "1000")
    monkeypatch.setenv("ARTCB_KCG_MAX_FEE_SATOSHI", "500")
    engine = _engine()
    ledger = _ledger(alice_bal=0, bob_bal=100_000)
    result = engine.apply_use_bonus("U_capped", "K_abc", BOB, ALICE, 999.0, ledger)
    assert result.ok is True
    assert result.amount_satoshi == 500  # plafonné


# ── Ledger ────────────────────────────────────────────────────────────────────

def test_ledger_transfer_ok() -> None:
    ledger = KCGLedger({"a": 1000, "b": 0})
    ledger.transfer("a", "b", 300)
    assert ledger.balance("a") == 700
    assert ledger.balance("b") == 300


def test_ledger_transfer_insufficient() -> None:
    ledger = KCGLedger({"a": 100})
    with pytest.raises(InsufficientFundsError):
        ledger.transfer("a", "b", 200)


def test_ledger_unknown_address_is_zero() -> None:
    ledger = KCGLedger()
    assert ledger.balance("artcb1unknown") == 0
