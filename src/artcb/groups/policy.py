"""Group security policy flags."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import os


def direct_member_invite_allowed() -> bool:
    """Direct POST /members by address — DEBUG only (insecure for production)."""
    return os.getenv("ARTCB_DEBUG_DIRECT_MEMBER", "false").lower() in ("1", "true", "yes")
