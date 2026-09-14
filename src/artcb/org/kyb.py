"""R343 — ORG/KYB status model (scaffold; not live-certified)."""

from __future__ import annotations

from enum import Enum
from typing import Any


class OrgKybStatus(str, Enum):
    ORG_CREATED = "ORG_CREATED"
    KYB_PENDING = "KYB_PENDING"
    KYB_IN_REVIEW = "KYB_IN_REVIEW"
    KYB_MORE_INFO = "KYB_MORE_INFO"
    KYB_APPROVED = "KYB_APPROVED"
    ORG_ACTIVE = "ORG_ACTIVE"
    ORG_SUSPENDED = "ORG_SUSPENDED"
    ORG_REVOKED = "ORG_REVOKED"
    ORG_EXPIRED = "ORG_EXPIRED"


REWARD_ELIGIBLE_STATUSES = frozenset({OrgKybStatus.KYB_APPROVED, OrgKybStatus.ORG_ACTIVE})


def reward_eligible(status: OrgKybStatus | str) -> bool:
    s = OrgKybStatus(status) if not isinstance(status, OrgKybStatus) else status
    return s in REWARD_ELIGIBLE_STATUSES


def creator_may_self_validate(*, creator_id: str, validator_id: str) -> bool:
    """Return True iff this validator is allowed to validate the org.

    R345 (2026-09-14T17:20:00Z): hard rule — creator cannot self-validate.
    ~~return creator_id == validator_id~~ was inverted (returned True on self).
    Expected:
      creator=A, validator=A → False (DENY)
      creator=A, validator=B → True (independent validator OK at this gate)
    Controller/UBO conflicts are handled separately by ``conflict_of_interest``.
    """
    c = (creator_id or "").strip()
    v = (validator_id or "").strip()
    if not c or not v:
        return False
    return c != v


def conflict_of_interest(
    *,
    validator_id: str,
    org_controller_ids: list[str],
    ubo_ids: list[str],
) -> bool:
    """True if validator is controller or UBO of the org (DENY)."""
    v = (validator_id or "").strip()
    if not v:
        return True
    controllers = {x.strip() for x in org_controller_ids if (x or "").strip()}
    ubos = {x.strip() for x in ubo_ids if (x or "").strip()}
    return v in controllers or v in ubos


def public_commitment_stub(org_id: str, dossier_hash: str) -> dict[str, Any]:
    """Public network view — no raw documents."""
    return {
        "protocol": "r343-org-kyb-commitment-v1",
        "org_id": org_id,
        "dossier_hash": dossier_hash,
        "includes_raw_documents": False,
        "certified_100": False,
    }
