"""HTTP-facing authorization gate: identity + engine + chain sidecar."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from src.artcb.authz.actions import GRANT, READ, REVOKE
from src.artcb.authz.engine import AuthorizationEngine
from src.artcb.authz.genesis import GenesisStore
from src.artcb.authz.identity import resolve_principal
from src.artcb.authz.models import Decision, Principal, ResourceRef
from src.artcb.authz.governance import GovernanceStore
from src.artcb.authz.registry import DomainRegistry
from src.artcb.authz.store import PolicyStore, ResourceIndex


def _owner_from_block(block: dict[str, Any]) -> str | None:
    for row in block.get("contributors") or []:
        addr = row.get("address")
        if addr:
            return str(addr)
    return None


class AuthzGate:
    def __init__(self, *, data_dir, groups, chain) -> None:
        root = data_dir / "authz"
        self.policies = PolicyStore(root / "policies.jsonl")
        self.index = ResourceIndex(root / "resources.jsonl")
        self.genesis = GenesisStore(root / "orgs.json")
        self.domains = DomainRegistry(root / "domains.json")
        self.governance = GovernanceStore(root / "governance.json")
        self.groups = groups
        self.chain = chain
        self.engine = AuthorizationEngine(groups=groups, policies=self.policies.load())

    def reload(self) -> None:
        self.engine.set_policies(self.policies.load())

    def resolve(self, request: Request, *, required: bool = False) -> Principal:
        return resolve_principal(request, required=required)

    def resource_for_block(self, block: dict[str, Any]) -> ResourceRef:
        graph_id = str(block.get("graph_id") or "")
        indexed = self.index.as_resource(graph_id) if graph_id else None
        owner = (indexed.owner_address if indexed else None) or _owner_from_block(block)
        return ResourceRef(
            visibility=str(block.get("visibility") or "private"),
            owner_address=owner,
            organization_id=indexed.organization_id if indexed else None,
            group_id=(indexed.group_id if indexed else None) or block.get("group_id"),
            subgroup_id=indexed.subgroup_id if indexed else None,
            resource_id=indexed.resource_id if indexed else None,
            graph_id=graph_id or None,
            block_index=block.get("index"),
        )

    def resource_for_graph(self, graph_id: str) -> ResourceRef:
        indexed = self.index.as_resource(graph_id)
        if indexed:
            return indexed
        try:
            blocks = self.chain.list_blocks()
        except FileNotFoundError:
            blocks = []
        for block in blocks:
            if block.get("graph_id") == graph_id:
                return self.resource_for_block(block)
        return ResourceRef(visibility="unstored", graph_id=graph_id)

    def decide(
        self,
        principal: Principal,
        action: str,
        resource: ResourceRef,
    ) -> Decision:
        self.reload()
        return self.engine.authorize(principal, action, resource)

    def allow_block(self, principal: Principal, block: dict[str, Any], action: str = READ) -> bool:
        return self.decide(principal, action, self.resource_for_block(block)).allowed

    def filter_blocks(
        self,
        principal: Principal,
        blocks: list[dict[str, Any]],
        action: str = READ,
    ) -> list[dict[str, Any]]:
        return [b for b in blocks if self.allow_block(principal, b, action)]

    def assert_graph(self, request: Request, graph_id: str, action: str = READ) -> Principal:
        principal = self.resolve(request)
        decision = self.decide(principal, action, self.resource_for_graph(graph_id))
        if decision.allowed:
            return principal
        raise HTTPException(status_code=404, detail="graph not found")

    def assert_block(self, request: Request, block: dict[str, Any], action: str = READ) -> Principal:
        principal = self.resolve(request)
        if self.allow_block(principal, block, action):
            return principal
        raise HTTPException(status_code=404, detail="block not found")

    def _is_subject_controller(self, address: str | None, resource: ResourceRef) -> bool:
        if not address:
            return False
        for sid in (resource.organization_id, resource.group_id, resource.subgroup_id):
            if sid and self.governance.is_controller(address, sid):
                return True
        return False

    def can_issue_grant(self, principal: Principal, resource: ResourceRef) -> Decision:
        owner = resource.owner_address and principal.address == resource.owner_address
        if owner:
            return Decision("ALLOW", "resource_owner")
        if self._is_subject_controller(principal.address, resource):
            return Decision("ALLOW", "org_or_group_controller")
        return self.decide(principal, GRANT, resource)

    def can_revoke(self, principal: Principal, resource: ResourceRef) -> Decision:
        owner = resource.owner_address and principal.address == resource.owner_address
        if owner:
            return Decision("ALLOW", "resource_owner")
        if self._is_subject_controller(principal.address, resource):
            return Decision("ALLOW", "org_or_group_controller")
        return self.decide(principal, REVOKE, resource)
