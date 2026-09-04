"""Policy and resource models — individual permissions are versioned txs.

The Genesis (see genesis.py) is the constitution. It does not store
A3→C3 grants. Those are PolicyTx records, signed/audited/revocable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Effect = Literal["ALLOW", "DENY"]
Op = Literal["GRANT", "REVOKE"]
SubjectKind = Literal["human", "agent"]
DecisionEffect = Literal["ALLOW", "DENY"]


@dataclass
class ResourceRef:
    """A resource at any depth of the org → group → subgroup → document tree.

    Unset fields mean "this statement is broader". A GRANT with only
    `group_id=C` covers every document under C. A GRANT with
    `resource_id=doc-x` covers only that document.
    `visibility` is classification, not a permission.
    """

    visibility: str | None = None
    owner_address: str | None = None
    organization_id: str | None = None
    group_id: str | None = None
    subgroup_id: str | None = None
    resource_id: str | None = None
    graph_id: str | None = None
    block_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ResourceRef:
        if not data:
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def covers(self, target: ResourceRef) -> bool:
        """True when this (policy) resource is equal to or broader than target."""
        for name in (
            "organization_id",
            "group_id",
            "subgroup_id",
            "resource_id",
            "graph_id",
            "block_index",
        ):
            policy_val = getattr(self, name)
            target_val = getattr(target, name)
            if policy_val is not None and policy_val != target_val:
                return False
        return True


@dataclass
class Principal:
    address: str | None = None
    wallet_name: str | None = None
    kind: str = "anonymous"  # anonymous | human | agent | operator
    agent_id: str | None = None
    parent_address: str | None = None
    source: str = "anonymous"  # session | api_key | wallet | anonymous | operator

    @property
    def is_anonymous(self) -> bool:
        return not self.address and self.kind == "anonymous"

    def human_subject(self) -> str | None:
        if self.kind == "agent":
            return self.parent_address
        return self.address

    def subject_id(self) -> str | None:
        if self.kind == "agent" and self.agent_id:
            return f"agent:{self.agent_id}"
        return self.address


@dataclass
class PolicyTx:
    tx_id: str
    policy_version: int
    effect: Effect
    op: Op
    subject: str
    action: str
    resource: ResourceRef
    issuer: str
    issued_at: str
    subject_kind: SubjectKind = "human"
    parent_subject: str | None = None
    expires_at: str | None = None
    delegation: bool = False
    active: bool = True
    target_tx_id: str | None = None
    revoked_at: str | None = None
    revoked_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["resource"] = self.resource.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyTx:
        raw = dict(data)
        raw["resource"] = ResourceRef.from_dict(raw.get("resource") or {})
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class Decision:
    effect: DecisionEffect
    reason: str
    matched_tx_ids: list[str] = field(default_factory=list)
    policy_version: int | None = None

    @property
    def allowed(self) -> bool:
        return self.effect == "ALLOW"

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect": self.effect,
            "allowed": self.allowed,
            "reason": self.reason,
            "matched_tx_ids": list(self.matched_tx_ids),
            "policy_version": self.policy_version,
        }
