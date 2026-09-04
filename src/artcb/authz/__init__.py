"""ARTCB Authorization & Privacy Policy Engine (rapport 216).

Membership + visibility classification is not an ACL. This package is the
authorization layer: GRANT/REVOKE transactions, DENY>ALLOW, agent ceiling.
Consensus does not decide who may read Document X.
"""

from src.artcb.authz.actions import ALL_ACTIONS, READ
from src.artcb.authz.engine import AuthorizationEngine
from src.artcb.authz.gate import AuthzGate
from src.artcb.authz.models import Decision, PolicyTx, Principal, ResourceRef

__all__ = [
    "ALL_ACTIONS",
    "READ",
    "AuthorizationEngine",
    "AuthzGate",
    "Decision",
    "PolicyTx",
    "Principal",
    "ResourceRef",
]
