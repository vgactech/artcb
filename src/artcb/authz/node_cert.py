"""Founder-signed node authorization certificates (rapport 236).

authorized_nodes[] is a declaration.

A certificate is:

    domain_id + node_id + node_public_key + role + founder_address
        + genesis_hash + validity
        + founder Ed25519 signature

The node then proves possession of node_public_key. Without both, the
node is not a consensus participant — even if its name is on the list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from src.artcb.authz.domains import canonical_hash
from src.artcb.authz.node_roles import (
    ROLE_HOST_ONLY,
    capabilities_for,
    can_role,
)

KIND = "artcb_node_authorization_v1"


class NodeCertError(ValueError):
    """Certificate missing, expired, or signature invalid."""


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def unsigned_payload(
    *,
    domain_id: str,
    node_id: str,
    node_public_key_hex: str,
    role: str,
    founder_address: str,
    genesis_hash: str,
    issued_at: str | None = None,
    valid_until: str | None = None,
) -> dict[str, Any]:
    role = (role or ROLE_HOST_ONLY).upper()
    caps = sorted(capabilities_for(role))
    return {
        "kind": KIND,
        "domain_id": domain_id,
        "node_id": node_id,
        "node_public_key_hex": node_public_key_hex.lower(),
        "role": role,
        "capabilities": caps,
        "founder_address": founder_address,
        "genesis_hash": genesis_hash,
        "issued_at": issued_at or _now_iso(),
        "valid_until": valid_until,
    }


def issue_node_certificate(
    founder_signing_key: SigningKey,
    *,
    domain_id: str,
    node_id: str,
    node_public_key_hex: str,
    role: str,
    founder_address: str,
    genesis_hash: str,
    valid_until: str | None = None,
) -> dict[str, Any]:
    payload = unsigned_payload(
        domain_id=domain_id,
        node_id=node_id,
        node_public_key_hex=node_public_key_hex,
        role=role,
        founder_address=founder_address,
        genesis_hash=genesis_hash,
        valid_until=valid_until,
    )
    digest = canonical_hash(payload).encode("utf-8")
    signature = founder_signing_key.sign(digest).signature.hex()
    return {
        **payload,
        "payload_hash": canonical_hash(payload),
        "founder_signature": signature,
        "founder_public_key_hex": founder_signing_key.verify_key.encode().hex(),
        "list_entry_is_not_proof": True,
    }


def verify_node_certificate(
    cert: dict[str, Any],
    *,
    expected_domain_id: str | None = None,
    expected_genesis_hash: str | None = None,
    expected_founder_address: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    if not isinstance(cert, dict) or cert.get("kind") != KIND:
        raise NodeCertError("invalid_cert_kind")
    payload = unsigned_payload(
        domain_id=str(cert.get("domain_id") or ""),
        node_id=str(cert.get("node_id") or ""),
        node_public_key_hex=str(cert.get("node_public_key_hex") or ""),
        role=str(cert.get("role") or ROLE_HOST_ONLY),
        founder_address=str(cert.get("founder_address") or ""),
        genesis_hash=str(cert.get("genesis_hash") or ""),
        issued_at=str(cert.get("issued_at") or ""),
        valid_until=cert.get("valid_until"),
    )
    recomputed = canonical_hash(payload)
    if cert.get("payload_hash") and cert["payload_hash"] != recomputed:
        raise NodeCertError("payload_hash_mismatch")
    pub = str(cert.get("founder_public_key_hex") or "")
    sig = str(cert.get("founder_signature") or "")
    if not pub or not sig:
        raise NodeCertError("missing_founder_signature")
    try:
        VerifyKey(bytes.fromhex(pub)).verify(recomputed.encode("utf-8"), bytes.fromhex(sig))
    except (BadSignatureError, ValueError) as exc:
        raise NodeCertError("founder_signature_invalid") from exc
    if expected_domain_id and payload["domain_id"] != expected_domain_id:
        raise NodeCertError("domain_mismatch")
    if expected_genesis_hash and payload["genesis_hash"] != expected_genesis_hash:
        raise NodeCertError("genesis_hash_mismatch")
    if expected_founder_address and payload["founder_address"] != expected_founder_address:
        raise NodeCertError("founder_mismatch")
    until = payload.get("valid_until")
    if until:
        stamp = now or _now_iso()
        if stamp > str(until):
            raise NodeCertError("cert_expired")
    return payload


def node_possession_proof(node_signing_key: SigningKey, cert: dict[str, Any]) -> str:
    digest = str(cert.get("payload_hash") or "").encode("utf-8")
    if not digest:
        raise NodeCertError("missing_payload_hash")
    return node_signing_key.sign(digest).signature.hex()


def verify_node_possession(cert: dict[str, Any], proof_hex: str) -> None:
    pub = str(cert.get("node_public_key_hex") or "")
    digest = str(cert.get("payload_hash") or "").encode("utf-8")
    if not pub or not digest:
        raise NodeCertError("incomplete_cert")
    try:
        VerifyKey(bytes.fromhex(pub)).verify(digest, bytes.fromhex(proof_hex))
    except (BadSignatureError, ValueError) as exc:
        raise NodeCertError("node_key_mismatch") from exc


def cert_allows(cert: dict[str, Any], capability: str) -> bool:
    try:
        payload = verify_node_certificate(cert)
    except NodeCertError:
        return False
    return can_role(str(payload.get("role") or ""), capability)


@dataclass(frozen=True)
class NodeAuthorization:
    """Resolved view: list declaration vs cryptographic certificate."""

    node_id: str
    listed: bool
    declared_role: str
    certified: bool
    certified_role: str
    can_host: bool
    can_replicate: bool
    can_produce: bool
    can_validate: bool
    can_change_governance: bool
    body_present: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "listed_on_authorized_nodes": self.listed,
            "declared_role": self.declared_role,
            "certified": self.certified,
            "certified_role": self.certified_role,
            "can_host": self.can_host,
            "can_replicate": self.can_replicate,
            "can_produce": self.can_produce,
            "can_validate": self.can_validate,
            "can_change_governance": self.can_change_governance,
            "body_present": self.body_present,
            "cest_a_dire": (
                "Certificat + possession de clé."
                if self.certified
                else "Nom dans authorized_nodes seulement — déclaration, pas une preuve."
            ),
        }
