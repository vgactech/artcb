"""Signed P2P capability card bound to KEM identity (D-034 / DV-01 C).

Unsigned advertisements must not be trusted as ML-DSA capability history.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nacl import signing

logger = logging.getLogger("artcb.p2p.handshake")


def kem_fingerprint(kem_public_key_hex: str) -> str:
    material = (kem_public_key_hex or "").strip().lower().encode("ascii")
    return hashlib.sha256(material).hexdigest()


def canonical_card(payload: dict[str, Any]) -> bytes:
    body = {
        "node_id": payload.get("node_id") or "",
        "kem_fingerprint": payload.get("kem_fingerprint") or "",
        "crypto_suite": payload.get("crypto_suite") or "",
        "protocol_version": payload.get("protocol_version") or "",
        "network_id": payload.get("network_id") or "",
        "genesis_hash": payload.get("genesis_hash") or "",
        "seq": int(payload.get("seq") or 0),
        "ts": payload.get("ts") or "",
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


class HandshakeKey:
    def __init__(self, signing_key: signing.SigningKey) -> None:
        self.signing_key = signing_key

    @property
    def public_hex(self) -> str:
        return self.signing_key.verify_key.encode().hex()

    def sign(self, message: bytes) -> str:
        return "ed25519:" + self.signing_key.sign(message).signature.hex()


def load_or_create_handshake_key(data_dir: Path) -> HandshakeKey:
    path = Path(data_dir) / "p2p" / "handshake_ed25519.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        raw = bytes.fromhex(path.read_text(encoding="utf-8").strip())
        return HandshakeKey(signing.SigningKey(raw))
    key = signing.SigningKey.generate()
    path.write_text(key.encode().hex() + "\n", encoding="utf-8")
    path.chmod(0o600)
    return HandshakeKey(key)


def verify_ed25519(message: bytes, signature_value: str, public_hex: str) -> bool:
    sig_hex = signature_value
    if sig_hex.startswith("ed25519:"):
        sig_hex = sig_hex[len("ed25519:") :]
    try:
        vk = signing.VerifyKey(bytes.fromhex(public_hex))
        vk.verify(message, bytes.fromhex(sig_hex))
        return True
    except Exception:
        return False


def build_signed_card(
    *,
    node_id: str,
    kem_public_key_hex: str,
    crypto_suite: str,
    protocol_version: str,
    network_id: str,
    genesis_hash: str,
    handshake: HandshakeKey,
    seq: int = 1,
) -> dict[str, Any]:
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "node_id": node_id,
        "kem_fingerprint": kem_fingerprint(kem_public_key_hex),
        "crypto_suite": crypto_suite,
        "protocol_version": protocol_version,
        "network_id": network_id,
        "genesis_hash": genesis_hash,
        "seq": seq,
        "ts": ts,
        "handshake_public_hex": handshake.public_hex,
    }
    payload["signature"] = handshake.sign(canonical_card(payload))
    payload["signed"] = True
    return payload


def verify_signed_card(card: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(card, dict) or not card:
        return False, "unsigned"
    pub = str(card.get("handshake_public_hex") or "")
    sig = str(card.get("signature") or "")
    if not pub or not sig:
        return False, "unsigned"
    if not verify_ed25519(canonical_card(card), sig, pub):
        return False, "bad_signature"
    return True, "signed_ok"


class CapabilityHistory:
    """Persisted crypto capability history keyed by KEM fingerprint."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "p2p" / "capability_history.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write({"identities": {}})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.path.chmod(0o600)

    def previous_suite(self, fingerprint: str) -> str | None:
        rec = (self._read().get("identities") or {}).get(fingerprint) or {}
        return rec.get("last_trusted_suite") or None

    def remember_trusted(self, fingerprint: str, *, suite: str, node_id: str, signed: bool) -> None:
        if not signed:
            return
        raw = self._read()
        identities = raw.setdefault("identities", {})
        identities[fingerprint] = {
            "node_id": node_id,
            "last_trusted_suite": suite,
            "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "signed": True,
        }
        self._write(raw)
