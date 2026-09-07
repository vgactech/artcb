"""PoUC — Proof of Useful Contribution Challenge/Stake/Escrow (GO-H 2026-09-07).

PoUC est le mécanisme de défi vérifiable qui transforme une déclaration de
contribution utile en preuve mesurable.

Architecture :
  PoUCChallenge  — un défi émis par le réseau sur une connaissance K
  PoUCStake      — mise en escrow du stake producteur (garantie de sincérité)
  PoUCEscrow     — coffre des stakes en attente de résolution
  PoUCResult     — résultat du défi (PASS / FAIL / TIMEOUT)
  PoUCEngine     — moteur de création/résolution des défis

Principe §237 :
  1. Le réseau émet un Challenge sur K (random ou ciblé)
  2. Le producteur stake X satoshi (gage de sincérité)
  3. Un verifier indépendant reproduit le raisonnement
  4. Si reproductibilité confirmée → PASS : stake retourné + bonus
  5. Si échec → FAIL : stake partiellement brûlé (pas de mint, juste pénalité)
  6. Si timeout → TIMEOUT : stake retourné (pas de pénalité)

GO-H invariant :
  - escrow_type = "stake"   (pas de nouveau token)
  - résolution = "transfer_back" ou "penalty_burn_partial"
  - Jamais de mint lors de la résolution
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger("artcb.kcg.pouc")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _uid(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


# ── Paramètres PoUC (configurables Doppler) ───────────────────────────────────

def pouc_default_stake_satoshi() -> int:
    return _env_int("ARTCB_POUC_DEFAULT_STAKE_SATOSHI", 1_000)


def pouc_challenge_timeout_seconds() -> int:
    return _env_int("ARTCB_POUC_CHALLENGE_TIMEOUT_SECONDS", 3600)  # 1h par défaut


def pouc_penalty_pct() -> float:
    """Pourcentage du stake brûlé en cas de FAIL (0.0–1.0)."""
    raw = os.environ.get("ARTCB_POUC_PENALTY_PCT", "0.1")
    try:
        v = float(raw)
        return max(0.0, min(1.0, v))
    except (ValueError, TypeError):
        return 0.1


# ── Énumérations ──────────────────────────────────────────────────────────────

class ChallengeStatus(str, Enum):
    PENDING  = "PENDING"    # défi émis, en attente de réponse
    PASS     = "PASS"       # reproductibilité confirmée
    FAIL     = "FAIL"       # échec de reproductibilité
    TIMEOUT  = "TIMEOUT"    # pas de réponse dans le délai


class EscrowStatus(str, Enum):
    LOCKED    = "LOCKED"    # stake en escrow
    RELEASED  = "RELEASED"  # stake retourné (PASS ou TIMEOUT)
    PENALIZED = "PENALIZED" # stake partiellement brûlé (FAIL)


# ── Modèles ──────────────────────────────────────────────────────────────────

@dataclass
class PoUCChallenge:
    """Un défi PoUC émis sur une connaissance K."""
    challenge_id: str = field(default_factory=lambda: _uid("CH"))
    knowledge_id: str = ""
    graph_id: str = ""
    producer_address: str = ""      # producteur challengé
    verifier_address: str = ""      # verifier assigné (ou "")
    issued_at: str = field(default_factory=_now_iso)
    expires_at: str = ""            # calculé depuis timeout
    status: str = ChallengeStatus.PENDING
    # Critère de succès
    min_reproduction_score: float = 0.7  # seuil de reproductibilité
    reproduction_score: float | None = None  # résultat verifier
    resolution_at: str = ""
    resolution_note: str = ""

    def __post_init__(self) -> None:
        if not self.expires_at:
            dt = datetime.now(UTC) + timedelta(seconds=pouc_challenge_timeout_seconds())
            self.expires_at = dt.isoformat(timespec="seconds")

    def is_expired(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(UTC) > exp
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PoUCChallenge":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PoUCStake:
    """Stake mis en escrow par le producteur lors d'un challenge."""
    stake_id: str = field(default_factory=lambda: _uid("SK"))
    challenge_id: str = ""
    knowledge_id: str = ""
    producer_address: str = ""
    amount_satoshi: int = 0
    escrow_status: str = EscrowStatus.LOCKED
    created_at: str = field(default_factory=_now_iso)
    resolved_at: str = ""
    penalty_burned_satoshi: int = 0  # toujours 0 sauf FAIL

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PoUCStake":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PoUCResult:
    """Résultat complet d'une résolution de challenge."""
    challenge_id: str
    status: str               # ChallengeStatus
    stake_id: str
    stake_released_satoshi: int = 0
    penalty_satoshi: int = 0
    fee_type: str = "transfer_back"  # GO-H invariant : jamais "mint"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Escrow (mémoire — persistance via KCGStore en production) ─────────────────

class PoUCEscrow:
    """Coffre des stakes PoUC en attente de résolution.

    En mémoire pour les tests — à brancher sur KCGStore en production.
    """

    def __init__(self) -> None:
        self._stakes: dict[str, PoUCStake] = {}    # stake_id → stake
        self._balances: dict[str, int] = {}         # address → satoshi

    def deposit(self, stake: PoUCStake) -> PoUCStake:
        """Dépose un stake en escrow depuis le compte du producteur."""
        bal = self._balances.get(stake.producer_address, 0)
        if bal < stake.amount_satoshi:
            raise ValueError(
                f"Solde escrow insuffisant : {stake.producer_address} bal={bal} "
                f"< stake={stake.amount_satoshi}"
            )
        self._balances[stake.producer_address] = bal - stake.amount_satoshi
        stake.escrow_status = EscrowStatus.LOCKED
        self._stakes[stake.stake_id] = stake
        logger.info(
            "PoUC escrow deposit : stake=%s producer=%s amount=%d satoshi",
            stake.stake_id, stake.producer_address[:12], stake.amount_satoshi,
        )
        return stake

    def fund(self, address: str, amount_satoshi: int) -> None:
        """Crédite un compte pour les tests (pas de mint — initialisation seulement)."""
        self._balances[address] = self._balances.get(address, 0) + amount_satoshi

    def balance(self, address: str) -> int:
        return self._balances.get(address, 0)

    def get_stake(self, stake_id: str) -> PoUCStake | None:
        return self._stakes.get(stake_id)

    def release(self, stake_id: str) -> PoUCStake:
        """Retourne le stake complet au producteur (PASS ou TIMEOUT)."""
        stake = self._stakes.get(stake_id)
        if not stake:
            raise KeyError(f"stake_id {stake_id} introuvable")
        if stake.escrow_status != EscrowStatus.LOCKED:
            raise ValueError(f"stake {stake_id} déjà résolu : {stake.escrow_status}")
        self._balances[stake.producer_address] = (
            self._balances.get(stake.producer_address, 0) + stake.amount_satoshi
        )
        stake.escrow_status = EscrowStatus.RELEASED
        stake.resolved_at = _now_iso()
        logger.info("PoUC escrow release : stake=%s → %s +%d satoshi",
                    stake.stake_id, stake.producer_address[:12], stake.amount_satoshi)
        return stake

    def penalize(self, stake_id: str) -> PoUCStake:
        """Applique la pénalité FAIL : brûle partiellement le stake.

        Le reste est retourné au producteur (pas de mint — juste perte).
        """
        stake = self._stakes.get(stake_id)
        if not stake:
            raise KeyError(f"stake_id {stake_id} introuvable")
        if stake.escrow_status != EscrowStatus.LOCKED:
            raise ValueError(f"stake {stake_id} déjà résolu : {stake.escrow_status}")
        pct = pouc_penalty_pct()
        burned = int(stake.amount_satoshi * pct)
        returned = stake.amount_satoshi - burned
        self._balances[stake.producer_address] = (
            self._balances.get(stake.producer_address, 0) + returned
        )
        stake.penalty_burned_satoshi = burned
        stake.escrow_status = EscrowStatus.PENALIZED
        stake.resolved_at = _now_iso()
        logger.info(
            "PoUC escrow penalize : stake=%s burned=%d returned=%d",
            stake.stake_id, burned, returned,
        )
        return stake


# ── Moteur PoUC ───────────────────────────────────────────────────────────────

class PoUCEngine:
    """Émet et résout les challenges PoUC."""

    def __init__(self, escrow: PoUCEscrow) -> None:
        self._escrow = escrow
        self._challenges: dict[str, PoUCChallenge] = {}

    def issue_challenge(
        self,
        knowledge_id: str,
        graph_id: str,
        producer_address: str,
        stake_satoshi: int | None = None,
        verifier_address: str = "",
        min_reproduction_score: float = 0.7,
    ) -> tuple[PoUCChallenge, PoUCStake]:
        """Émet un challenge et met le stake en escrow."""
        amount = stake_satoshi if stake_satoshi is not None else pouc_default_stake_satoshi()
        challenge = PoUCChallenge(
            knowledge_id=knowledge_id,
            graph_id=graph_id,
            producer_address=producer_address,
            verifier_address=verifier_address,
            min_reproduction_score=min_reproduction_score,
        )
        stake = PoUCStake(
            challenge_id=challenge.challenge_id,
            knowledge_id=knowledge_id,
            producer_address=producer_address,
            amount_satoshi=amount,
        )
        self._escrow.deposit(stake)
        self._challenges[challenge.challenge_id] = challenge
        logger.info(
            "PoUC challenge émis : %s knowledge=%s producer=%s stake=%d satoshi",
            challenge.challenge_id, knowledge_id, producer_address[:12], amount,
        )
        return challenge, stake

    def resolve(
        self,
        challenge_id: str,
        stake_id: str,
        reproduction_score: float,
    ) -> PoUCResult:
        """Résout un challenge avec le score de reproductibilité fourni par le verifier.

        GO-H invariant : fee_type = "transfer_back" ou "penalty_partial" (jamais "mint").
        """
        challenge = self._challenges.get(challenge_id)
        if not challenge:
            raise KeyError(f"challenge_id {challenge_id} introuvable")
        if challenge.status != ChallengeStatus.PENDING:
            raise ValueError(f"challenge {challenge_id} déjà résolu : {challenge.status}")

        challenge.reproduction_score = reproduction_score
        challenge.resolution_at = _now_iso()

        # Timeout check
        if challenge.is_expired():
            challenge.status = ChallengeStatus.TIMEOUT
            stake = self._escrow.release(stake_id)
            logger.info("PoUC TIMEOUT : %s → stake retourné", challenge_id)
            return PoUCResult(
                challenge_id=challenge_id,
                status=ChallengeStatus.TIMEOUT,
                stake_id=stake_id,
                stake_released_satoshi=stake.amount_satoshi,
                fee_type="transfer_back",
                note="timeout — stake intégralement retourné",
            )

        if reproduction_score >= challenge.min_reproduction_score:
            # PASS : stake retourné
            challenge.status = ChallengeStatus.PASS
            stake = self._escrow.release(stake_id)
            logger.info("PoUC PASS : %s score=%.2f → stake retourné", challenge_id, reproduction_score)
            return PoUCResult(
                challenge_id=challenge_id,
                status=ChallengeStatus.PASS,
                stake_id=stake_id,
                stake_released_satoshi=stake.amount_satoshi,
                fee_type="transfer_back",
                note=f"reproductibilité confirmée score={reproduction_score:.2f}",
            )
        else:
            # FAIL : pénalité partielle
            challenge.status = ChallengeStatus.FAIL
            stake = self._escrow.penalize(stake_id)
            logger.info(
                "PoUC FAIL : %s score=%.2f < %.2f → pénalité %d satoshi",
                challenge_id, reproduction_score,
                challenge.min_reproduction_score, stake.penalty_burned_satoshi,
            )
            return PoUCResult(
                challenge_id=challenge_id,
                status=ChallengeStatus.FAIL,
                stake_id=stake_id,
                stake_released_satoshi=stake.amount_satoshi - stake.penalty_burned_satoshi,
                penalty_satoshi=stake.penalty_burned_satoshi,
                fee_type="penalty_partial",
                note=f"reproductibilité insuffisante score={reproduction_score:.2f}",
            )

    def get_challenge(self, challenge_id: str) -> PoUCChallenge | None:
        return self._challenges.get(challenge_id)
