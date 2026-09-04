"""Append-only policy log + resource index (sidecar, not chain consensus).

Authorization is not consensus. Block hashes stay unchanged. Owner,
subgroup and resource_id live here so a GRANT can name Document X
without rewriting Genesis or the block body.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.artcb.authz.models import PolicyTx, ResourceRef

logger = logging.getLogger("artcb.authz.store")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PolicyStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self.path.write_text("", encoding="utf-8")

    def load(self) -> list[PolicyTx]:
        txs: list[PolicyTx] = []
        if not self.path.is_file():
            return txs
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                txs.append(PolicyTx.from_dict(json.loads(line)))
        return txs

    def next_version(self) -> int:
        txs = self.load()
        return (max((t.policy_version for t in txs), default=0) + 1)

    def append(self, tx: PolicyTx) -> PolicyTx:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(tx.to_dict(), ensure_ascii=False) + "\n")
        logger.debug("authz tx %s op=%s effect=%s subject=%s", tx.tx_id, tx.op, tx.effect, tx.subject[:16])
        return tx

    def grant(
        self,
        *,
        subject: str,
        action: str,
        resource: ResourceRef,
        issuer: str,
        effect: str = "ALLOW",
        subject_kind: str = "human",
        parent_subject: str | None = None,
        expires_at: str | None = None,
        delegation: bool = False,
    ) -> PolicyTx:
        tx = PolicyTx(
            tx_id=f"pol_{uuid.uuid4().hex[:16]}",
            policy_version=self.next_version(),
            effect=effect,  # type: ignore[arg-type]
            op="GRANT",
            subject=subject,
            action=action.upper(),
            resource=resource,
            issuer=issuer,
            issued_at=_now_iso(),
            subject_kind=subject_kind,  # type: ignore[arg-type]
            parent_subject=parent_subject,
            expires_at=expires_at,
            delegation=delegation,
            active=True,
        )
        return self.append(tx)

    def revoke(self, *, target_tx_id: str, issuer: str) -> PolicyTx:
        current = self.load()
        target = next((t for t in current if t.tx_id == target_tx_id), None)
        if target is None:
            raise KeyError(target_tx_id)
        now = _now_iso()
        rewritten: list[PolicyTx] = []
        for tx in current:
            if tx.tx_id == target_tx_id:
                tx.active = False
                tx.revoked_at = now
                tx.revoked_by = issuer
            rewritten.append(tx)
        with self.path.open("w", encoding="utf-8") as handle:
            for tx in rewritten:
                handle.write(json.dumps(tx.to_dict(), ensure_ascii=False) + "\n")
        revoke_tx = PolicyTx(
            tx_id=f"pol_{uuid.uuid4().hex[:16]}",
            policy_version=self.next_version(),
            effect="DENY",
            op="REVOKE",
            subject=target.subject,
            action=target.action,
            resource=target.resource,
            issuer=issuer,
            issued_at=now,
            subject_kind=target.subject_kind,
            parent_subject=target.parent_subject,
            active=True,
            target_tx_id=target_tx_id,
        )
        return self.append(revoke_tx)


class ResourceIndex:
    """Sidecar map graph_id / block_index → ACL attributes."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self.path.write_text("", encoding="utf-8")
        self._by_graph: dict[str, dict[str, Any]] = {}
        self._by_resource: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        self._by_graph = {}
        self._by_resource = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            gid = row.get("graph_id")
            if gid:
                self._by_graph[gid] = row
            rid = row.get("resource_id")
            if rid:
                self._by_resource[rid] = row

    def record(
        self,
        *,
        graph_id: str,
        visibility: str,
        owner_address: str | None = None,
        group_id: str | None = None,
        subgroup_id: str | None = None,
        resource_id: str | None = None,
        organization_id: str | None = None,
        block_index: int | None = None,
    ) -> dict[str, Any]:
        row = {
            "graph_id": graph_id,
            "visibility": visibility,
            "owner_address": owner_address,
            "group_id": group_id,
            "subgroup_id": subgroup_id,
            "resource_id": resource_id,
            "organization_id": organization_id,
            "block_index": block_index,
            "indexed_at": _now_iso(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._by_graph[graph_id] = row
        if resource_id:
            self._by_resource[resource_id] = row
        return row

    def get_by_graph(self, graph_id: str) -> dict[str, Any] | None:
        return self._by_graph.get(graph_id)

    def get_by_resource_id(self, resource_id: str) -> dict[str, Any] | None:
        return self._by_resource.get(resource_id)

    def as_resource(self, graph_id: str) -> ResourceRef | None:
        row = self.get_by_graph(graph_id)
        if not row:
            return None
        return self._row_to_resource(row)

    def as_resource_id(self, resource_id: str) -> ResourceRef | None:
        row = self.get_by_resource_id(resource_id)
        if not row:
            return None
        return self._row_to_resource(row)

    @staticmethod
    def _row_to_resource(row: dict[str, Any]) -> ResourceRef:
        return ResourceRef(
            visibility=row.get("visibility"),
            owner_address=row.get("owner_address"),
            organization_id=row.get("organization_id"),
            group_id=row.get("group_id"),
            subgroup_id=row.get("subgroup_id"),
            resource_id=row.get("resource_id"),
            graph_id=row.get("graph_id"),
            block_index=row.get("block_index"),
        )
