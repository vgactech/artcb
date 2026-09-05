"""ORG / GROUP / subgroup authority — transferable, Genesis stays immutable.

Same certification rules as a user: session identity, humans only for
control transfer, unique_human_proven is never implied, agents cannot
exceed the human controller. The ORG_ID / group_id never changes.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TRANSFER_REASONS = frozenset(
    {"SALE", "SUCCESSION", "DIRECTOR_CHANGE", "KEY_ROTATION", "DELEGATION_END"}
)
SUBJECT_TYPES = frozenset({"organization", "group", "subgroup"})


class GovernanceError(ValueError):
    """Authority / transfer error."""


class GovernanceForbidden(GovernanceError):
    """Caller is not the current controller."""


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OrgAuthority:
    """Operational authority. Not the Genesis constitution."""

    subject_type: str
    subject_id: str
    domain_id: str
    founder_address: str
    legal_owner: str
    controller_address: str
    parent_id: str | None = None
    threshold: int = 1
    guardians: list[str] = field(default_factory=list)
    status: str = "active"
    successor_id: str | None = None
    unique_human_proven: bool = False
    pending_tx_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["unique_human_proven"] = False
        data["org_id_unchanged"] = True
        return data

    def public_view(self) -> dict[str, Any]:
        return {
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "domain_id": self.domain_id,
            "founder_address": self.founder_address,
            "legal_owner": self.legal_owner,
            "controller_address": self.controller_address,
            "parent_id": self.parent_id,
            "threshold": self.threshold,
            "status": self.status,
            "unique_human_proven": False,
            "projection": "authority_public",
            "contains_private_data": False,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrgAuthority:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        payload["unique_human_proven"] = False
        return cls(**payload)


@dataclass
class ControlTransfer:
    tx_id: str
    subject_type: str
    subject_id: str
    domain_id: str
    reason: str
    old_controller: str
    new_controller: str
    legal_owner_before: str
    legal_owner_after: str
    status: str
    proposed_at: str
    accepted_at: str | None = None
    finalized_at: str | None = None
    revoke_old: bool = True
    unique_human_proven: bool = False
    assurance_source: str = "session"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["unique_human_proven"] = False
        data["org_id_unchanged"] = True
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlTransfer:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        payload["unique_human_proven"] = False
        return cls(**payload)


class GovernanceStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.transfers_path = self.path.parent / "transfers.jsonl"

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return json.loads(self.path.read_text(encoding="utf-8") or "[]")

    def _write_all(self, rows: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def list_all(self) -> list[OrgAuthority]:
        return [OrgAuthority.from_dict(r) for r in self._read_all()]

    def get(self, subject_id: str) -> OrgAuthority | None:
        for row in self._read_all():
            if row.get("subject_id") == subject_id:
                return OrgAuthority.from_dict(row)
        return None

    def _upsert(self, auth: OrgAuthority) -> OrgAuthority:
        rows = self._read_all()
        updated = False
        for index, row in enumerate(rows):
            if row.get("subject_id") == auth.subject_id:
                rows[index] = auth.to_dict()
                updated = True
                break
        if not updated:
            rows.append(auth.to_dict())
        self._write_all(rows)
        return auth

    def initialize(
        self,
        *,
        subject_type: str,
        subject_id: str,
        domain_id: str,
        founder_address: str,
        parent_id: str | None = None,
    ) -> OrgAuthority:
        if subject_type not in SUBJECT_TYPES:
            raise GovernanceError(f"unknown_subject_type:{subject_type}")
        existing = self.get(subject_id)
        if existing:
            return existing
        now = _now_iso()
        return self._upsert(
            OrgAuthority(
                subject_type=subject_type,
                subject_id=subject_id,
                domain_id=domain_id,
                founder_address=founder_address,
                legal_owner=founder_address,
                controller_address=founder_address,
                parent_id=parent_id,
                created_at=now,
                updated_at=now,
            )
        )

    def require_human_controller(self, principal, subject_id: str) -> OrgAuthority:
        if getattr(principal, "kind", None) == "agent":
            raise GovernanceForbidden("agent_cannot_transfer_or_admin_org")
        if not getattr(principal, "address", None):
            raise GovernanceForbidden("authentication_required")
        auth = self.get(subject_id)
        if auth is None:
            raise GovernanceError("authority_not_found")
        if principal.address != auth.controller_address:
            raise GovernanceForbidden("controller_mismatch")
        return auth

    def is_controller(self, address: str | None, subject_id: str) -> bool:
        auth = self.get(subject_id)
        return bool(auth and address and address == auth.controller_address)

    def propose_transfer(
        self,
        *,
        principal,
        subject_id: str,
        new_controller: str,
        reason: str,
        revoke_old: bool = True,
    ) -> ControlTransfer:
        if reason not in TRANSFER_REASONS:
            raise GovernanceError(f"unknown_transfer_reason:{reason}")
        if not new_controller or new_controller == getattr(principal, "address", None):
            raise GovernanceError("invalid_new_controller")
        auth = self.require_human_controller(principal, subject_id)
        if auth.pending_tx_id:
            existing = self.get_transfer(auth.pending_tx_id)
            if existing and existing.status == "proposed":
                raise GovernanceError("transfer_already_proposed")
        legal_after = new_controller if reason == "SALE" else auth.legal_owner
        tx = ControlTransfer(
            tx_id=f"xfer_{uuid.uuid4().hex[:16]}",
            subject_type=auth.subject_type,
            subject_id=auth.subject_id,
            domain_id=auth.domain_id,
            reason=reason,
            old_controller=auth.controller_address,
            new_controller=new_controller,
            legal_owner_before=auth.legal_owner,
            legal_owner_after=legal_after,
            status="proposed",
            proposed_at=_now_iso(),
            revoke_old=revoke_old,
            assurance_source=getattr(principal, "source", "session") or "session",
        )
        auth.pending_tx_id = tx.tx_id
        auth.updated_at = tx.proposed_at
        self._upsert(auth)
        self._append_transfer(tx)
        return tx

    def cancel_transfer(self, *, principal, tx_id: str) -> ControlTransfer:
        if getattr(principal, "kind", None) == "agent":
            raise GovernanceForbidden("agent_cannot_transfer_or_admin_org")
        tx = self.get_transfer(tx_id)
        if tx is None:
            raise GovernanceError("transfer_not_found")
        if tx.status != "proposed":
            raise GovernanceError(f"transfer_not_proposed:{tx.status}")
        auth = self.require_human_controller(principal, tx.subject_id)
        if principal.address != auth.controller_address:
            raise GovernanceForbidden("controller_mismatch")
        tx.status = "cancelled"
        tx.finalized_at = _now_iso()
        auth.pending_tx_id = None
        auth.updated_at = tx.finalized_at
        self._upsert(auth)
        self._append_transfer(tx)
        return tx

    def decline_transfer(self, *, principal, tx_id: str) -> ControlTransfer:
        if getattr(principal, "kind", None) == "agent":
            raise GovernanceForbidden("agent_cannot_transfer_or_admin_org")
        if not getattr(principal, "address", None):
            raise GovernanceForbidden("authentication_required")
        tx = self.get_transfer(tx_id)
        if tx is None:
            raise GovernanceError("transfer_not_found")
        if tx.status != "proposed":
            raise GovernanceError(f"transfer_not_proposed:{tx.status}")
        if principal.address != tx.new_controller:
            raise GovernanceForbidden("acceptor_mismatch")
        tx.status = "declined"
        tx.accepted_at = _now_iso()
        tx.finalized_at = tx.accepted_at
        auth = self.get(tx.subject_id)
        if auth:
            auth.pending_tx_id = None
            auth.updated_at = tx.finalized_at
            self._upsert(auth)
        self._append_transfer(tx)
        return tx

    def accept_transfer(self, *, principal, tx_id: str) -> ControlTransfer:
        if getattr(principal, "kind", None) == "agent":
            raise GovernanceForbidden("agent_cannot_transfer_or_admin_org")
        if not getattr(principal, "address", None):
            raise GovernanceForbidden("authentication_required")
        tx = self.get_transfer(tx_id)
        if tx is None:
            raise GovernanceError("transfer_not_found")
        if tx.status != "proposed":
            raise GovernanceError(f"transfer_not_proposed:{tx.status}")
        if principal.address != tx.new_controller:
            raise GovernanceForbidden("acceptor_mismatch")
        auth = self.get(tx.subject_id)
        if auth is None:
            raise GovernanceError("authority_not_found")
        if auth.controller_address != tx.old_controller:
            raise GovernanceError("controller_changed_since_propose")
        auth.controller_address = tx.new_controller
        if tx.reason == "SALE":
            auth.legal_owner = tx.legal_owner_after
        auth.pending_tx_id = None
        auth.updated_at = _now_iso()
        self._upsert(auth)
        tx.status = "finalized"
        tx.accepted_at = auth.updated_at
        tx.finalized_at = auth.updated_at
        self._append_transfer(tx)
        return tx

    def get_transfer(self, tx_id: str) -> ControlTransfer | None:
        last: ControlTransfer | None = None
        for row in self.list_transfers():
            if row.tx_id == tx_id:
                last = row
        return last

    def list_transfers(self, subject_id: str | None = None) -> list[ControlTransfer]:
        if not self.transfers_path.is_file():
            return []
        rows: list[ControlTransfer] = []
        for line in self.transfers_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            tx = ControlTransfer.from_dict(json.loads(line))
            if subject_id is None or tx.subject_id == subject_id:
                rows.append(tx)
        return rows

    def _append_transfer(self, tx: ControlTransfer) -> None:
        with self.transfers_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(tx.to_dict(), ensure_ascii=False) + "\n")
