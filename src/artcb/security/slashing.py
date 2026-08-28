"""
Slashing Manager — Pénalités pour comportements malveillants

Implémente :
1. Détection fraude (double-spend, tampering)
2. Pénalités graduelles (warning → suspension → ban)
3. Confiscation rewards frauduleux
4. Blacklist persistante
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SlashingEvent:
    """Événement de slashing"""
    address: str
    timestamp: datetime
    reason: str
    severity: str  # "warning", "minor", "major", "critical"
    penalty_satoshi: int = 0
    blocks_affected: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Sérialise en dict"""
        return {
            "address": self.address,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "severity": self.severity,
            "penalty_satoshi": self.penalty_satoshi,
            "blocks_affected": self.blocks_affected
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SlashingEvent":
        """Désérialise depuis dict"""
        return cls(
            address=data["address"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            reason=data["reason"],
            severity=data["severity"],
            penalty_satoshi=data.get("penalty_satoshi", 0),
            blocks_affected=data.get("blocks_affected", [])
        )


@dataclass
class AddressStatus:
    """Statut d'une adresse"""
    address: str
    warnings: int = 0
    minor_slashes: int = 0
    major_slashes: int = 0
    critical_slashes: int = 0
    total_penalty_satoshi: int = 0
    is_banned: bool = False
    ban_until: datetime | None = None
    last_slash: datetime | None = None

    @property
    def total_slashes(self) -> int:
        """Nombre total de slashes"""
        return self.minor_slashes + self.major_slashes + self.critical_slashes

    @property
    def is_suspended(self) -> bool:
        """Adresse suspendue temporairement ?"""
        return bool(self.ban_until and datetime.now(UTC) < self.ban_until)

    @property
    def risk_level(self) -> str:
        """Niveau de risque"""
        if self.is_banned:
            return "BANNED"
        if self.critical_slashes > 0:
            return "CRITICAL"
        if self.major_slashes >= 2:
            return "HIGH"
        if self.minor_slashes >= 3:
            return "MEDIUM"
        if self.warnings >= 5:
            return "LOW"
        return "CLEAN"


class SlashingManager:
    """
    Gestionnaire de slashing pour comportements malveillants

    Sévérités :
    - warning : Avertissement (pas de pénalité)
    - minor : Slash mineur (10% rewards)
    - major : Slash majeur (50% rewards + suspension 24h)
    - critical : Slash critique (100% rewards + ban permanent)
    """

    # Pénalités en % des rewards
    PENALTY_MINOR = 0.10
    PENALTY_MAJOR = 0.50
    PENALTY_CRITICAL = 1.00

    # Durées suspension
    SUSPENSION_MINOR = timedelta(hours=1)
    SUSPENSION_MAJOR = timedelta(hours=24)

    def __init__(
        self,
        slashing_file: Path | None = None,
        blacklist_file: Path | None = None
    ):
        self.slashing_file = slashing_file or Path("data/slashing_events.jsonl")
        self.blacklist_file = blacklist_file or Path("data/blacklist.json")

        # Cache en mémoire
        self.events: list[SlashingEvent] = []
        self.status: dict[str, AddressStatus] = {}
        self.blacklist: list[str] = []

        # Charger données existantes
        self._load_events()
        self._load_blacklist()

        logger.info(
            f"SlashingManager initialized: {len(self.events)} events, "
            f"{len(self.blacklist)} blacklisted addresses"
        )

    def slash(
        self,
        address: str,
        reason: str,
        severity: str,
        reward_satoshi: int = 0,
        block_index: int | None = None
    ) -> SlashingEvent:
        """
        Applique un slash à une adresse

        Args:
            address: Adresse à slasher
            reason: Raison du slash
            severity: "warning", "minor", "major", "critical"
            reward_satoshi: Rewards à pénaliser
            block_index: Index du bloc concerné

        Returns:
            SlashingEvent créé
        """
        now = datetime.now(UTC)

        # Calculer pénalité
        penalty = 0
        if severity == "minor":
            penalty = int(reward_satoshi * self.PENALTY_MINOR)
        elif severity == "major":
            penalty = int(reward_satoshi * self.PENALTY_MAJOR)
        elif severity == "critical":
            penalty = reward_satoshi  # 100%

        # Créer événement
        event = SlashingEvent(
            address=address,
            timestamp=now,
            reason=reason,
            severity=severity,
            penalty_satoshi=penalty,
            blocks_affected=[block_index] if block_index else []
        )

        # Mettre à jour statut
        if address not in self.status:
            self.status[address] = AddressStatus(address=address)

        status = self.status[address]
        status.last_slash = now
        status.total_penalty_satoshi += penalty

        if severity == "warning":
            status.warnings += 1
        elif severity == "minor":
            status.minor_slashes += 1
            status.ban_until = now + self.SUSPENSION_MINOR
        elif severity == "major":
            status.major_slashes += 1
            status.ban_until = now + self.SUSPENSION_MAJOR
        elif severity == "critical":
            status.critical_slashes += 1
            status.is_banned = True
            self.blacklist.append(address)
            self._save_blacklist()

        # Enregistrer événement
        self.events.append(event)
        self._save_event(event)

        logger.warning(
            f"SLASH {severity.upper()}: {address[:12]}... — {reason} "
            f"(penalty={penalty/1e8:.2f} ARTCB, block={block_index})"
        )

        return event

    def is_allowed(self, address: str) -> tuple[bool, str | None]:
        """
        Vérifie si une adresse est autorisée à miner

        Args:
            address: Adresse à vérifier

        Returns:
            (allowed, reason) — True si autorisé, sinon (False, raison)
        """
        # Blacklist
        if address in self.blacklist:
            return False, "Address is permanently banned"

        # Statut
        if address in self.status:
            status = self.status[address]

            if status.is_banned:
                return False, "Address is permanently banned"

            if status.is_suspended and status.ban_until:
                remaining = (status.ban_until - datetime.now(UTC)).total_seconds()
                return False, f"Address is suspended for {remaining/3600:.1f}h"

        return True, None

    def get_status(self, address: str) -> AddressStatus:
        """Récupère le statut d'une adresse"""
        if address not in self.status:
            self.status[address] = AddressStatus(address=address)
        return self.status[address]

    def get_events(
        self,
        address: str | None = None,
        severity: str | None = None,
        limit: int = 100
    ) -> list[SlashingEvent]:
        """
        Récupère les événements de slashing

        Args:
            address: Filtrer par adresse (optionnel)
            severity: Filtrer par sévérité (optionnel)
            limit: Nombre max d'événements

        Returns:
            Liste d'événements
        """
        events = self.events

        if address:
            events = [e for e in events if e.address == address]

        if severity:
            events = [e for e in events if e.severity == severity]

        # Trier par timestamp décroissant
        events = sorted(events, key=lambda e: e.timestamp, reverse=True)

        return events[:limit]

    def _load_events(self):
        """Charge les événements depuis le fichier"""
        if not self.slashing_file.exists():
            return

        try:
            with self.slashing_file.open() as f:
                for line in f:
                    data = json.loads(line)
                    event = SlashingEvent.from_dict(data)
                    self.events.append(event)

                    # Reconstruire statut
                    if event.address not in self.status:
                        self.status[event.address] = AddressStatus(address=event.address)

                    status = self.status[event.address]
                    status.total_penalty_satoshi += event.penalty_satoshi
                    status.last_slash = event.timestamp

                    if event.severity == "warning":
                        status.warnings += 1
                    elif event.severity == "minor":
                        status.minor_slashes += 1
                    elif event.severity == "major":
                        status.major_slashes += 1
                    elif event.severity == "critical":
                        status.critical_slashes += 1
                        status.is_banned = True

            logger.info(f"Loaded {len(self.events)} slashing events")
        except Exception as e:
            logger.error(f"Failed to load slashing events: {e}")

    def _save_event(self, event: SlashingEvent):
        """Sauvegarde un événement dans le fichier"""
        try:
            self.slashing_file.parent.mkdir(parents=True, exist_ok=True)
            with self.slashing_file.open("a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Failed to save slashing event: {e}")

    def _load_blacklist(self):
        """Charge la blacklist depuis le fichier"""
        if not self.blacklist_file.exists():
            return

        try:
            with self.blacklist_file.open() as f:
                data = json.load(f)
                self.blacklist = data.get("addresses", [])
            logger.info(f"Loaded {len(self.blacklist)} blacklisted addresses")
        except Exception as e:
            logger.error(f"Failed to load blacklist: {e}")

    def _save_blacklist(self):
        """Sauvegarde la blacklist dans le fichier"""
        try:
            self.blacklist_file.parent.mkdir(parents=True, exist_ok=True)
            with self.blacklist_file.open("w") as f:
                json.dump({"addresses": self.blacklist}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save blacklist: {e}")

