"""ARTCB Authorization & Privacy Policy Engine (rapport 216).

Membership + visibility classification is not an ACL. This package is the
authorization layer: GRANT/REVOKE transactions, DENY>ALLOW, agent ceiling.
Consensus does not decide who may read Document X.
"""

from src.artcb.authz.actions import ALL_ACTIONS, READ
from src.artcb.authz.domains import REPLICATION_MATRIX, canonical_hash
from src.artcb.authz.engine import AuthorizationEngine
from src.artcb.authz.gate import AuthzGate
from src.artcb.authz.models import Decision, PolicyTx, Principal, ResourceRef
from src.artcb.authz.registry import DomainManifest, DomainRegistry

__all__ = [
    "ALL_ACTIONS",
    "READ",
    "REPLICATION_MATRIX",
    "AuthorizationEngine",
    "AuthzGate",
    "Decision",
    "DomainManifest",
    "DomainRegistry",
    "PolicyTx",
    "Principal",
    "ResourceRef",
    "canonical_hash",
]
