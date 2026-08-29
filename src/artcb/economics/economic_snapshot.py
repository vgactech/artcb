"""EconomicStateSnapshot + SettlementID — Simulation 167.

Recommended defaults (PENDING user validation V-01…V-07)::

    V-01 Snapshot at epoch start (Solution A)
    V-02 Transfer economic effect = next epoch
    V-03 Reconnect grace = 24h (or 1 epoch)
    V-04 Retirement effect = next snapshot
    V-05 Finality = N confirmations (default 2) — vs quorum, unfrozen
    V-06 H_adult_max = versioned DemographicReference, not a bare integer
    V-07 HBP 10→60→20 on ratio H_verified / H_adult_max (anchors provisional)

Settlement = f(snapshot). Mid-epoch ownership changes do not rewrite P(N).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.economics.economic_snapshot")

PROTOCOL_VERSION = "167-distributed-snapshot"
ECONOMIC_RULES_VERSION = "D-025+V01-V07-provisional"
DEFAULT_GRACE_SECONDS = 24 * 3600  # V-03 proposed
DEFAULT_FINALITY_CONFIRMATIONS = 2  # V-05 B
DEFAULT_EPOCH_SECONDS = 600  # TARGET_BLOCK_SECONDS


class AlreadySettled(ValueError):
    """Second consume of the same SettlementID."""


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotMachine:
    machine_id: str
    owner_address: str
    machine_index: int
    bound_human_address: str | None
    status: str
    is_first_machine: bool
    n_economic: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PendingOp:
    kind: str  # transfer | retire | reconnect
    machine_id: str
    payload: dict[str, Any]
    queued_at: str
    effective_epoch: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EconomicStateSnapshot:
    epoch: int
    parent_root: str
    protocol_version: str
    economic_rules_version: str
    taken_at: str
    h_adult: int
    demographic_digest: str
    machines: tuple[SnapshotMachine, ...]
    work_ids_open: tuple[str, ...]
    pending_ops: tuple[PendingOp, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "parent_root": self.parent_root,
            "protocol_version": self.protocol_version,
            "economic_rules_version": self.economic_rules_version,
            "taken_at": self.taken_at,
            "h_adult": self.h_adult,
            "demographic_digest": self.demographic_digest,
            "machines": [m.to_dict() for m in self.machines],
            "work_ids_open": list(self.work_ids_open),
            "pending_ops": [p.to_dict() for p in self.pending_ops],
        }

    def digest(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def machine(self, machine_id: str) -> SnapshotMachine | None:
        for rec in self.machines:
            if rec.machine_id == machine_id:
                return rec
        return None

    def n_economic(self, owner_address: str) -> int:
        return max(
            (
                rec.n_economic
                for rec in self.machines
                if rec.owner_address == owner_address
            ),
            default=0,
        )


def settlement_id(
    *,
    work_id: str,
    snapshot_digest: str,
    protocol_version: str = PROTOCOL_VERSION,
) -> str:
    """SettlementID = SHA256(WorkID | EconomicSnapshot | ProtocolVersion)."""
    material = f"{work_id}|{snapshot_digest}|{protocol_version}".encode("utf-8")
    sid = hashlib.sha256(material).hexdigest()
    logger.debug("SettlementID work=%s sid=%s", work_id, sid[:16])
    return sid


class SettlementLedger:
    """One SettlementID → one consume. Thread-safe for concurrent nodes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self._consumed: dict[str, dict[str, Any]] = {}
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_file():
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self._consumed = data
                except (OSError, json.JSONDecodeError) as exc:
                    logger.error("settlement ledger unreadable %s %s", self.path, exc)

    def _persist(self) -> None:
        if not self.path:
            return
        self.path.write_text(
            json.dumps(self._consumed, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def consumed(self, sid: str) -> bool:
        with self._lock:
            return sid in self._consumed

    def consume(
        self,
        sid: str,
        *,
        work_id: str,
        node_id: str,
        epoch: int,
    ) -> dict[str, Any]:
        with self._lock:
            if sid in self._consumed:
                raise AlreadySettled(f"AlreadySettled SettlementID={sid[:16]} work={work_id}")
            for row in self._consumed.values():
                if row.get("work_id") == work_id:
                    raise AlreadySettled(
                        f"AlreadySettled WorkID={work_id} prior_sid={str(row.get('settlement_id'))[:16]}"
                    )
            row = {
                "settlement_id": sid,
                "work_id": work_id,
                "node_id": node_id,
                "epoch": epoch,
                "consumed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            self._consumed[sid] = row
            self._persist()
            logger.debug("settlement consumed sid=%s node=%s", sid[:16], node_id)
            return row

    def count_for_work(self, work_id: str) -> int:
        with self._lock:
            return sum(1 for row in self._consumed.values() if row.get("work_id") == work_id)

    def to_list(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._consumed.values())


@dataclass
class EpochCoordinator:
    """V-01/V-02/V-04: snapshot at epoch start; transfers/retirements next epoch."""

    grace_seconds: int = DEFAULT_GRACE_SECONDS
    protocol_version: str = PROTOCOL_VERSION
    pending: list[PendingOp] = field(default_factory=list)
    epoch: int = 0
    last_snapshot: EconomicStateSnapshot | None = None
    reconnect_ready_at: dict[str, datetime] = field(default_factory=dict)

    def queue_transfer(
        self,
        machine_id: str,
        *,
        new_owner: str,
        bound_human_address: str | None,
    ) -> PendingOp:
        op = PendingOp(
            kind="transfer",
            machine_id=machine_id,
            payload={"new_owner": new_owner, "bound_human_address": bound_human_address},
            queued_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            effective_epoch=self.epoch + 1,
        )
        self.pending.append(op)
        logger.debug("queued transfer %s -> %s effective_epoch=%s", machine_id, new_owner, op.effective_epoch)
        return op

    def queue_retire(self, machine_id: str) -> PendingOp:
        op = PendingOp(
            kind="retire",
            machine_id=machine_id,
            payload={},
            queued_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            effective_epoch=self.epoch + 1,
        )
        self.pending.append(op)
        logger.debug("queued retire %s effective_epoch=%s", machine_id, op.effective_epoch)
        return op

    def queue_reconnect(self, machine_id: str, *, now: datetime | None = None) -> PendingOp:
        instant = now or datetime.now(UTC)
        ready = instant + timedelta(seconds=self.grace_seconds)
        self.reconnect_ready_at[machine_id] = ready
        op = PendingOp(
            kind="reconnect",
            machine_id=machine_id,
            payload={"ready_at": ready.strftime("%Y-%m-%dT%H:%M:%SZ")},
            queued_at=instant.strftime("%Y-%m-%dT%H:%M:%SZ"),
            effective_epoch=self.epoch + 1,
        )
        self.pending.append(op)
        logger.debug("queued reconnect %s ready=%s", machine_id, ready.isoformat())
        return op

    def apply_due_ops(self, machines, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Apply pending ops whose effective_epoch <= current epoch. Mutates registry."""
        instant = now or datetime.now(UTC)
        applied: list[dict[str, Any]] = []
        remain: list[PendingOp] = []
        for op in self.pending:
            if op.effective_epoch > self.epoch:
                remain.append(op)
                continue
            if op.kind == "reconnect":
                ready = self.reconnect_ready_at.get(op.machine_id)
                if ready is not None and instant < ready:
                    remain.append(op)
                    continue
                machines.mark_active(op.machine_id)
            elif op.kind == "retire":
                machines.finalize_retire(op.machine_id)
            elif op.kind == "transfer":
                machines.transfer(
                    op.machine_id,
                    new_owner=op.payload["new_owner"],
                    bound_human_address=op.payload.get("bound_human_address"),
                )
            else:
                raise SnapshotError(f"unknown pending op {op.kind}")
            applied.append(op.to_dict())
        self.pending = remain
        return applied

    def begin_epoch(
        self,
        *,
        machines,
        humans,
        parent_root: str,
        work_ids_open: list[str],
        demographic_digest: str,
        now: datetime | None = None,
    ) -> EconomicStateSnapshot:
        self.epoch += 1
        applied = self.apply_due_ops(machines, now=now)
        rows = []
        for rec in machines.all():
            rows.append(
                SnapshotMachine(
                    machine_id=rec.machine_id,
                    owner_address=rec.owner_address,
                    machine_index=rec.machine_index,
                    bound_human_address=rec.bound_human_address,
                    status=rec.status,
                    is_first_machine=rec.is_first_machine or rec.machine_index == 1,
                    n_economic=machines.economic_count(rec.owner_address),
                )
            )
        taken = now or datetime.now(UTC)
        snap = EconomicStateSnapshot(
            epoch=self.epoch,
            parent_root=parent_root,
            protocol_version=self.protocol_version,
            economic_rules_version=ECONOMIC_RULES_VERSION,
            taken_at=taken.strftime("%Y-%m-%dT%H:%M:%SZ"),
            h_adult=humans.verified_adult_count(),
            demographic_digest=demographic_digest,
            machines=tuple(rows),
            work_ids_open=tuple(work_ids_open),
            pending_ops=tuple(self.pending),
        )
        self.last_snapshot = snap
        logger.info(
            "epoch=%s snapshot=%s applied=%s machines=%s h_adult=%s",
            self.epoch,
            snap.digest()[:16],
            len(applied),
            len(rows),
            snap.h_adult,
        )
        return snap
