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
        "unknown_replica_id",
    }
)

_lock = threading.Lock()
_test_override: dict[str, "ReplicaKeyBinding"] | None = None
_official_cache: dict[str, "ReplicaKeyBinding"] | None = None


@dataclass(frozen=True)
class ReplicaKeyBinding:
    node_id: str
    ed25519_b64: str
    pqc_b64: str = ""
    activation_epoch: int = 0
    revoked: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "ed25519_b64": self.ed25519_b64,
            "pqc_b64": self.pqc_b64,
            "activation_epoch": self.activation_epoch,
            "revoked": self.revoked,
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
            revoked=bool(raw.get("revoked")),
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
            revoked=bool(raw.get("revoked")),
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


def active_registry() -> dict[str, ReplicaKeyBinding]:
    with _lock:
        if _test_override is not None:
            return dict(_test_override)
    if binding_enforced():
        return load_official_registry()
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
        if _norm_b64(expected.ed25519_b64) != ed:
            return False, "invalid_replica_key_binding"
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


def official_consensus_node_id() -> str:
    """Consensus identity is the official replica id, not IP / wallet / env alone."""
    rid = official_replica_id()
    if rid in OFFICIAL_COMPUTE_NODE_IDS:
        return rid
    return rid


def public_registry_view() -> dict[str, Any]:
    official = load_official_registry()
    active = active_registry()
    return {
        "protocol": "273-replica-identity-binding",
        "binding_enforced": binding_enforced(),
        "test_override": _test_override is not None,
        "official_replica_ids": list(OFFICIAL_COMPUTE_NODE_IDS),
        "local_replica_id": official_consensus_node_id(),
        "replicas": {nid: row.to_public_dict() for nid, row in (active or official).items()},
        "note": (
            "IP / hostname / ARTCB_NODE_ID label a machine. "
            "Only the registered public key proves the consensus role."
        ),
    }
