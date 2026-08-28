"""Identity / Finder Q=100 — rapport 162.

Creator is Genesis-VERIFIED (exemplary later 100/100 never rewrites Genesis).
Normal humans: up to 100 independent admissible validations.
When validator count > 100, creator-direct validations become revalidation-eligible.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger("artcb.economics.identity")

Q_FINDER = 100
ADULT_AGE_YEARS = 18  # protocol-wide; not per-country (user: adulte vérifié)
FINDER_ATTESTATIONS_PER_DAY_DEFAULT_SIM = 25


class HumanStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    GENESIS_VALIDATED = "GENESIS_VALIDATED"
    VERIFIED = "VERIFIED"
    REVALIDATION_REQUIRED = "REVALIDATION_REQUIRED"
    REVALIDATED = "REVALIDATED"
    SUSPENDED = "SUSPENDED"


@dataclass
class HumanRecord:
    human_id: str
    address: str
    status: str
    adult_verified: bool
    created_at: str
    validation_count: int = 0
    creator_direct: bool = False
    validated_by_creator: bool = False
    finder_eligible: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class IdentityError(ValueError):
    pass


class HumanRegistry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("human registry unreadable path=%s err=%s", self.path, exc)
            return []
        return data if isinstance(data, list) else []

    def _write(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    def bootstrap_creator(self, *, human_id: str, address: str) -> HumanRecord:
        if self.get(human_id) is not None:
            raise IdentityError(f"creator already exists: {human_id}")
        rec = HumanRecord(
            human_id=human_id,
            address=address,
            status=HumanStatus.GENESIS_VALIDATED.value,
            adult_verified=True,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            validation_count=0,
            creator_direct=True,
            validated_by_creator=False,
            finder_eligible=True,
        )
        rows = self._read()
        rows.append(rec.to_dict())
        self._write(rows)
        logger.debug("bootstrap creator id=%s addr=%s", human_id, address)
        return rec

    def get(self, human_id: str) -> HumanRecord | None:
        for row in self._read():
            if row.get("human_id") == human_id:
                return HumanRecord(**row)
        return None

    def get_by_address(self, address: str) -> HumanRecord | None:
        addr = address.strip()
        for row in self._read():
            if row.get("address") == addr:
                return HumanRecord(**row)
        return None

    def validator_count(self) -> int:
        ok = {
            HumanStatus.GENESIS_VALIDATED.value,
            HumanStatus.VERIFIED.value,
            HumanStatus.REVALIDATED.value,
        }
        return sum(1 for row in self._read() if row.get("status") in ok and row.get("adult_verified"))

    def verified_adult_count(self) -> int:
        return self.validator_count()

    def register_candidate(self, *, human_id: str, address: str) -> HumanRecord:
        if self.get(human_id) is not None:
            raise IdentityError(f"human already registered: {human_id}")
        if self.get_by_address(address) is not None:
            raise IdentityError(
                f"FAKE_HUMAN: address already bound to another HumanID: {address}"
            )
        rec = HumanRecord(
            human_id=human_id,
            address=address,
            status=HumanStatus.CANDIDATE.value,
            adult_verified=False,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        rows = self._read()
        rows.append(rec.to_dict())
        self._write(rows)
        return rec

    def creator_direct_validate(self, human_id: str, *, creator_id: str) -> HumanRecord:
        creator = self.get(creator_id)
        if creator is None or not creator.creator_direct:
            raise IdentityError("only the genesis creator may direct-validate")
        rec = self.get(human_id)
        if rec is None:
            raise IdentityError(f"unknown human {human_id}")
        rec.status = HumanStatus.GENESIS_VALIDATED.value
        rec.adult_verified = True
        rec.validated_by_creator = True
        rec.finder_eligible = True
        rec.validation_count = 1
        self._save(rec)
        self._maybe_require_revalidation()
        logger.debug("creator-direct validated %s", human_id)
        return rec

    def add_finder_validation(self, human_id: str) -> HumanRecord:
        rec = self.get(human_id)
        if rec is None:
            raise IdentityError(f"unknown human {human_id}")
        rec.validation_count = min(Q_FINDER, rec.validation_count + 1)
        if rec.validation_count >= Q_FINDER:
            rec.status = HumanStatus.VERIFIED.value
            rec.adult_verified = True
            rec.finder_eligible = True
        self._save(rec)
        self._maybe_require_revalidation()
        return rec

    def _maybe_require_revalidation(self) -> None:
        if self.validator_count() <= Q_FINDER:
            return
        rows = self._read()
        changed = False
        for row in rows:
            if row.get("creator_direct"):
                continue  # Genesis creator record is never rewritten
            if row.get("status") == HumanStatus.GENESIS_VALIDATED.value and row.get(
                "validated_by_creator"
            ):
                row["status"] = HumanStatus.REVALIDATION_REQUIRED.value
                changed = True
        if changed:
            self._write(rows)
            logger.debug("network maturity: genesis-direct humans marked REVALIDATION_REQUIRED")

    def _save(self, rec: HumanRecord) -> None:
        rows = self._read()
        for i, row in enumerate(rows):
            if row.get("human_id") == rec.human_id:
                rows[i] = rec.to_dict()
                self._write(rows)
                return
        rows.append(rec.to_dict())
        self._write(rows)


@dataclass
class DeviceRecord:
    device_id: str
    fingerprint: str
    human_id: str | None
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class DeviceRegistry:
    """DeviceID store — fingerprint is a hash, never raw hardware serials on-chain."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("device registry unreadable %s %s", self.path, exc)
            return []
        return data if isinstance(data, list) else []

    def _write(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, device_id: str) -> DeviceRecord | None:
        for row in self._read():
            if row.get("device_id") == device_id:
                return DeviceRecord(**row)
        return None

    def register(self, *, device_id: str, fingerprint: str, human_id: str | None = None) -> DeviceRecord:
        if self.get(device_id) is not None:
            raise IdentityError(f"device already registered: {device_id}")
        rec = DeviceRecord(
            device_id=device_id,
            fingerprint=fingerprint,
            human_id=human_id,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        rows = self._read()
        rows.append(rec.to_dict())
        self._write(rows)
        logger.debug("registered DeviceID=%s human=%s", device_id, human_id)
        return rec


@dataclass
class WalletIdRecord:
    wallet_id: str
    address: str
    human_id: str
    device_id: str
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class WalletIdRegistry:
    """WalletID bound to HumanID + DeviceID. Does not mint."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("wallet-id registry unreadable %s %s", self.path, exc)
            return []
        return data if isinstance(data, list) else []

    def _write(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, wallet_id: str) -> WalletIdRecord | None:
        for row in self._read():
            if row.get("wallet_id") == wallet_id:
                return WalletIdRecord(**row)
        return None

    def by_address(self, address: str) -> WalletIdRecord | None:
        for row in self._read():
            if row.get("address") == address:
                return WalletIdRecord(**row)
        return None

    def bind(
        self,
        *,
        wallet_id: str,
        address: str,
        human_id: str,
        device_id: str,
    ) -> WalletIdRecord:
        if self.get(wallet_id) is not None:
            raise IdentityError(f"WalletID already bound: {wallet_id}")
        if self.by_address(address) is not None:
            raise IdentityError(f"address already has a WalletID: {address}")
        rec = WalletIdRecord(
            wallet_id=wallet_id,
            address=address,
            human_id=human_id,
            device_id=device_id,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        rows = self._read()
        rows.append(rec.to_dict())
        self._write(rows)
        logger.debug(
            "bound WalletID=%s addr=%s human=%s device=%s",
            wallet_id,
            address,
            human_id,
            device_id,
        )
        return rec
