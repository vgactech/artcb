"""Canonical NodeID ↔ public-key binding for the four official replicas.

The public key attached to a PBFT / tip-attest message is informational.
Authority is this registry (or a test override), never the sender-supplied key.

Production (on_official_compute or ARTCB_REQUIRE_REPLICA_BINDING=1):
    replica_id → expected Ed25519 + PQC → verify signature with THOSE keys.

Pytest default: registry inactive so existing local-key cluster tests still
sign. Tests that prove binding call install_test_replica_registry().
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from src.artcb.node_registry import (
    OFFICIAL_COMPUTE_NODE_IDS,
    OFFICIAL_NODE_MARKER,
    official_replica_id,
    on_official_compute,
)

REGISTRY_REL = Path(__file__).resolve().parent / "official_replica_keys.json"
BINDING_REASONS = frozenset(
    {
        "invalid_replica_key_binding",
        "invalid_replica_pqc_binding",
        "unregistered_replica_key",
        "replica_key_revoked",
        "replica_key_expired",
        "replica_key_not_yet_valid",
        "replica_pqc_downgrade",
        "unknown_replica_id",
    }
)
OVERLAY_DEFAULT = Path("/etc/artcb/replica_overlay.json")
OVERLAY_VERSION_DEFAULT = Path("/var/lib/artcb/node/overlay_seen_version")

_lock = threading.Lock()
_test_override: dict[str, "ReplicaKeyBinding"] | None = None
_official_cache: dict[str, "ReplicaKeyBinding"] | None = None
_overlay_cache: dict[str, "ReplicaKeyBinding"] = {}
_overlay_mtime: float | None = None
_overlay_meta: dict[str, Any] = {"present": False}
_overlay_seen_mem: int = 0


@dataclass(frozen=True)
class ReplicaKeyBinding:
    node_id: str
    ed25519_b64: str
    pqc_b64: str = ""
    activation_epoch: int = 0
    not_after_epoch: int = 0
    revoked: bool = False
    require_pqc: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "ed25519_b64": self.ed25519_b64,
            "pqc_b64": self.pqc_b64,
            "activation_epoch": self.activation_epoch,
            "not_after_epoch": self.not_after_epoch,
            "revoked": self.revoked,
            "require_pqc": self.require_pqc,
        }


def _norm_b64(raw: str) -> str:
    return "".join(str(raw or "").split())


def binding_enforced() -> bool:
    env = (os.getenv("ARTCB_REQUIRE_REPLICA_BINDING") or "").strip().lower()
    if env in {"1", "true", "yes", "on", "live", "official"}:
        return True
    if env in {"0", "false", "no", "off"}:
        return False
    mode = (os.getenv("ARTCB_REPLICA_REGISTRY") or "").strip().lower()
    if mode in {"live", "official", "1"}:
        return True
    # Official VMs write /etc/artcb/official_node. Do not key enforcement on
    # the public IPv4: AWS often sees only the VPC address, which is not identity.
    if OFFICIAL_NODE_MARKER.is_file():
        try:
            raw = OFFICIAL_NODE_MARKER.read_text(encoding="utf-8").strip().splitlines()
            marker = (raw[0] if raw else "").strip()
        except OSError:
            marker = ""
        if marker in OFFICIAL_COMPUTE_NODE_IDS:
            return True
    return bool(on_official_compute())


def _parse_replicas(payload: dict[str, Any]) -> dict[str, ReplicaKeyBinding]:
    rows = payload.get("replicas") if isinstance(payload.get("replicas"), dict) else {}
    out: dict[str, ReplicaKeyBinding] = {}
    for nid, raw in rows.items():
        if nid not in OFFICIAL_COMPUTE_NODE_IDS or not isinstance(raw, dict):
            continue
        ed = _norm_b64(str(raw.get("ed25519_b64") or ""))
        if not ed:
            continue
        out[str(nid)] = ReplicaKeyBinding(
            node_id=str(nid),
            ed25519_b64=ed,
            pqc_b64=_norm_b64(str(raw.get("pqc_b64") or "")),
            activation_epoch=int(raw.get("activation_epoch") or 0),
            not_after_epoch=int(raw.get("not_after_epoch") or 0),
            revoked=bool(raw.get("revoked")),
            require_pqc=bool(raw.get("require_pqc")),
        )
    return out


def load_official_registry(*, force: bool = False) -> dict[str, ReplicaKeyBinding]:
    global _official_cache
    with _lock:
        if _official_cache is not None and not force:
            return dict(_official_cache)
        extra = (os.getenv("ARTCB_REPLICA_REGISTRY_PATH") or "").strip()
        path = Path(extra) if extra else REGISTRY_REL
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        parsed = _parse_replicas(payload if isinstance(payload, dict) else {})
        _official_cache = parsed
        return dict(parsed)


def install_test_replica_registry(mapping: dict[str, ReplicaKeyBinding | dict[str, Any]]) -> None:
    """Replace the active registry for this process (tests / adversarial fixtures)."""
    global _test_override
    parsed: dict[str, ReplicaKeyBinding] = {}
    for nid, raw in mapping.items():
        if isinstance(raw, ReplicaKeyBinding):
            parsed[nid] = raw
            continue
        parsed[nid] = ReplicaKeyBinding(
            node_id=str(nid),
            ed25519_b64=_norm_b64(str(raw.get("ed25519_b64") or "")),
            pqc_b64=_norm_b64(str(raw.get("pqc_b64") or "")),
            activation_epoch=int(raw.get("activation_epoch") or 0),
            not_after_epoch=int(raw.get("not_after_epoch") or 0),
            revoked=bool(raw.get("revoked")),
            require_pqc=bool(raw.get("require_pqc")),
        )
    with _lock:
        _test_override = parsed


def clear_test_replica_registry() -> None:
    global _test_override
    with _lock:
        _test_override = None


@contextmanager
def override_replica_registry(mapping: dict[str, ReplicaKeyBinding | dict[str, Any]]) -> Iterator[None]:
    install_test_replica_registry(mapping)
    try:
        yield
    finally:
        clear_test_replica_registry()


def register_chain_replicas(chains: dict[str, Any]) -> dict[str, ReplicaKeyBinding]:
    """Install generated ChainManager keys as the test registry (NodeID → that chain)."""
    from src.artcb.consensus.tip_attest import producer_key_b64

    mapping: dict[str, ReplicaKeyBinding] = {}
    for nid, chain in chains.items():
        ed, pqc = producer_key_b64(chain)
        mapping[str(nid)] = ReplicaKeyBinding(node_id=str(nid), ed25519_b64=ed, pqc_b64=pqc)
    install_test_replica_registry(mapping)
    return mapping


def overlay_file() -> Path:
    extra = (os.getenv("ARTCB_REPLICA_OVERLAY") or "").strip()
    return Path(extra) if extra else OVERLAY_DEFAULT


def overlay_version_file() -> Path:
    extra = (os.getenv("ARTCB_REPLICA_OVERLAY_VERSION") or "").strip()
    return Path(extra) if extra else OVERLAY_VERSION_DEFAULT


def _seen_overlay_version() -> int:
    global _overlay_seen_mem
    path = overlay_version_file()
    disk = 0
    try:
        disk = int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        disk = 0
    return max(int(_overlay_seen_mem or 0), disk)


def _remember_overlay_version(version: int) -> None:
    global _overlay_seen_mem
    version = int(version)
    if version > int(_overlay_seen_mem or 0):
        _overlay_seen_mem = version
    path = overlay_version_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(version) + "\n", encoding="utf-8")
    except OSError:
        pass


def load_overlay(*, force: bool = False) -> tuple[dict[str, ReplicaKeyBinding], dict[str, Any]]:
    """Live overlay merged into the official registry. Rollback of version is rejected."""
    global _overlay_cache, _overlay_mtime, _overlay_meta
    path = overlay_file()
    try:
        mtime = path.stat().st_mtime if path.is_file() else None
    except OSError:
        mtime = None
    official_snapshot = load_official_registry()
    with _lock:
        if not force and mtime == _overlay_mtime and _overlay_meta:
            return dict(_overlay_cache), dict(_overlay_meta)
        if mtime is None:
            _overlay_cache = {}
            _overlay_mtime = None
            _overlay_meta = {"present": False, "applied": False, "reason": "absent"}
            return {}, dict(_overlay_meta)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _overlay_cache = {}
            _overlay_mtime = mtime
            _overlay_meta = {"present": True, "applied": False, "reason": "invalid_json", "error": type(exc).__name__}
            return {}, dict(_overlay_meta)
        if not isinstance(payload, dict):
            _overlay_cache = {}
            _overlay_mtime = mtime
            _overlay_meta = {"present": True, "applied": False, "reason": "invalid_payload"}
            return {}, dict(_overlay_meta)
        version = int(payload.get("version") or 0)
        seen = _seen_overlay_version()
        if version and seen and version < seen:
            _overlay_cache = {}
            _overlay_mtime = mtime
            _overlay_meta = {
                "present": True,
                "applied": False,
                "reason": "overlay_rollback_rejected",
                "version": version,
                "seen": seen,
            }
            return {}, dict(_overlay_meta)
        parsed = _parse_replicas(payload if isinstance(payload.get("replicas"), dict) else payload)
        rows = payload.get("replicas") if isinstance(payload.get("replicas"), dict) else {}
        official = dict(official_snapshot)
        merged: dict[str, ReplicaKeyBinding] = {}
        for nid, raw in rows.items():
            if nid not in OFFICIAL_COMPUTE_NODE_IDS or not isinstance(raw, dict):
                continue
            base = official.get(nid)
            if nid in parsed:
                merged[nid] = parsed[nid]
                continue
            if base is None:
                continue
            merged[nid] = ReplicaKeyBinding(
                node_id=nid,
                ed25519_b64=base.ed25519_b64,
                pqc_b64=base.pqc_b64,
                activation_epoch=int(raw.get("activation_epoch") or base.activation_epoch),
                not_after_epoch=int(raw.get("not_after_epoch") or base.not_after_epoch),
                revoked=bool(raw["revoked"]) if "revoked" in raw else base.revoked,
                require_pqc=bool(raw["require_pqc"]) if "require_pqc" in raw else base.require_pqc,
            )
        if version:
            _remember_overlay_version(version)
        _overlay_cache = merged
        _overlay_mtime = mtime
        _overlay_meta = {"present": True, "applied": True, "reason": "ok", "version": version, "ids": list(merged)}
        return dict(merged), dict(_overlay_meta)


def active_registry() -> dict[str, ReplicaKeyBinding]:
    with _lock:
        if _test_override is not None:
            return dict(_test_override)
    if binding_enforced():
        official = load_official_registry()
        overlay, _meta = load_overlay()
        if overlay:
            official.update(overlay)
        return official
    overlay, _meta = load_overlay()
    if overlay:
        official = load_official_registry()
        official.update(overlay)
        return official
    return {}


def expected_binding(node_id: str) -> ReplicaKeyBinding | None:
    return active_registry().get(str(node_id or ""))


def owner_of_ed25519(ed25519_b64: str) -> str | None:
    needle = _norm_b64(ed25519_b64)
    if not needle:
        return None
    for nid, row in active_registry().items():
        if _norm_b64(row.ed25519_b64) == needle:
            return nid
    return None


def verify_replica_key_binding(
    replica_id: str,
    producer_ed25519_b64: str,
    producer_pqc_b64: str = "",
) -> tuple[bool, str]:
    """Return (ok, reason). reason is invalid_replica_key_binding on A3/A7."""
    claimed = str(replica_id or "").strip()
    ed = _norm_b64(producer_ed25519_b64)
    pqc = _norm_b64(producer_pqc_b64)
    owner = owner_of_ed25519(ed)
    if owner and owner != claimed:
        return False, "invalid_replica_key_binding"
    registry = active_registry()
    if claimed in OFFICIAL_COMPUTE_NODE_IDS:
        expected = registry.get(claimed)
        if expected is None:
            if binding_enforced():
                return False, "unregistered_replica_key"
            return True, "registry_inactive"
        if expected.revoked:
            return False, "replica_key_revoked"
        import time

        now = int(time.time())
        if expected.activation_epoch and now < int(expected.activation_epoch):
            return False, "replica_key_not_yet_valid"
        if expected.not_after_epoch and now > int(expected.not_after_epoch):
            return False, "replica_key_expired"
        if _norm_b64(expected.ed25519_b64) != ed:
            return False, "invalid_replica_key_binding"
        if expected.require_pqc and not pqc:
            return False, "replica_pqc_downgrade"
        if expected.pqc_b64 and pqc and _norm_b64(expected.pqc_b64) != pqc:
            return False, "invalid_replica_pqc_binding"
        return True, "ok"
    if claimed and registry and binding_enforced() and owner is None and ed:
        # Official compute: a free-form node_id must not carry a registered key
        # (already handled) and must not impersonate an official id.
        return True, "non_official_id"
    return True, "ok"


def verification_keys(replica_id: str, producer_ed25519_b64: str, producer_pqc_b64: str = "") -> tuple[str, str]:
    """Keys that MUST be used for signature verify — expected, not sender-supplied."""
    expected = expected_binding(replica_id)
    if expected is not None and not expected.revoked:
        return expected.ed25519_b64, expected.pqc_b64 or _norm_b64(producer_pqc_b64)
    return _norm_b64(producer_ed25519_b64), _norm_b64(producer_pqc_b64)


def verify_bound_signature(
    *,
    replica_id: str,
    message: str,
    signature: str,
    producer_ed25519_b64: str,
    producer_pqc_b64: str = "",
) -> tuple[bool, str]:
    ok, reason = verify_replica_key_binding(replica_id, producer_ed25519_b64, producer_pqc_b64)
    if not ok:
        return False, reason
    from src.artcb.consensus.tip_attest import verify_chain_signature

    ed, pqc = verification_keys(replica_id, producer_ed25519_b64, producer_pqc_b64)
    if not verify_chain_signature(
        message=message,
        signature=signature,
        producer_ed25519_b64=ed,
        producer_pqc_b64=pqc,
    ):
        return False, "invalid_signature"
    return True, "ok"


def local_ed25519_b64() -> str:
    """Public Ed25519 of the local chain.key — no ChainManager / liboqs."""
    try:
        from src.artcb.config import load_settings
        from src.artcb.wallet.encryption import decrypt_private_key, is_encrypted_key_blob
        from nacl.encoding import Base64Encoder
        from nacl.signing import SigningKey
    except Exception:
        return ""
    try:
        raw = (load_settings().data_dir / "chain.key").read_bytes()
        seed = decrypt_private_key(raw) if is_encrypted_key_blob(raw) else raw[:32]
        return SigningKey(seed).verify_key.encode(encoder=Base64Encoder).decode("ascii")
    except Exception:
        return ""


def official_node_file_id() -> str:
    try:
        raw = OFFICIAL_NODE_MARKER.read_text(encoding="utf-8").strip().splitlines()
        return (raw[0] if raw else "").strip()
    except OSError:
        return ""


def local_identity_status() -> dict[str, Any]:
    marker = official_replica_id()
    file_id = official_node_file_id()
    env_id = (os.getenv("ARTCB_NODE_ID") or "").strip()
    ed = local_ed25519_b64()
    owner = owner_of_ed25519(ed) if ed else None
    coherent = bool(owner and marker and owner == marker)
    file_mismatch = bool(owner and file_id and file_id != owner)
    return {
        "official_node_marker": marker,
        "official_node_file": file_id,
        "env_node_id": env_id,
        "env_shadows_file": bool(env_id in OFFICIAL_COMPUTE_NODE_IDS and file_id and env_id != file_id),
        "local_ed25519_b64": ed,
        "key_owner": owner,
        "coherent": coherent,
        "mismatch": bool(owner and marker and owner != marker) or file_mismatch,
        "file_mismatch": file_mismatch,
        "note": "official_node / ARTCB_NODE_ID label a machine. The registered key is the consensus identity.",
    }


def official_consensus_node_id() -> str:
    """Speak as the key owner when official_node disagrees. File is not the proof."""
    status = local_identity_status()
    owner = str(status.get("key_owner") or "")
    marker = str(status.get("official_node_marker") or official_replica_id())
    if owner in OFFICIAL_COMPUTE_NODE_IDS:
        return owner
    if marker in OFFICIAL_COMPUTE_NODE_IDS:
        return marker
    return marker or owner


def public_registry_view() -> dict[str, Any]:
    official = load_official_registry()
    active = active_registry()
    _overlay, overlay_meta = load_overlay()
    local = local_identity_status()
    return {
        "protocol": "278-replica-identity-binding",
        "binding_enforced": binding_enforced(),
        "test_override": _test_override is not None,
        "official_replica_ids": list(OFFICIAL_COMPUTE_NODE_IDS),
        "local_replica_id": official_consensus_node_id(),
        "local_identity": local,
        "overlay": overlay_meta,
        "replicas": {nid: row.to_public_dict() for nid, row in (active or official).items()},
        "note": (
            "IP / hostname / ARTCB_NODE_ID / official_node label a machine. "
            "Only the registered public key proves the consensus role. "
            "A live overlay can revoke/expire/rotate without rewriting git."
        ),
    }
