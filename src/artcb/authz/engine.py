"""Authorization engine — DENY > ALLOW, least privilege, agent ceiling.

Consensus (PoL / block validity) is a different question. This engine only
answers: may this principal do this action on this resource?
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.artcb.authz import actions
from src.artcb.authz.models import Decision, PolicyTx, Principal, ResourceRef


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _expired(tx: PolicyTx, now: str) -> bool:
    return bool(tx.expires_at and now >= tx.expires_at)


class AuthorizationEngine:
    """Evaluate P_effective = P_allowed − P_denied, with DENY winning.

    Layers (all must not DENY; an ALLOW at any matching layer is enough
    unless a DENY also matches):

        organization ∩ group ∩ subgroup ∩ resource ∩ user ∩ agent

    An agent never exceeds its human parent: even an explicit agent GRANT
    is clipped by the human's effective permission.
    """

    def __init__(
        self,
        *,
        groups,
        policies: list[PolicyTx] | None = None,
    ) -> None:
        self.groups = groups
        self.policies: list[PolicyTx] = list(policies or [])

    def set_policies(self, policies: list[PolicyTx]) -> None:
        self.policies = list(policies)

    def authorize(
        self,
        principal: Principal,
        action: str,
        resource: ResourceRef,
        *,
        now: str | None = None,
        _skip_agent_ceiling: bool = False,
    ) -> Decision:
        now = now or _now_iso()
        action = action.upper()

        if principal.kind == "agent" and not _skip_agent_ceiling:
            human = Principal(
                address=principal.parent_address,
                kind="human",
                source=principal.source,
            )
            human_decision = self.authorize(
                human, action, resource, now=now, _skip_agent_ceiling=True
            )
            if not human_decision.allowed:
                return Decision(
                    "DENY",
                    "agent_exceeds_human_ceiling",
                    matched_tx_ids=human_decision.matched_tx_ids,
                    policy_version=human_decision.policy_version,
                )
            agent_decision = self._decide(principal, action, resource, now)
            if not agent_decision.allowed:
                return agent_decision
            return Decision(
                "ALLOW",
                "agent_grant_within_human_ceiling",
                matched_tx_ids=agent_decision.matched_tx_ids + human_decision.matched_tx_ids,
                policy_version=max(
                    filter(None, [agent_decision.policy_version, human_decision.policy_version]),
                    default=None,
                ),
            )

        return self._decide(principal, action, resource, now)

    def _decide(
        self,
        principal: Principal,
        action: str,
        resource: ResourceRef,
        now: str,
    ) -> Decision:
        denies, allows = self._matching(principal, action, resource, now)
        if denies:
            latest = max(denies, key=lambda t: t.policy_version)
            return Decision(
                "DENY",
                "explicit_deny",
                matched_tx_ids=[t.tx_id for t in denies],
                policy_version=latest.policy_version,
            )

        implicit = self._implicit_allow(principal, action, resource)
        if allows or implicit:
            reason = "policy_grant" if allows else implicit or "allow"
            latest_ver = max((t.policy_version for t in allows), default=None)
            return Decision(
                "ALLOW",
                reason,
                matched_tx_ids=[t.tx_id for t in allows],
                policy_version=latest_ver,
            )
        return Decision("DENY", "default_deny")

    def _matching(
        self,
        principal: Principal,
        action: str,
        resource: ResourceRef,
        now: str,
    ) -> tuple[list[PolicyTx], list[PolicyTx]]:
        subject = principal.subject_id()
        human = principal.human_subject()
        denies: list[PolicyTx] = []
        allows: list[PolicyTx] = []
        for tx in self.policies:
            if not tx.active or tx.op == "REVOKE" or _expired(tx, now):
                continue
            if tx.action not in (action, "*"):
                continue
            if not tx.resource.covers(resource):
                continue
            if principal.kind == "agent":
                if tx.subject != subject:
                    continue
            else:
                if tx.subject != subject and tx.subject != human:
                    continue
            if tx.effect == "DENY":
                denies.append(tx)
            elif tx.effect == "ALLOW":
                allows.append(tx)
        return denies, allows

    def _implicit_allow(
        self,
        principal: Principal,
        action: str,
        resource: ResourceRef,
    ) -> str | None:
        """Classification defaults. Never treat `private` as a permission."""
        vis = (resource.visibility or "private").lower()

        if vis == "unstored" and action == actions.READ:
            return "unstored_working_copy"

        if vis == "public" and action == actions.READ:
            return "public_read"
        if vis == "public" and action == actions.EXPORT:
            return "public_export"

        if principal.kind == "agent":
            # Agents never inherit membership/ownership. Only explicit GRANTs
            # (already collected) plus the human ceiling.
            return None

        if not principal.address:
            return None

        if resource.owner_address and resource.owner_address == principal.address:
            return "resource_owner"

        if vis == "group":
            role = self._role_for(principal.address, resource)
            if role is None:
                return None
            if action == actions.READ and role in actions.MEMBER_READ_ROLES:
                return "group_member_read"
            if action in actions.WRITE_LIKE and role in actions.MEMBER_WRITE_ROLES:
                return "group_member_write"
            if action in actions.ADMIN_LIKE and role in actions.MEMBER_ADMIN_ROLES:
                return "group_member_admin"
        return None

    def _role_for(self, address: str, resource: ResourceRef) -> str | None:
        """Least privilege on the tree: subgroup membership does not fall back
        to the parent group. C2 ∈ Group C is not enough to read Sub2.
        """
        if not self.groups:
            return None
        if resource.subgroup_id:
            return self._member_role(resource.subgroup_id, address)
        if resource.group_id:
            return self._member_role(resource.group_id, address)
        return None

    def _member_role(self, group_id: str, address: str) -> str | None:
        group = self.groups.get_group(group_id)
        if not group or group.dissolved:
            return None
        for member in group.members:
            if member.address == address:
                return member.role
        return None
