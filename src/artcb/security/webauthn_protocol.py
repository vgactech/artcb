"""WebAuthn (platform authenticator) for ARTCB wallet enrollment.

Fingerprint and Face ID / OS face unlock go through WebAuthn.
Raw biometric samples never leave the device and are never written on chain.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey

from src.artcb.security.webauthn_cose import (
    ALG_ES256,
    CborError,
    cbor_dumps,
    cbor_loads,
    cose_ec2_p256,
    der_from_raw_rs,
    public_key_from_cose,
)

CHALLENGE_TTL_SEC = 300
FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40

_pending: dict[str, dict[str, Any]] = {}

OFFICIAL_RP_ID = "artcb.me"
LOCAL_RP_IDS = frozenset({"localhost", "127.0.0.1", "testserver", "test"})


def b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64u_decode(text: str) -> bytes:
    raw = (text or "").strip().replace("\n", "")
    pad = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + pad)


def rp_id_for_host(host: str) -> str:
    host = (host or "").split("@")[-1].split(":")[0].lower().strip()
    if host in LOCAL_RP_IDS or host.endswith(".localhost"):
        return host or "localhost"
    if host == OFFICIAL_RP_ID or host.endswith("." + OFFICIAL_RP_ID):
        return OFFICIAL_RP_ID
    if host.endswith(".artcb.space"):
        return host
    return host or OFFICIAL_RP_ID


def expected_origins(host: str, scheme: str) -> set[str]:
    rp = rp_id_for_host(host)
    origins = {f"{scheme}://{host.split(':')[0]}"}
    if ":" in host and not host.startswith("["):
        origins.add(f"{scheme}://{host}")
    if rp == OFFICIAL_RP_ID:
        origins.update(
            {
                "https://artcb.me",
                "https://www.artcb.me",
                "https://n1.artcb.me",
                "https://n2.artcb.me",
                "https://n3.artcb.me",
                "https://n4.artcb.me",
                "https://node.artcb.me",
            }
        )
    if rp in LOCAL_RP_IDS:
        origins.update({f"http://{rp}", f"https://{rp}", "http://testserver", "http://localhost"})
    extra = (os.getenv("ARTCB_WEBAUTHN_EXTRA_ORIGIN") or "").strip()
    if extra:
        origins.add(extra.rstrip("/"))
    return origins


def _put_pending(kind: str, wallet_name: str, modality: str, rp_id: str, challenge: bytes) -> str:
    token = b64u_encode(challenge)
    _pending[token] = {
        "kind": kind,
        "wallet_name": wallet_name,
        "modality": modality,
        "rp_id": rp_id,
        "challenge": token,
        "expires_at": time.time() + CHALLENGE_TTL_SEC,
    }
    return token


def pop_pending(challenge_b64: str, *, kind: str, wallet_name: str) -> dict[str, Any]:
    rec = _pending.get(challenge_b64)
    if not rec:
        raise WebAuthnError("challenge_unknown")
    if time.time() > rec["expires_at"]:
        _pending.pop(challenge_b64, None)
        raise WebAuthnError("challenge_expired")
    if rec.get("kind") != kind:
        raise WebAuthnError("challenge_kind_mismatch")
    if rec.get("wallet_name") != wallet_name:
        raise WebAuthnError("challenge_wallet_mismatch")
    _pending.pop(challenge_b64, None)
    return rec


class WebAuthnError(ValueError):
    """User-facing WebAuthn failure (safe to return as HTTP detail)."""


def registration_options(
    *,
    wallet_name: str,
    user_id: bytes,
    host: str,
    modality: str,
) -> dict[str, Any]:
    rp_id = rp_id_for_host(host)
    challenge = secrets.token_bytes(32)
    token = _put_pending("create", wallet_name, modality, rp_id, challenge)
    user_display = wallet_name
    return {
        "rp": {"id": rp_id, "name": "ARTCB"},
        "user": {
            "id": b64u_encode(user_id),
            "name": wallet_name,
            "displayName": user_display,
        },
        "challenge": token,
        "pubKeyCredParams": [{"type": "public-key", "alg": ALG_ES256}],
        "timeout": CHALLENGE_TTL_SEC * 1000,
        "attestation": "none",
        "excludeCredentials": [],
        "authenticatorSelection": {
            "authenticatorAttachment": "platform",
            "residentKey": "preferred",
            "requireResidentKey": False,
            "userVerification": "required",
        },
        "hints": ["client-device"],
        "extensions": {"credProps": True},
        "modality": modality,
    }


def assertion_options(
    *,
    wallet_name: str,
    host: str,
    allow_credential_ids: list[str],
    modality: str,
) -> dict[str, Any]:
    rp_id = rp_id_for_host(host)
    challenge = secrets.token_bytes(32)
    token = _put_pending("get", wallet_name, modality, rp_id, challenge)
    allow = [{"type": "public-key", "id": cid} for cid in allow_credential_ids]
    return {
        "challenge": token,
        "timeout": CHALLENGE_TTL_SEC * 1000,
        "rpId": rp_id,
        "allowCredentials": allow,
        "userVerification": "required",
        "hints": ["client-device"],
        "modality": modality,
    }


def parse_client_data(client_data_json: bytes) -> dict[str, Any]:
    try:
        data = json.loads(client_data_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebAuthnError("client_data_invalid") from exc
    if not isinstance(data, dict):
        raise WebAuthnError("client_data_invalid")
    return data


def _check_client_data(
    client_data: dict[str, Any],
    *,
    expected_type: str,
    challenge_b64: str,
    origins: set[str],
) -> None:
    if client_data.get("type") != expected_type:
        raise WebAuthnError("client_data_type")
    chal = client_data.get("challenge")
    if not isinstance(chal, str) or chal != challenge_b64:
        raise WebAuthnError("challenge_mismatch")
    origin = str(client_data.get("origin") or "")
    if origin.rstrip("/") not in {o.rstrip("/") for o in origins}:
        raise WebAuthnError("origin_mismatch")


def parse_authenticator_data(auth_data: bytes) -> dict[str, Any]:
    if len(auth_data) < 37:
        raise WebAuthnError("auth_data_truncated")
    rp_id_hash = auth_data[:32]
    flags = auth_data[32]
    sign_count = int.from_bytes(auth_data[33:37], "big")
    rest = auth_data[37:]
    cred_id = b""
    cose = b""
    if flags & FLAG_AT:
        if len(rest) < 18:
            raise WebAuthnError("attested_truncated")
        cred_len = int.from_bytes(rest[16:18], "big")
        cred_id = rest[18 : 18 + cred_len]
        cose = rest[18 + cred_len :]
        if len(cred_id) < 16:
            raise WebAuthnError("credential_id_short")
    return {
        "rp_id_hash": rp_id_hash,
        "flags": flags,
        "sign_count": sign_count,
        "credential_id": cred_id,
        "cose": cose,
        "raw": auth_data,
    }


def _require_uv(flags: int) -> None:
    if not (flags & FLAG_UP):
        raise WebAuthnError("user_presence_required")
    if not (flags & FLAG_UV):
        raise WebAuthnError("user_verification_required")


def verify_attestation(
    *,
    client_data_json: bytes,
    attestation_object: bytes,
    challenge_b64: str,
    rp_id: str,
    origins: set[str],
) -> dict[str, Any]:
    client_data = parse_client_data(client_data_json)
    _check_client_data(
        client_data,
        expected_type="webauthn.create",
        challenge_b64=challenge_b64,
        origins=origins,
    )
    try:
        att, _ = cbor_loads(attestation_object)
    except CborError as exc:
        raise WebAuthnError("attestation_cbor") from exc
    if not isinstance(att, dict):
        raise WebAuthnError("attestation_cbor")
    fmt = att.get("fmt")
    auth_data = att.get("authData")
    if fmt not in {"none", "packed", "tpm", "android-key", "apple"}:
        raise WebAuthnError("attestation_fmt")
    if not isinstance(auth_data, bytes):
        raise WebAuthnError("auth_data_missing")
    parsed = parse_authenticator_data(auth_data)
    if not (parsed["flags"] & FLAG_AT):
        raise WebAuthnError("attested_credential_missing")
    _require_uv(parsed["flags"])
    if parsed["rp_id_hash"] != hashlib.sha256(rp_id.encode("utf-8")).digest():
        raise WebAuthnError("rp_id_hash_mismatch")
    try:
        public_key = public_key_from_cose(parsed["cose"])
    except CborError as exc:
        raise WebAuthnError("cose_key_invalid") from exc
    return {
        "credential_id": b64u_encode(parsed["credential_id"]),
        "cose_b64": b64u_encode(parsed["cose"]),
        "sign_count": parsed["sign_count"],
        "public_key": public_key,
        "rp_id": rp_id,
    }


def verify_assertion(
    *,
    client_data_json: bytes,
    authenticator_data: bytes,
    signature: bytes,
    challenge_b64: str,
    rp_id: str,
    origins: set[str],
    public_key: EllipticCurvePublicKey,
    previous_sign_count: int,
) -> int:
    client_data = parse_client_data(client_data_json)
    _check_client_data(
        client_data,
        expected_type="webauthn.get",
        challenge_b64=challenge_b64,
        origins=origins,
    )
    parsed = parse_authenticator_data(authenticator_data)
    _require_uv(parsed["flags"])
    if parsed["rp_id_hash"] != hashlib.sha256(rp_id.encode("utf-8")).digest():
        raise WebAuthnError("rp_id_hash_mismatch")
    if previous_sign_count > 0 and parsed["sign_count"] > 0 and parsed["sign_count"] <= previous_sign_count:
        raise WebAuthnError("sign_count_replay")
    signed = authenticator_data + hashlib.sha256(client_data_json).digest()
    der = der_from_raw_rs(signature)
    try:
        public_key.verify(der, signed, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise WebAuthnError("assertion_signature") from exc
    return parsed["sign_count"]


def software_create_credential(
    *,
    options: dict[str, Any],
    origin: str,
    private_key: ec.EllipticCurvePrivateKey | None = None,
) -> tuple[ec.EllipticCurvePrivateKey, dict[str, Any]]:
    """Deterministic platform-authenticator stand-in for tests. Not a browser."""
    key = private_key or ec.generate_private_key(ec.SECP256R1())
    challenge = options["challenge"]
    rp_id = options["rp"]["id"]
    client_data = json.dumps(
        {
            "type": "webauthn.create",
            "challenge": challenge,
            "origin": origin,
            "crossOrigin": False,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    cred_id = secrets.token_bytes(32)
    cose = cose_ec2_p256(key.public_key())
    flags = FLAG_UP | FLAG_UV | FLAG_AT
    auth_data = (
        hashlib.sha256(rp_id.encode("utf-8")).digest()
        + bytes([flags])
        + (0).to_bytes(4, "big")
        + (b"\x00" * 16)
        + len(cred_id).to_bytes(2, "big")
        + cred_id
        + cose
    )
    att = cbor_dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
    credential = {
        "id": b64u_encode(cred_id),
        "rawId": b64u_encode(cred_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": b64u_encode(client_data),
            "attestationObject": b64u_encode(att),
        },
        "authenticatorAttachment": "platform",
    }
    return key, credential


def software_assert_credential(
    *,
    options: dict[str, Any],
    origin: str,
    private_key: ec.EllipticCurvePrivateKey,
    credential_id: str,
    sign_count: int = 1,
) -> dict[str, Any]:
    challenge = options["challenge"]
    rp_id = options["rpId"]
    client_data = json.dumps(
        {
            "type": "webauthn.get",
            "challenge": challenge,
            "origin": origin,
            "crossOrigin": False,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    flags = FLAG_UP | FLAG_UV
    auth_data = (
        hashlib.sha256(rp_id.encode("utf-8")).digest()
        + bytes([flags])
        + sign_count.to_bytes(4, "big")
    )
    signed = auth_data + hashlib.sha256(client_data).digest()
    signature = private_key.sign(signed, ec.ECDSA(hashes.SHA256()))
    return {
        "id": credential_id,
        "rawId": credential_id,
        "type": "public-key",
        "response": {
            "clientDataJSON": b64u_encode(client_data),
            "authenticatorData": b64u_encode(auth_data),
            "signature": b64u_encode(signature),
        },
        "authenticatorAttachment": "platform",
    }
