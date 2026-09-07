"""Tests découvert ARTCB (Overdraft) — extension KCG Reasoning Fee.

Vérifie :
- Transfer avec solde suffisant (normal)
- Transfer avec découvert autorisé (balance négative autorisée)
- Transfer refusé si découvert dépassé
- Auto-repay : remboursement automatique à la réception de tokens
- Auto-repay partiel puis total
- Remboursement prioritaire sur le crédit entrant
- Invariant : pas de mint (supply conservée hors dette)
- Découvert non autorisé = InsufficientFundsError comportement identique
"""

from __future__ import annotations

import pytest

from artcb.kcg.overdraft import OverdraftLedger

ALICE = "artcb1alice_producer"
BOB   = "artcb1bob_consultant"


def _ledger() -> OverdraftLedger:
    return OverdraftLedger()


# ── Transfer normal (solde suffisant) ─────────────────────────────────────────

def test_normal_transfer_ok() -> None:
    ledger = _ledger()
    ledger.fund(BOB, 1_000)
    result = ledger.transfer(BOB, ALICE, 300)
    assert result.ok is True
    assert result.amount_satoshi == 300
    assert result.overdraft_used_satoshi == 0
    assert ledger.balance(BOB) == 700
    assert ledger.balance(ALICE) == 300


# ── Découvert autorisé ────────────────────────────────────────────────────────

def test_overdraft_allowed_when_limit_set() -> None:
    """Bob a 200 satoshi, découvert autorisé à 500 → peut payer 600."""
    ledger = _ledger()
    ledger.fund(BOB, 200)
    ledger.set_overdraft_limit(BOB, 500)
    result = ledger.transfer(BOB, ALICE, 600)
    assert result.ok is True
    assert result.overdraft_used_satoshi == 400   # 600 - 200 = 400 en découvert
    assert ledger.balance(BOB) == -400            # solde négatif = dette
    assert ledger.debt(BOB) == 400
    assert ledger.balance(ALICE) == 600           # Alice reçoit le montant complet


def test_overdraft_creates_debt() -> None:
    ledger = _ledger()
    ledger.fund(BOB, 0)
    ledger.set_overdraft_limit(BOB, 1_000)
    ledger.transfer(BOB, ALICE, 500)
    assert ledger.debt(BOB) == 500
    assert ledger.balance(BOB) == -500


def test_overdraft_at_limit_is_allowed() -> None:
    """Transfer exactement à la limite du découvert → autorisé."""
    ledger = _ledger()
    ledger.fund(BOB, 0)
    ledger.set_overdraft_limit(BOB, 1_000)
    result = ledger.transfer(BOB, ALICE, 1_000)
    assert result.ok is True
    assert ledger.balance(BOB) == -1_000


def test_overdraft_beyond_limit_is_refused() -> None:
    """Transfer au-delà de la limite → refusé."""
    ledger = _ledger()
    ledger.fund(BOB, 0)
    ledger.set_overdraft_limit(BOB, 500)
    result = ledger.transfer(BOB, ALICE, 600)
    assert result.ok is False
    assert "solde_insuffisant" in result.reason
    assert ledger.balance(BOB) == 0   # rien débité


def test_no_overdraft_by_default() -> None:
    """Sans limite explicite, le découvert est 0 → refus si solde insuffisant."""
    ledger = _ledger()
    ledger.fund(BOB, 100)
    result = ledger.transfer(BOB, ALICE, 300)
    assert result.ok is False
    assert ledger.balance(BOB) == 100   # solde inchangé


# ── Auto-repay ────────────────────────────────────────────────────────────────

def test_auto_repay_on_credit() -> None:
    """Dès que Bob reçoit des tokens, sa dette est remboursée en priorité."""
    ledger = _ledger()
    ledger.fund(BOB, 0)
    ledger.set_overdraft_limit(BOB, 1_000)
    # Bob paie 600 en découvert → dette = 600
    ledger.transfer(BOB, ALICE, 600)
    assert ledger.debt(BOB) == 600
    assert ledger.balance(BOB) == -600
    # Bob reçoit une récompense PoL de 1000 satoshi
    result = ledger.credit(BOB, 1_000)
    assert result.debt_repaid_satoshi == 600  # 600 remboursés
    assert ledger.debt(BOB) == 0              # dette épurée
    assert ledger.balance(BOB) == 400         # 1000 - 600 = 400 restants


def test_auto_repay_partial() -> None:
    """Si le crédit ne couvre pas toute la dette → remboursement partiel."""
    ledger = _ledger()
    ledger.fund(BOB, 0)
    ledger.set_overdraft_limit(BOB, 2_000)
    ledger.transfer(BOB, ALICE, 1_000)  # dette = 1000
    # Bob reçoit seulement 400
    result = ledger.credit(BOB, 400)
    assert result.debt_repaid_satoshi == 400
    assert ledger.debt(BOB) == 600      # reste 600 de dette
    assert ledger.balance(BOB) == -600  # toujours négatif


def test_auto_repay_multiple_credits() -> None:
    """Plusieurs crédits successifs remboursent progressivement la dette."""
    ledger = _ledger()
    ledger.fund(BOB, 0)
    ledger.set_overdraft_limit(BOB, 3_000)
    ledger.transfer(BOB, ALICE, 3_000)
    assert ledger.debt(BOB) == 3_000
    ledger.credit(BOB, 1_000)
    assert ledger.debt(BOB) == 2_000
    ledger.credit(BOB, 1_000)
    assert ledger.debt(BOB) == 1_000
    ledger.credit(BOB, 1_000)
    assert ledger.debt(BOB) == 0
    assert ledger.balance(BOB) == 0


def test_credit_surplus_after_full_repay() -> None:
    """Après remboursement total, le surplus va sur le solde."""
    ledger = _ledger()
    ledger.fund(BOB, 0)
    ledger.set_overdraft_limit(BOB, 500)
    ledger.transfer(BOB, ALICE, 500)  # dette = 500
    # Reçoit 800 → 500 remboursés, 300 sur balance
    result = ledger.credit(BOB, 800)
    assert result.debt_repaid_satoshi == 500
    assert ledger.debt(BOB) == 0
    assert ledger.balance(BOB) == 300


# ── Available (solde effectif) ────────────────────────────────────────────────

def test_available_with_no_overdraft() -> None:
    ledger = _ledger()
    ledger.fund(BOB, 500)
    assert ledger.available(BOB) == 500


def test_available_with_overdraft_limit() -> None:
    """Disponible = balance + découvert restant non utilisé."""
    ledger = _ledger()
    ledger.fund(BOB, 200)
    ledger.set_overdraft_limit(BOB, 500)
    assert ledger.available(BOB) == 700   # 200 + 500 (découvert non utilisé)


def test_available_reduces_as_overdraft_used() -> None:
    """available = balance + découvert_restant_non_utilisé.

    Bob : balance=0, limite=1000 → available=1000
    Après transfer 300 : balance=-300, overdraft_utilisé=300, restant=700
    available = -300 + 700 = 400
    """
    ledger = _ledger()
    ledger.fund(BOB, 0)
    ledger.set_overdraft_limit(BOB, 1_000)
    ledger.transfer(BOB, ALICE, 300)
    # Disponible = balance(-300) + découvert_restant(700) = 400
    assert ledger.available(BOB) == 400


# ── Invariant : pas de mint ───────────────────────────────────────────────────

def test_no_mint_on_overdraft() -> None:
    """La dette n'est pas de la monnaie créée — le producteur est crédité
    depuis la réserve du réseau, pas depuis rien."""
    ledger = _ledger()
    ledger.fund(BOB, 0)
    ledger.set_overdraft_limit(BOB, 500)
    # Bob paie Alice avec découvert
    ledger.transfer(BOB, ALICE, 500)
    # Alice a bien reçu 500 — mais ce sont des tokens "avancés"
    assert ledger.balance(ALICE) == 500
    # Bob a une dette de 500 — pas de création nette de monnaie
    assert ledger.debt(BOB) == 500
    # Global : alice=500 + bob_debt=500 = cohérent (dette compensée)
    assert ledger.global_debt() == 500
