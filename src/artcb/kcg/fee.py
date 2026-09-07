"""KCG Reasoning Fee — GO-G 2026-09-07.

ReasoningFee = transfert wallet→wallet (jamais de mint).
Deux composantes (§45 rapport 237) :
  BaseAccessFee   — petit frais fixe au moment du CONSULT
  UsageBonus      — récompense supplémentaire si utilité prouvée (USE + delta > 0)

Principe :
  - Le consultant paie le producteur en ARTCB (satoshi)
  - Le transfert est enregistré dans le ledger ARTCB (pas une nouvelle émission)
  - Le plafond 21M ARTCB est respecté
  - Découvert ARTCB : un wallet peut passer en négatif jusqu'à sa limite autorisée.
    La dette est remboursée automatiquement dès réception de tokens (auto_repay).
    C'est une dette enregistrée, pas du mint.
  - Taux configurables par variable d'env ou Doppler (jamais gelés en dur)

GO-G invariant :
  - fee_type = "transfer"   (jamais "mint")
  - fee_active = True
  - Les GOs F+G+H = paquet GO-L

Intégration :
  - KCGFeeEngine.apply_consult_fee(consult_event, ledger) → FeeResult
  - KCGFeeEngine.apply_use_bonus(use_event, ledger)        → FeeResult
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("artcb.kcg.fee")

# ── Paramètres du Reasoning Fee (configurables Doppler) ──────────────────────
# Ces valeurs sont des paramètres économiques, pas des constantes de consensus.
# Ils PEUVENT être modifiés par l'opérateur sans fork protocole.

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def base_access_fee_satoshi() -> int:
    """Frais d'accès de base en satoshi ARTCB (1 satoshi = 1e-8 ARTCB)."""
    return _env_int("ARTCB_KCG_BASE_ACCESS_FEE_SATOSHI", 100)   # 0,000001 ARTCB par défaut


def usage_bonus_satoshi_per_delta() -> int:
    """Satoshi supplémentaires par unité de delta_utility prouvée."""
    return _env_int("ARTCB_KCG_USAGE_BONUS_PER_DELTA_SATOSHI", 10)  # 10 satoshi / delta unit


def max_fee_satoshi() -> int:
    """Plafond absolu du Reasoning Fee (protège contre overflow de delta)."""
    return _env_int("ARTCB_KCG_MAX_FEE_SATOSHI", 100_000)  # 0.001 ARTCB max


# ── Modèles ──────────────────────────────────────────────────────────────────

@dataclass
class FeeResult:
    """Résultat d'une opération de Reasoning Fee."""
    ok: bool
    fee_type: str = "transfer"   # TOUJOURS "transfer" — jamais "mint" (GO-G invariant)
    amount_satoshi: int = 0
    from_address: str = ""       # wallet consultant
    to_address: str = ""         # wallet producteur
    knowledge_id: str = ""
    event_id: str = ""           # consult_id ou usage_id
    reason: str = ""             # motif si ok=False
    balance_before_from: int = 0
    balance_after_from: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "fee_type": self.fee_type,
            "amount_satoshi": self.amount_satoshi,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "knowledge_id": self.knowledge_id,
            "event_id": self.event_id,
            "reason": self.reason,
        }


class InsufficientFundsError(Exception):
    """Le consultant n'a pas les fonds pour payer le Reasoning Fee."""


# ── Ledger minimal (interface — le vrai ledger est dans economics/) ──────────

class KCGLedger:
    """Ledger simplifié pour les transferts Reasoning Fee.

    Interface minimale — peut être substituée par le vrai ledger ARTCB
    en production. Utilise un dict mémoire en test.
    """

    def __init__(self, balances: dict[str, int] | None = None) -> None:
        self._balances: dict[str, int] = dict(balances or {})

    def balance(self, address: str) -> int:
        return self._balances.get(address, 0)

    def transfer(self, from_addr: str, to_addr: str, amount_satoshi: int) -> None:
        """Transfère amount_satoshi de from_addr vers to_addr.

        Raises InsufficientFundsError si solde insuffisant.
        """
        if amount_satoshi <= 0:
            return
        bal = self.balance(from_addr)
        if bal < amount_satoshi:
            raise InsufficientFundsError(
                f"{from_addr} solde={bal} satoshi insuffisant pour fee={amount_satoshi}"
            )
        self._balances[from_addr] = bal - amount_satoshi
        self._balances[to_addr] = self.balance(to_addr) + amount_satoshi

    def all_balances(self) -> dict[str, int]:
        return dict(self._balances)


# ── Moteur de fee ─────────────────────────────────────────────────────────────

class KCGFeeEngine:
    """Applique le Reasoning Fee sur les événements KCG.

    GO-G invariant : fee_type = "transfer" uniquement.
    La supply totale est conservée à chaque transfert.
    """

    def apply_consult_fee(
        self,
        consult_id: str,
        knowledge_id: str,
        consultant_address: str,
        producer_address: str,
        ledger: KCGLedger,
    ) -> FeeResult:
        """Applique le BaseAccessFee au moment du CONSULT.

        Transfert : consultant → producteur.
        Retourne FeeResult(ok=False) si fonds insuffisants (le CONSULT n'est
        pas enregistré — c'est à l'appelant de gérer le rejet).
        """
        amount = min(base_access_fee_satoshi(), max_fee_satoshi())
        if amount == 0:
            return FeeResult(
                ok=True, amount_satoshi=0,
                from_address=consultant_address, to_address=producer_address,
                knowledge_id=knowledge_id, event_id=consult_id,
                reason="fee_zero_config",
            )
        bal_before = ledger.balance(consultant_address)
        try:
            ledger.transfer(consultant_address, producer_address, amount)
        except InsufficientFundsError as exc:
            logger.warning("KCG Reasoning Fee CONSULT refusé : %s", exc)
            return FeeResult(
                ok=False, amount_satoshi=amount,
                from_address=consultant_address, to_address=producer_address,
                knowledge_id=knowledge_id, event_id=consult_id,
                reason=str(exc),
                balance_before_from=bal_before,
            )
        logger.info(
            "KCG Reasoning Fee CONSULT : %s → %s %d satoshi (knowledge=%s)",
            consultant_address[:12], producer_address[:12], amount, knowledge_id,
        )
        return FeeResult(
            ok=True, amount_satoshi=amount,
            from_address=consultant_address, to_address=producer_address,
            knowledge_id=knowledge_id, event_id=consult_id,
            balance_before_from=bal_before,
            balance_after_from=ledger.balance(consultant_address),
        )

    def apply_use_bonus(
        self,
        usage_id: str,
        knowledge_id: str,
        consumer_address: str,
        producer_address: str,
        delta_utility: float,
        ledger: KCGLedger,
    ) -> FeeResult:
        """Applique le UsageBonus si utilité prouvée (delta > 0).

        Le bonus est proportionnel au delta mais plafonné à max_fee_satoshi.
        Transfert : consumer → producteur.
        """
        if delta_utility <= 0:
            return FeeResult(
                ok=True, amount_satoshi=0,
                from_address=consumer_address, to_address=producer_address,
                knowledge_id=knowledge_id, event_id=usage_id,
                reason="no_utility_delta",
            )
        bonus = min(
            int(delta_utility * usage_bonus_satoshi_per_delta()),
            max_fee_satoshi(),
        )
        if bonus == 0:
            return FeeResult(
                ok=True, amount_satoshi=0,
                from_address=consumer_address, to_address=producer_address,
                knowledge_id=knowledge_id, event_id=usage_id,
                reason="bonus_zero",
            )
        bal_before = ledger.balance(consumer_address)
        try:
            ledger.transfer(consumer_address, producer_address, bonus)
        except InsufficientFundsError as exc:
            logger.warning("KCG Reasoning Fee USE bonus refusé : %s", exc)
            return FeeResult(
                ok=False, amount_satoshi=bonus,
                from_address=consumer_address, to_address=producer_address,
                knowledge_id=knowledge_id, event_id=usage_id,
                reason=str(exc),
                balance_before_from=bal_before,
            )
        logger.info(
            "KCG Reasoning Fee USE bonus : %s → %s %d satoshi delta=%.2f (knowledge=%s)",
            consumer_address[:12], producer_address[:12], bonus, delta_utility, knowledge_id,
        )
        return FeeResult(
            ok=True, amount_satoshi=bonus,
            from_address=consumer_address, to_address=producer_address,
            knowledge_id=knowledge_id, event_id=usage_id,
            balance_before_from=bal_before,
            balance_after_from=ledger.balance(consumer_address),
        )
