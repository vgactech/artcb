"""Genesis = constitution, not the permission database.

Who governs, which permission mechanisms exist, who may emit policy
transactions. Individual A3→C3 grants are PolicyTx records (store.py).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.artcb.authz.actions import ALL_ACTIONS


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OrgGenesis:
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrgGenesis:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class GenesisStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return json.loads(self.path.read_text(encoding="utf-8") or "[]")

    def _write_all(self, rows: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def create_org(self, name: str, founder_address: str) -> OrgGenesis:
        org = OrgGenesis(
            organization_id=f"org_{uuid.uuid4().hex[:12]}",
            name=name,
            founder_address=founder_address,
            created_at=_now_iso(),
            governance_root=founder_address,
            membership_root=founder_address,
        )
        rows = self._read_all()
        rows.append(org.to_dict())
        self._write_all(rows)
        return org

    def get_org(self, organization_id: str) -> OrgGenesis | None:
        for row in self._read_all():
            if row.get("organization_id") == organization_id:
                return OrgGenesis.from_dict(row)
        return None

    def list_orgs(self) -> list[OrgGenesis]:
        return [OrgGenesis.from_dict(r) for r in self._read_all()]
