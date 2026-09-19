"""R343 — QR phone pairing for biometric / WebAuthn fallback (scaffold).

PC without camera/authenticator → short-lived pairing session → phone produces
WebAuthn + liveness proof. QR is not itself human validation.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib
import secrets
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PairingState(str, Enum):
    UNUSED = "UNUSED"
    USED = "USED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


@dataclass
class PairingSession:
    protocol: str = "r343-qr-pairing-v1"
    session_id: str = ""
    nonce: str = ""
    created_ts_ns: int = 0
    expires_ts_ns: int = 0
    state: str = PairingState.UNUSED.value
    expected_user: str | None = None
    domain: str = "artcb.me"
    ttl_s: int = 120

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        # never expose long-term secrets; nonce is short-lived challenge
        return d


def create_pairing_session(
    *,
    ttl_s: int = 120,
    expected_user: str | None = None,
    domain: str = "artcb.me",
) -> PairingSession:
    now = time.time_ns()
    sid = "S" + secrets.token_hex(16)
    nonce = secrets.token_hex(16)
    return PairingSession(
        session_id=sid,
        nonce=nonce,
        created_ts_ns=now,
        expires_ts_ns=now + ttl_s * 1_000_000_000,
        expected_user=expected_user,
        domain=domain,
        ttl_s=ttl_s,
    )


def qr_payload(session: PairingSession, *, base_url: str = "https://artcb.me") -> str:
    """Deep link only — no permanent secret in QR."""
    return f"{base_url.rstrip('/')}/pair/{session.session_id}"


def consume_pairing(session: PairingSession, *, now_ns: int | None = None) -> PairingSession:
    now = now_ns if now_ns is not None else time.time_ns()
    if session.state != PairingState.UNUSED.value:
        session.state = PairingState.REJECTED.value
        return session
    if now > session.expires_ts_ns:
        session.state = PairingState.EXPIRED.value
        return session
    session.state = PairingState.USED.value
    return session


def capability_matrix(
    *,
    camera_available: bool,
    authenticator_available: bool,
) -> dict[str, Any]:
    """Browser capability detection — not absolute hardware inventory."""
    if camera_available and authenticator_available:
        path = "local_enroll"
    elif (not camera_available) and authenticator_available:
        path = "policy_alt_or_qr"
    elif camera_available and (not authenticator_available):
        path = "qr_or_external_authenticator"
    else:
        path = "qr_phone_required"
    return {
        "CAMERA_AVAILABLE": camera_available,
        "AUTHENTICATOR_AVAILABLE": authenticator_available,
        "recommended_path": path,
        "levels_preserved": [
            "WALLET_CREATED",
            "DEVICE_AUTHENTICATED",
            "LIVE_HUMAN_VERIFIED",
            "UNIQUE_HUMAN_VERIFIED",
        ],
        "note": "QR success ≠ UNIQUE_HUMAN_VERIFIED automatically",
        "certified_100": False,
    }


def session_fingerprint(session: PairingSession) -> str:
    raw = f"{session.session_id}|{session.nonce}|{session.expires_ts_ns}"
    return hashlib.sha256(raw.encode()).hexdigest()
