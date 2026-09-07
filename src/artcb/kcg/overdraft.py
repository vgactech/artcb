"""Découvert ARTCB (ARTCB Overdraft) — extension KCG/Reasoning Fee.

Un wallet ARTCB peut être autorisé à payer des frais (CONSULT, USE, stake PoUC)
même si son solde est insuffisant, jusqu'à une limite négative fixée.

Principes :
  - La dette est enregistrée dans `debt_satoshi` du compte
  - Ce N'EST PAS du mint : la supply totale du réseau n'augmente pas
  - Le créancier (producteur) reçoit quand même les satoshi (prélevés du solde réseau)
  - La dette est remboursée automatiquement (auto_repay) dès que le débiteur
    reçoit des tokens (récompense PoL, autre transfert entrant)
  - Un wallet sans limit_overdraft = 0 (pas de découvert autorisé)

Mécanique :
  solde_effectif = balance - debt_satoshi
  transfer autorisé si : balance + limit_overdraft >= amount
  après transfer : balance peut devenir négatif jusqu'à -limit_overdraft
  à chaque crédit entrant : d'abord rembourser debt_satoshi, puis créditer le reste

Analogie : découvert bancaire autorisé.
  - La banque paie le commerçant
  - Le client est débiteur
  - Dès que le client est crédité → remboursement automatique
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("artcb.kcg.overdraft")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def default_overdraft_limit_satoshi() -> int:
    """Limite de découvert par défaut pour les wallets autorisés (configurable Doppler)."""
    return _env_int("ARTCB_OVERDRAFT_DEFAULT_LIMIT_SATOSHI", 10_000)  # 0.0001 ARTCB par défaut


# ── Modèles ──────────────────────────────────────────────────────────────────

@dataclass
class OverdraftAccount:
    """Compte ARTCB avec support du découvert autorisé."""
    address: str
    balance_satoshi: int = 0         # solde courant (peut être négatif si overdraft actif)
    debt_satoshi: int = 0            # dette totale accumulée (>= 0)
    limit_overdraft_satoshi: int = 0 # limite max de découvert (0 = pas de découvert)
    total_credited: int = 0          # total reçu sur la vie du compte
    total_debited: int = 0           # total prélevé (hors dette)
    total_debt_repaid: int = 0       # total de dettes remboursées

    @property
    def available(self) -> int:
        """Solde disponible = balance + limite découvert non utilisée."""
        overdraft_used = max(0, -self.balance_satoshi)
        overdraft_remaining = max(0, self.limit_overdraft_satoshi - overdraft_used)
        return self.balance_satoshi + overdraft_remaining

    @property
    def is_in_overdraft(self) -> bool:
        return self.balance_satoshi < 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "balance_satoshi": self.balance_satoshi,
            "debt_satoshi": self.debt_satoshi,
            "limit_overdraft_satoshi": self.limit_overdraft_satoshi,
            "available": self.available,
            "is_in_overdraft": self.is_in_overdraft,
            "total_credited": self.total_credited,
            "total_debited": self.total_debited,
            "total_debt_repaid": self.total_debt_repaid,
        }


@dataclass
class OverdraftTransferResult:
    """Résultat d'un transfert avec gestion du découvert."""
    ok: bool
    amount_satoshi: int
    overdraft_used_satoshi: int = 0   # portion payée en découvert
    debt_repaid_satoshi: int = 0      # dette remboursée lors d'un crédit
    reason: str = ""
    from_balance_after: int = 0
    from_debt_after: int = 0


# ── Ledger avec découvert ─────────────────────────────────────────────────────

class OverdraftLedger:
    """Ledger ARTCB avec gestion du découvert autorisé.

    Compatible avec KCGLedger (même interface de base) mais enrichi.
    """

    def __init__(self) -> None:
        self._accounts: dict[str, OverdraftAccount] = {}

    def get_or_create(self, address: str) -> OverdraftAccount:
        if address not in self._accounts:
            self._accounts[address] = OverdraftAccount(address=address)
        return self._accounts[address]

    def fund(self, address: str, amount_satoshi: int) -> None:
        """Crédite un compte (initialisation ou récompense PoL)."""
        acc = self.get_or_create(address)
        self.credit(address, amount_satoshi)

    def set_overdraft_limit(self, address: str, limit_satoshi: int) -> None:
        """Autorise un découvert jusqu'à limit_satoshi pour ce wallet."""
        acc = self.get_or_create(address)
        acc.limit_overdraft_satoshi = max(0, limit_satoshi)
        logger.info(
            "Overdraft autorisé : %s limite=%d satoshi",
            address[:16], limit_satoshi,
        )

    def balance(self, address: str) -> int:
        return self.get_or_create(address).balance_satoshi

    def available(self, address: str) -> int:
        return self.get_or_create(address).available

    def debt(self, address: str) -> int:
        return self.get_or_create(address).debt_satoshi

    def credit(self, address: str, amount_satoshi: int) -> OverdraftTransferResult:
        """Crédite un compte. Rembourse la dette (balance négative) en priorité.

        Invariant : debt_satoshi == abs(min(0, balance_satoshi))
        Séquence :
          balance_satoshi += amount_satoshi  (peut remonter de négatif à positif)
          debt_satoshi = abs(min(0, balance_satoshi))
        """
        if amount_satoshi <= 0:
            return OverdraftTransferResult(ok=True, amount_satoshi=0)
        acc = self.get_or_create(address)
        debt_before = acc.debt_satoshi
        acc.balance_satoshi += amount_satoshi
        acc.total_credited += amount_satoshi
        # Recalcul propre de la dette
        acc.debt_satoshi = max(0, -acc.balance_satoshi)
        repay = debt_before - acc.debt_satoshi
        acc.total_debt_repaid += repay
        if repay > 0:
            logger.info(
                "Auto-repay découvert : %s remboursé=%d satoshi dette_restante=%d",
                address[:16], repay, acc.debt_satoshi,
            )
        return OverdraftTransferResult(
            ok=True,
            amount_satoshi=amount_satoshi,
            debt_repaid_satoshi=repay,
            from_balance_after=acc.balance_satoshi,
            from_debt_after=acc.debt_satoshi,
        )

    def transfer(
        self,
        from_addr: str,
        to_addr: str,
        amount_satoshi: int,
    ) -> OverdraftTransferResult:
        """Transfère amount_satoshi de from_addr vers to_addr.

        Si le solde est insuffisant ET que le compte a un découvert autorisé,
        le transfer est autorisé et la dette est enregistrée.

        Le destinataire reçoit toujours le montant complet.
        """
        if amount_satoshi <= 0:
            return OverdraftTransferResult(ok=True, amount_satoshi=0)

        from_acc = self.get_or_create(from_addr)
        to_acc = self.get_or_create(to_addr)

        # Vérifier si le transfer est possible (balance + découvert disponible)
        if from_acc.available < amount_satoshi:
            logger.warning(
                "Transfer refusé : %s disponible=%d < %d satoshi (overdraft limit=%d)",
                from_addr[:16], from_acc.available, amount_satoshi,
                from_acc.limit_overdraft_satoshi,
            )
            return OverdraftTransferResult(
                ok=False,
                amount_satoshi=amount_satoshi,
                reason=f"solde_insuffisant: disponible={from_acc.available} requis={amount_satoshi}",
                from_balance_after=from_acc.balance_satoshi,
                from_debt_after=from_acc.debt_satoshi,
            )

        # Calculer la part payée en découvert
        overdraft_used = max(0, amount_satoshi - from_acc.balance_satoshi)

        # Débiter from_addr (balance peut devenir négative)
        from_acc.balance_satoshi -= amount_satoshi
        from_acc.total_debited += amount_satoshi

        # Recalcul propre de la dette : dette = abs(balance) si balance < 0
        from_acc.debt_satoshi = max(0, -from_acc.balance_satoshi)
        if overdraft_used > 0:
            logger.info(
                "Découvert utilisé : %s overdraft=%d satoshi dette_totale=%d",
                from_addr[:16], overdraft_used, from_acc.debt_satoshi,
            )

        # Créditer to_addr (avec auto-repay si to_addr a une dette)
        self.credit(to_addr, amount_satoshi)

        return OverdraftTransferResult(
            ok=True,
            amount_satoshi=amount_satoshi,
            overdraft_used_satoshi=overdraft_used,
            from_balance_after=from_acc.balance_satoshi,
            from_debt_after=from_acc.debt_satoshi,
        )

    def all_accounts(self) -> list[OverdraftAccount]:
        return list(self._accounts.values())

    def global_debt(self) -> int:
        """Dette totale non remboursée sur tous les comptes."""
        return sum(a.debt_satoshi for a in self._accounts.values())
