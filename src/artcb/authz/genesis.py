"""Genesis objects = constitutions. Individual grants live in store.py.

ORG / GROUP genesis bodies stay in the local domain store. Only
``public_commitment`` rows (kind + id + hash) are safe to show the
whole network. See domains.py for the replication matrix.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.artcb.authz.actions import ALL_ACTIONS
from src.artcb.authz.domains import canonical_hash, public_commitment


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OrgGenesis:
    """Constitution of an organisation — not the permission database."""

    organization_id: str
    name: str
    founder_address: str
    created_at: str
    parent_root: str = "ARTCB"
    governance_root: str = ""
    policy_root: str = "v0"
    membership_root: str = ""
    key_root: str = ""
    audit_root: str = ""
    allowed_actions: list[str] = field(default_factory=lambda: list(ALL_ACTIONS))
    deny_wins: bool = True
    agent_ceiling: bool = True
    allowed_delegations: list[str] = field(default_factory=lambda: ["READ", "WRITE", "GRANT", "REVOKE"])
    forbidden_delegations: list[str] = field(default_factory=lambda: ["ADMIN_ORG"])
    content_hash: str = ""
    domain_kind: str = "org"

    def constitution_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("content_hash", None)
        return data

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload.get("content_hash"):
            payload["content_hash"] = canonical_hash(self.constitution_payload())
        return payload

    def public_view(self) -> dict[str, Any]:
        """Existence + hash. No member list, no documents."""
        return {
            "organization_id": self.organization_id,
            "name": self.name,
            "parent_root": self.parent_root,
            "content_hash": self.content_hash or canonical_hash(self.constitution_payload()),
            "deny_wins": self.deny_wins,
            "agent_ceiling": self.agent_ceiling,
            "projection": "public_commitment",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrgGenesis:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class GroupGenesis:
    """Constitution of a group / subgroup — depends on an ORG, never rewrites global genesis."""

    group_id: str
    name: str
    founder_address: str
    created_at: str
    parent_org: str | None = None
    parent_group_id: str | None = None
    policy_root: str = "v0"
    membership_root: str = ""
    allowed_actions: list[str] = field(default_factory=lambda: ["READ", "WRITE", "CREATE", "GRANT", "REVOKE"])
    forbidden_delegations: list[str] = field(default_factory=lambda: ["ADMIN_ORG"])
    content_hash: str = ""
    domain_kind: str = "group"

    def constitution_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("content_hash", None)
        return data

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload.get("content_hash"):
            payload["content_hash"] = canonical_hash(self.constitution_payload())
        return payload

    def public_view(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "parent_org": self.parent_org,
            "parent_group_id": self.parent_group_id,
            "content_hash": self.content_hash or canonical_hash(self.constitution_payload()),
            "projection": "public_commitment",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroupGenesis:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class CommitmentLog:
    """Append-only public commitments (hashes). Safe to list to any node."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self.path.write_text("", encoding="utf-8")

    def append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def list_all(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows


class GenesisStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.groups_path = self.path.parent / "group_genesis.json"
        self.commitments = CommitmentLog(self.path.parent / "commitments.jsonl")

    def _read_all(self, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        return json.loads(path.read_text(encoding="utf-8") or "[]")

    def _write_all(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def create_org(self, name: str, founder_address: str) -> OrgGenesis:
        org = OrgGenesis(
            organization_id=f"org_{uuid.uuid4().hex[:12]}",
            name=name,
            founder_address=founder_address,
            created_at=_now_iso(),
            governance_root=founder_address,
            membership_root=founder_address,
        )
        org.content_hash = canonical_hash(org.constitution_payload())
        rows = self._read_all(self.path)
        rows.append(org.to_dict())
        self._write_all(self.path, rows)
        self.commitments.append(
            public_commitment(
                kind="org",
                domain_id=org.organization_id,
                content_hash=org.content_hash,
                parent_id="ARTCB",
                issuer=founder_address,
                issued_at=org.created_at,
            )
        )
        return org

    def get_org(self, organization_id: str) -> OrgGenesis | None:
        for row in self._read_all(self.path):
            if row.get("organization_id") == organization_id:
                return OrgGenesis.from_dict(row)
        return None

    def list_orgs(self) -> list[OrgGenesis]:
        return [OrgGenesis.from_dict(r) for r in self._read_all(self.path)]

    def create_group_genesis(
        self,
        *,
        group_id: str,
        name: str,
        founder_address: str,
        parent_org: str | None = None,
        parent_group_id: str | None = None,
    ) -> GroupGenesis:
        genesis = GroupGenesis(
            group_id=group_id,
            name=name,
            founder_address=founder_address,
            created_at=_now_iso(),
            parent_org=parent_org,
            parent_group_id=parent_group_id,
            membership_root=founder_address,
        )
        genesis.content_hash = canonical_hash(genesis.constitution_payload())
        rows = self._read_all(self.groups_path)
        rows.append(genesis.to_dict())
        self._write_all(self.groups_path, rows)
        self.commitments.append(
            public_commitment(
                kind="group",
                domain_id=group_id,
                content_hash=genesis.content_hash,
                parent_id=parent_org or parent_group_id or "ARTCB",
                issuer=founder_address,
                issued_at=genesis.created_at,
            )
        )
        return genesis

    def get_group_genesis(self, group_id: str) -> GroupGenesis | None:
        for row in self._read_all(self.groups_path):
            if row.get("group_id") == group_id:
                return GroupGenesis.from_dict(row)
        return None

    def import_org(self, data: dict[str, Any]) -> OrgGenesis:
        """Install an ORG Genesis body after hash verification. Does not own it."""
        from src.artcb.authz.registry import verify_genesis_hash

        org = OrgGenesis.from_dict(data)
        org.content_hash = verify_genesis_hash(org.to_dict(), data.get("content_hash") or "")
        if self.get_org(org.organization_id):
            raise ValueError("org_already_exists")
        rows = self._read_all(self.path)
        rows.append(org.to_dict())
        self._write_all(self.path, rows)
        self.commitments.append(
            public_commitment(
                kind="org",
                domain_id=org.organization_id,
                content_hash=org.content_hash,
                parent_id="ARTCB",
                issuer=org.founder_address,
                issued_at=org.created_at,
            )
        )
        return org

    def import_group_genesis(self, data: dict[str, Any]) -> GroupGenesis:
        from src.artcb.authz.registry import verify_genesis_hash

        genesis = GroupGenesis.from_dict(data)
        genesis.content_hash = verify_genesis_hash(
            genesis.to_dict(), data.get("content_hash") or ""
        )
        if self.get_group_genesis(genesis.group_id):
            raise ValueError("group_already_exists")
        rows = self._read_all(self.groups_path)
        rows.append(genesis.to_dict())
        self._write_all(self.groups_path, rows)
        self.commitments.append(
            public_commitment(
                kind="group",
                domain_id=genesis.group_id,
                content_hash=genesis.content_hash,
                parent_id=genesis.parent_org or genesis.parent_group_id or "ARTCB",
                issuer=genesis.founder_address,
                issued_at=genesis.created_at,
            )
        )
        return genesis
