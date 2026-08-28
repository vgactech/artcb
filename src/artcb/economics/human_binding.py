"""Machine registry + human binding — rapport 162.

- M1 of owner A: 100% owner, no extra human.
- Machine n≥2: distinct verified human, not A, and **at most one external
  binding per human network-wide**.
- Offline ≠ removed from N_economic (GRACE/OFFLINE still count).
- N_economic decreases only after TRANSFERRED or RETIRED finality.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("artcb.economics.human_binding")

ECONOMIC_STATES = frozenset(
    {
        "REGISTERED",
        "ATTESTED",
        "ACTIVE",
        "GRACE",
        "OFFLINE",
        "DEACTIVATION_REQUESTED",
        "TRANSFER_PENDING",
    }
)
EXITED_STATES = frozenset({"TRANSFERRED", "RETIRED", "COMPROMISED"})


class HumanBindingError(ValueError):
    """Raised when a machine cannot be bound under protocol rules."""


@dataclass
class MachineRecord:
    machine_id: str
    owner_address: str
    machine_index: int
    bound_human_address: str | None
    registered_at: str
    device_fingerprint: str | None = None
    status: str = "ACTIVE"
    is_first_machine: bool = False

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

    def _hydrate(self, row: dict) -> MachineRecord:
        known = {
            "machine_id",
            "owner_address",
            "machine_index",
            "bound_human_address",
            "registered_at",
            "device_fingerprint",
            "status",
            "is_first_machine",
        }
        filtered = {k: v for k, v in row.items() if k in known}
        rec = MachineRecord(**filtered)
        if rec.machine_index == 1:
            rec.is_first_machine = True
        return rec

    def machines_of(self, owner_address: str) -> list[MachineRecord]:
        owner = owner_address.strip()
        records = [
            self._hydrate(row)
            for row in self._read()
            if row.get("owner_address") == owner
        ]
        records.sort(key=lambda rec: rec.machine_index)
        return records

    def economic_machines_of(self, owner_address: str) -> list[MachineRecord]:
        return [m for m in self.machines_of(owner_address) if m.status in ECONOMIC_STATES]

    def economic_count(self, owner_address: str) -> int:
        return len(self.economic_machines_of(owner_address))

    def next_index(self, owner_address: str) -> int:
        existing = self.machines_of(owner_address)
        live = [m for m in existing if m.status not in EXITED_STATES]
        if not live:
            return 1
        return max(m.machine_index for m in live) + 1

    def get(self, machine_id: str) -> MachineRecord | None:
        for row in self._read():
            if row.get("machine_id") == machine_id:
                return self._hydrate(row)
        return None

    def external_bindings_of(self, human_address: str) -> list[MachineRecord]:
        human = human_address.strip()
        out = []
        for row in self._read():
            rec = self._hydrate(row)
            if rec.bound_human_address == human and rec.status not in EXITED_STATES:
                out.append(rec)
        return out

    def verified_human_addresses(self) -> set[str]:
        humans: set[str] = set()
        for row in self._read():
            owner = row.get("owner_address")
            if owner:
                humans.add(owner)
            bound = row.get("bound_human_address")
            if bound:
                humans.add(bound)
        return humans

    def _save_record(self, record: MachineRecord) -> None:
        rows = self._read()
        for i, row in enumerate(rows):
            if row.get("machine_id") == record.machine_id:
                rows[i] = record.to_dict()
                self._write(rows)
                return
        rows.append(record.to_dict())
        self._write(rows)

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

        econ = self.economic_count(owner)
        index = 1 if econ == 0 else self.next_index(owner)
        first = index == 1 or econ == 0
        bound = bound_human_address.strip() if bound_human_address else None
        if bound == "":
            bound = None

        if first:
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
            already = {
                rec.bound_human_address
                for rec in self.economic_machines_of(owner)
            }
            if bound in already:
                raise HumanBindingError(
                    f"human {bound} is already bound to another machine of {owner}"
                )
            if self.external_bindings_of(bound):
                raise HumanBindingError(
                    f"human {bound} already has an external machine binding (max 1)"
                )

        record = MachineRecord(
            machine_id=machine_id,
            owner_address=owner,
            machine_index=index,
            bound_human_address=bound,
            registered_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            device_fingerprint=device_fingerprint,
            status="ACTIVE",
            is_first_machine=first,
        )
        self._save_record(record)
        logger.debug(
            "registered machine id=%s owner=%s index=%s first=%s human=%s N_econ=%s",
            machine_id,
            owner,
            index,
            first,
            bound,
            self.economic_count(owner),
        )
        return record

    def mark_active(self, machine_id: str) -> MachineRecord:
        rec = self.get(machine_id)
        if rec is None:
            raise HumanBindingError(f"unknown machine {machine_id}")
        if rec.status in EXITED_STATES:
            raise HumanBindingError("exited machine cannot return to ACTIVE")
        rec.status = "ACTIVE"
        self._save_record(rec)
        return rec

    def mark_offline(self, machine_id: str) -> MachineRecord:
        rec = self.get(machine_id)
        if rec is None:
            raise HumanBindingError(f"unknown machine {machine_id}")
        if rec.status in EXITED_STATES:
            raise HumanBindingError("exited machine cannot go offline")
        rec.status = "OFFLINE"
        self._save_record(rec)
        logger.debug(
            "offline %s N_econ unchanged=%s",
            machine_id,
            self.economic_count(rec.owner_address),
        )
        return rec

    def mark_grace(self, machine_id: str) -> MachineRecord:
        rec = self.get(machine_id)
        if rec is None:
            raise HumanBindingError(f"unknown machine {machine_id}")
        rec.status = "GRACE"
        self._save_record(rec)
        return rec

    def request_deactivation(self, machine_id: str) -> MachineRecord:
        rec = self.get(machine_id)
        if rec is None:
            raise HumanBindingError(f"unknown machine {machine_id}")
        rec.status = "DEACTIVATION_REQUESTED"
        self._save_record(rec)
        return rec

    def finalize_retire(self, machine_id: str) -> MachineRecord:
        rec = self.get(machine_id)
        if rec is None:
            raise HumanBindingError(f"unknown machine {machine_id}")
        rec.status = "RETIRED"
        self._save_record(rec)
        logger.debug("retired %s N_econ=%s", machine_id, self.economic_count(rec.owner_address))
        return rec

    def transfer(
        self,
        machine_id: str,
        *,
        new_owner: str,
        bound_human_address: str | None = None,
    ) -> MachineRecord:
        rec = self.get(machine_id)
        if rec is None:
            raise HumanBindingError(f"unknown machine {machine_id}")
        rec.status = "TRANSFERRED"
        self._save_record(rec)
        logger.debug("transferred out %s from %s", machine_id, rec.owner_address)
        new_id = f"{machine_id}:to:{new_owner}"
        return self.register(
            machine_id=new_id,
            owner_address=new_owner,
            bound_human_address=bound_human_address,
            device_fingerprint=rec.device_fingerprint,
        )
