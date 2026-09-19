"""R348 — USER ↔ NODE association (challenge + signature; never privkey upload).

Does NOT replace R345 client device binding.
Does NOT claim UNIQUE_HUMAN or CERTIFIED_100.
Does NOT auto-bind wallets to humans (that is R349).
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

PROTOCOL = "r348-user-node-association-v1"
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


class UserNodeAssociationError(ValueError):
    pass


@dataclass
class AssociationRecord:
    user_address: str
    user_public_key_hex: str
    node_id: str
    node_wallet_address: str | None
    role: str  # client | operator
    challenge_sha256: str
    created_ts_ns: int
    protocol: str = PROTOCOL

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def reject_private_key_fields(payload: dict[str, Any]) -> None:
    """I5 — never accept user/node private key material on the wire."""
    bad = sorted(k for k in payload.keys() if k in FORBIDDEN_BODY_KEYS)
    if bad:
        raise UserNodeAssociationError(f"private_key_fields_forbidden:{','.join(bad)}")


def canonical_message(
    *,
    challenge: str,
    node_id: str,
    node_wallet_address: str | None,
    user_address: str,
    role: str,
) -> bytes:
    """Deterministic UTF-8 payload the user must sign (not the raw seed)."""
    line = "|".join(
        [
            PROTOCOL,
            challenge.strip(),
            node_id.strip(),
            (node_wallet_address or "").strip(),
            user_address.strip(),
            role.strip(),
        ]
    )
    return line.encode("utf-8")


def issue_challenge(
    *,
    node_id: str,
    node_wallet_address: str | None,
    store: dict[str, dict[str, Any]],
    ttl_s: int = CHALLENGE_TTL_S,
) -> dict[str, Any]:
    challenge = secrets.token_hex(32)
    now = time.time()
    store[challenge] = {
        "node_id": node_id,
        "node_wallet_address": node_wallet_address,
        "expires_at": now + ttl_s,
        "protocol": PROTOCOL,
    }
    return {
        "protocol": PROTOCOL,
        "challenge": challenge,
        "node_id": node_id,
        "node_wallet_address": node_wallet_address,
        "expires_in": ttl_s,
        "sign_over": "canonical_message",
        "instructions": (
            "Sign canonical_message(challenge,node_id,node_wallet_address,user_address,role) "
            "with User Ed25519 private key locally. Never send the private key."
        ),
        "unique_human": False,
        "certified_100": False,
    }


def verify_and_build_association(
    *,
    challenge: str,
    store: dict[str, dict[str, Any]],
    user_address: str,
    user_public_key_hex: str,
    signature_hex: str,
    role: str = "client",
) -> AssociationRecord:
    pending = store.pop(challenge, None)
    if not pending:
        raise UserNodeAssociationError("challenge_unknown")
    if time.time() > float(pending["expires_at"]):
        raise UserNodeAssociationError("challenge_expired")

    role_n = (role or "client").strip().lower()
    if role_n not in {"client", "operator"}:
        raise UserNodeAssociationError("role_invalid")

    node_id = str(pending["node_id"])
    node_wallet = pending.get("node_wallet_address")
    msg = canonical_message(
        challenge=challenge,
        node_id=node_id,
        node_wallet_address=node_wallet,
        user_address=user_address,
        role=role_n,
    )
    try:
        vk = VerifyKey(bytes.fromhex(user_public_key_hex.strip()))
        vk.verify(msg, bytes.fromhex(signature_hex.strip()))
    except (BadSignatureError, ValueError) as exc:
        raise UserNodeAssociationError("signature_invalid") from exc

    return AssociationRecord(
        user_address=user_address.strip(),
        user_public_key_hex=user_public_key_hex.strip().lower(),
        node_id=node_id,
        node_wallet_address=node_wallet,
        role=role_n,
        challenge_sha256=hashlib.sha256(challenge.encode()).hexdigest(),
        created_ts_ns=time.time_ns(),
    )


class UserNodeAssociationStore:
    """Local per-node association file (R348).

    Persistence mode today: **LOCAL_NODE** — JSON file rewritten on upsert
    (not a blockchain event; not multi-node consensus).
    Target (R348b decision): **REPLICATED_PROTOCOL** association event later.
    """

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

    def upsert(self, rec: AssociationRecord) -> AssociationRecord:
        rows = self._read()
        key = (rec.user_address, rec.node_id, rec.role)
        out: list[dict] = []
        replaced = False
        for row in rows:
            k = (row.get("user_address"), row.get("node_id"), row.get("role"))
            if k == key:
                out.append(rec.to_dict())
                replaced = True
            else:
                out.append(row)
        if not replaced:
            out.append(rec.to_dict())
        self._write(out)
        return rec

    def list_for_user(self, user_address: str) -> list[dict]:
        addr = user_address.strip()
        return [r for r in self._read() if r.get("user_address") == addr]

    def list_for_node(self, node_id: str) -> list[dict]:
        nid = node_id.strip()
        return [r for r in self._read() if r.get("node_id") == nid]
