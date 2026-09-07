"""ORG node roles: hosting ≠ replication ≠ consensus (rapport 236).

A JSON list of node names is a *declaration*. It is not a cryptographic
proof that the node may produce, validate, or change governance.

Humans (founder / controller / members) stay distinct from nodes.
TRANSFER_OWNERSHIP is never a node capability.
"""

from __future__ import annotations

from typing import FrozenSet

CAP_HOST = "HOST"
CAP_REPLICATE = "REPLICATE"
CAP_PRODUCE = "PRODUCE"
CAP_VALIDATE = "VALIDATE"
CAP_CHANGE_GOVERNANCE = "CHANGE_GOVERNANCE"

ROLE_HOST_ONLY = "HOST_ONLY"
ROLE_REPLICA = "REPLICA"
ROLE_CONSENSUS = "CONSENSUS"
ROLE_GOVERNANCE = "GOVERNANCE"

ROLE_CAPABILITIES: dict[str, FrozenSet[str]] = {
    ROLE_HOST_ONLY: frozenset({CAP_HOST}),
    ROLE_REPLICA: frozenset({CAP_HOST, CAP_REPLICATE}),
    ROLE_CONSENSUS: frozenset({CAP_HOST, CAP_REPLICATE, CAP_PRODUCE, CAP_VALIDATE}),
    ROLE_GOVERNANCE: frozenset(
        {CAP_HOST, CAP_REPLICATE, CAP_PRODUCE, CAP_VALIDATE, CAP_CHANGE_GOVERNANCE}
    ),
}

HUMAN_ONLY = frozenset({"TRANSFER_OWNERSHIP", "LEGAL_OWNER"})


class NodeRoleError(ValueError):
    """Unknown role or capability denied."""


def capabilities_for(role: str) -> FrozenSet[str]:
    key = (role or ROLE_HOST_ONLY).upper()
    if key not in ROLE_CAPABILITIES:
        raise NodeRoleError(f"unknown_node_role:{role}")
    return ROLE_CAPABILITIES[key]


def can_role(role: str, capability: str) -> bool:
    if capability in HUMAN_ONLY:
        return False
    try:
        return capability in capabilities_for(role)
    except NodeRoleError:
        return False


def declared_role(authorized: bool, role: str | None) -> str:
    """A name on authorized_nodes without a cert is HOST_ONLY at most."""
    if not authorized:
        return ""
    if not role:
        return ROLE_HOST_ONLY
    return role.upper()
