"""Machine registry + human binding.

Rules:
- machine_index is 1-based and **per owner** (n_A), never confused with H.
- Machine 1 of owner A: 100% owner, no extra human required.
- Machine n≥2 of owner A: a distinct verified human is mandatory,
  different from A and from every human already bound to A's other machines.
- Owner C's own first machine C1 is independent of C being bound on A's A3.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("artcb.economics.human_binding")


class HumanBindingError(ValueError):
    """Raised when a machine cannot be bound under protocol rules."""


@dataclass(frozen=True)
class MachineRecord:
    machine_id: str
    owner_address: str
    machine_index: int
    bound_human_address: str | None
    registered_at: str
    device_fingerprint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class MachineRegistry:
    """Persistent owner → machines map (JSON, debug-logged)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("machine registry unreadable path=%s err=%s", self.path, exc)
            return []
        if not isinstance(data, list):
            logger.error("machine registry corrupted (not a list) path=%s", self.path)
            return []
        return data

    def _write(self, records: list[dict]) -> None:
        self.path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def machines_of(self, owner_address: str) -> list[MachineRecord]:
        owner = owner_address.strip()
        records = [
            MachineRecord(**row)
            for row in self._read()
            if row.get("owner_address") == owner
        ]
        records.sort(key=lambda rec: rec.machine_index)
        return records

    def next_index(self, owner_address: str) -> int:
        existing = self.machines_of(owner_address)
        return (existing[-1].machine_index + 1) if existing else 1

    def get(self, machine_id: str) -> MachineRecord | None:
        for row in self._read():
            if row.get("machine_id") == machine_id:
                return MachineRecord(**row)
        return None

    def verified_human_addresses(self) -> set[str]:
        """Unique owners + bound humans (network-wide H contributors)."""
        humans: set[str] = set()
        for row in self._read():
            owner = row.get("owner_address")
            if owner:
                humans.add(owner)
            bound = row.get("bound_human_address")
            if bound:
                humans.add(bound)
        return humans

    def register(
        self,
        *,
        machine_id: str,
        owner_address: str,
        bound_human_address: str | None = None,
        device_fingerprint: str | None = None,
    ) -> MachineRecord:
        machine_id = machine_id.strip()
        owner = owner_address.strip()
        if not machine_id:
            raise HumanBindingError("machine_id is required")
        if not owner:
            raise HumanBindingError("owner_address is required")
        if self.get(machine_id) is not None:
            raise HumanBindingError(f"machine already registered: {machine_id}")

        index = self.next_index(owner)
        bound = bound_human_address.strip() if bound_human_address else None
        if bound == "":
            bound = None

        if index == 1:
            if bound is not None and bound != owner:
                raise HumanBindingError(
                    "first machine of an owner cannot bind a third-party human"
                )
            bound = None
        else:
            if bound is None:
                raise HumanBindingError(
                    f"machine index {index} requires a distinct verified human"
                )
            if bound == owner:
                raise HumanBindingError(
                    "bound human must be distinct from the owner for n>=2"
                )
            already = {rec.bound_human_address for rec in self.machines_of(owner)}
            if bound in already:
                raise HumanBindingError(
                    f"human {bound} is already bound to another machine of {owner}"
                )

        record = MachineRecord(
            machine_id=machine_id,
            owner_address=owner,
            machine_index=index,
            bound_human_address=bound,
            registered_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            device_fingerprint=device_fingerprint,
        )
        rows = self._read()
        rows.append(record.to_dict())
        self._write(rows)
        logger.debug(
            "registered machine id=%s owner=%s index=%s human=%s",
            machine_id,
            owner,
            index,
            bound,
        )
        return record
