"""R349 — USER ↔ WALLET ownership bind (challenge + signature).

LOCAL_NODE persistence today; designed so the record can become a
REPLICATED_PROTOCOL event later (same fields + event_id/hash).

Does NOT claim UNIQUE_HUMAN.
Does NOT replace USER↔NODE (R348).
Does NOT change DEVICE_CLIENT wallet create limits (R345).
Never accepts seed/private_key on the wire.
"""

MODULE_VERSION = '1.0.0'  # R390 — auto-versioning
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

PROTOCOL = "r349-user-wallet-ownership-v1"
CHALLENGE_TTL_S = 300
FORBIDDEN_BODY_KEYS = frozenset(
    {
        "private_key",
        "privateKey",
        "privkey",
        "seed",
        "seed_hex",
        "secret",
        "secret_key",
        "kem_secret",
        "mnemonic",
    }
)


class UserWalletBindError(ValueError):
    pass


@dataclass
class OwnershipRecord:
    """Canonical fields — keep stable for future replication."""

    wallet_address: str
    owner_public_key_hex: str
    user_label: str
    node_id: str
    challenge_sha256: str
    created_ts_ns: int
    protocol: str = PROTOCOL
    persistence: str = "LOCAL_NODE"
    replication_target: str = "REPLICATED_PROTOCOL"
    unique_human: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def content_hash(self) -> str:
        payload = {
            "protocol": self.protocol,
            "wallet_address": self.wallet_address,
            "owner_public_key_hex": self.owner_public_key_hex,
            "user_label": self.user_label,
            "node_id": self.node_id,
            "challenge_sha256": self.challenge_sha256,
            "created_ts_ns": self.created_ts_ns,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


def reject_private_key_fields(payload: dict[str, Any]) -> None:
    bad = sorted(k for k in payload.keys() if k in FORBIDDEN_BODY_KEYS)
    if bad:
        raise UserWalletBindError(f"private_key_fields_forbidden:{','.join(bad)}")


def canonical_message(
    *,
    challenge: str,
    wallet_address: str,
    owner_public_key_hex: str,
    user_label: str,
    node_id: str,
) -> bytes:
    line = "|".join(
        [
            PROTOCOL,
            challenge.strip(),
            wallet_address.strip(),
            owner_public_key_hex.strip().lower(),
            user_label.strip(),
            node_id.strip(),
        ]
    )
    return line.encode("utf-8")


def issue_challenge(
    *,
    wallet_address: str,
    node_id: str,
    store: dict[str, dict[str, Any]],
    ttl_s: int = CHALLENGE_TTL_S,
) -> dict[str, Any]:
    challenge = secrets.token_hex(32)
    store[challenge] = {
        "wallet_address": wallet_address.strip(),
        "node_id": node_id.strip(),
        "expires_at": time.time() + ttl_s,
        "protocol": PROTOCOL,
    }
    return {
        "protocol": PROTOCOL,
        "challenge": challenge,
        "wallet_address": wallet_address.strip(),
        "node_id": node_id.strip(),
        "expires_in": ttl_s,
        "sign_over": "canonical_message",
        "persistence": "LOCAL_NODE",
        "replication_target": "REPLICATED_PROTOCOL",
        "unique_human": False,
        "certified_100": False,
        "instructions": (
            "Sign canonical_message with the wallet Ed25519 private key locally. "
            "Never send seed/private_key. Ownership ≠ UNIQUE_HUMAN."
        ),
    }


def verify_and_build(
    *,
    challenge: str,
    store: dict[str, dict[str, Any]],
    owner_public_key_hex: str,
    signature_hex: str,
    user_label: str = "",
) -> OwnershipRecord:
    pending = store.pop(challenge, None)
    if not pending:
        raise UserWalletBindError("challenge_unknown")
    if time.time() > float(pending["expires_at"]):
        raise UserWalletBindError("challenge_expired")

    wallet_address = str(pending["wallet_address"])
    node_id = str(pending["node_id"])
    label = (user_label or "").strip() or wallet_address
    msg = canonical_message(
        challenge=challenge,
        wallet_address=wallet_address,
        owner_public_key_hex=owner_public_key_hex,
        user_label=label,
        node_id=node_id,
    )
    try:
        vk = VerifyKey(bytes.fromhex(owner_public_key_hex.strip()))
        vk.verify(msg, bytes.fromhex(signature_hex.strip()))
    except (BadSignatureError, ValueError) as exc:
        raise UserWalletBindError("signature_invalid") from exc

    return OwnershipRecord(
        wallet_address=wallet_address,
        owner_public_key_hex=owner_public_key_hex.strip().lower(),
        user_label=label,
        node_id=node_id,
        challenge_sha256=hashlib.sha256(challenge.encode()).hexdigest(),
        created_ts_ns=time.time_ns(),
    )


class UserWalletOwnershipStore:
    """LOCAL_NODE store — fields chosen to map 1:1 into a future replicated event."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _write(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def upsert(self, rec: OwnershipRecord) -> dict[str, Any]:
        row = rec.to_dict()
        row["content_hash"] = rec.content_hash()
        row["event_id"] = f"uw_{row['content_hash'][:32]}"
        rows = self._read()
        out: list[dict] = []
        replaced = False
        for existing in rows:
            if existing.get("wallet_address") == rec.wallet_address:
                out.append(row)
                replaced = True
            else:
                out.append(existing)
        if not replaced:
            out.append(row)
        self._write(out)
        return row

    def get(self, wallet_address: str) -> dict | None:
        addr = wallet_address.strip()
        for row in self._read():
            if row.get("wallet_address") == addr:
                return row
        return None

    def list_all(self) -> list[dict]:
        return self._read()
