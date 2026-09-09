"""R278 — overlay revocation/expiry/rotation, official_node is not the proof."""

from __future__ import annotations

import json
import time
from pathlib import Path

from src.artcb.consensus.platform_attest import classify
from src.artcb.consensus.replica_identity import (
    ReplicaKeyBinding,
    load_overlay,
    official_consensus_node_id,
    override_replica_registry,
    verify_replica_key_binding,
)


def test_a4_revoked_and_a5_expired() -> None:
    ed = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    with override_replica_registry(
        {
            "ovh-node-2": ReplicaKeyBinding(
                node_id="ovh-node-2",
                ed25519_b64=ed,
                revoked=True,
            )
        }
    ):
        ok, reason = verify_replica_key_binding("ovh-node-2", ed)
        assert ok is False
        assert reason == "replica_key_revoked"
    with override_replica_registry(
        {
            "ovh-node-2": ReplicaKeyBinding(
                node_id="ovh-node-2",
                ed25519_b64=ed,
                not_after_epoch=1,
            )
        }
    ):
        ok, reason = verify_replica_key_binding("ovh-node-2", ed)
        assert ok is False
        assert reason == "replica_key_expired"
    with override_replica_registry(
        {
            "ovh-node-2": ReplicaKeyBinding(
                node_id="ovh-node-2",
                ed25519_b64=ed,
                activation_epoch=int(time.time()) + 10_000,
            )
        }
    ):
        ok, reason = verify_replica_key_binding("ovh-node-2", ed)
        assert ok is False
        assert reason == "replica_key_not_yet_valid"


def test_a6_pqc_downgrade() -> None:
    ed = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    with override_replica_registry(
        {
            "ovh-node-2": ReplicaKeyBinding(
                node_id="ovh-node-2",
                ed25519_b64=ed,
                pqc_b64="cHFj",
                require_pqc=True,
            )
        }
    ):
        ok, reason = verify_replica_key_binding("ovh-node-2", ed, "")
        assert ok is False
        assert reason == "replica_pqc_downgrade"


def test_a8_rotation_old_key_rejected() -> None:
    old = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    new = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
    with override_replica_registry(
        {"ovh-node-2": ReplicaKeyBinding(node_id="ovh-node-2", ed25519_b64=new)}
    ):
        ok, reason = verify_replica_key_binding("ovh-node-2", old)
        assert ok is False
        assert reason == "invalid_replica_key_binding"
        ok2, reason2 = verify_replica_key_binding("ovh-node-2", new)
        assert ok2 is True


def test_overlay_revoke_and_rollback(tmp_path: Path, monkeypatch) -> None:
    from src.artcb.consensus import replica_identity as rid

    overlay = tmp_path / "overlay.json"
    seen = tmp_path / "seen"
    monkeypatch.setenv("ARTCB_REPLICA_OVERLAY", str(overlay))
    monkeypatch.setenv("ARTCB_REPLICA_OVERLAY_VERSION", str(seen))
    monkeypatch.setattr(rid, "_overlay_mtime", None)
    monkeypatch.setattr(rid, "_overlay_cache", {})
    monkeypatch.setattr(rid, "_overlay_meta", {"present": False})
    overlay.write_text(
        json.dumps({"version": 11, "replicas": {"ovh-node-2": {"revoked": True}}}),
        encoding="utf-8",
    )
    merged, meta = load_overlay(force=True)
    assert meta.get("applied") is True
    assert merged["ovh-node-2"].revoked is True
    overlay.write_text(
        json.dumps({"version": 10, "replicas": {"ovh-node-2": {"revoked": False}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(rid, "_overlay_mtime", None)
    merged2, meta2 = load_overlay(force=True)
    assert meta2.get("reason") == "overlay_rollback_rejected"
    assert merged2 == {}


def test_platform_class_does_not_recast_absent_tpm() -> None:
    klass = classify(
        tpm={"present": False},
        virt={"is_vm": True},
        aws={"document_ok": True},
        ovh={"document_ok": False},
    )
    assert klass == "cloud_instance_identity"
    klass2 = classify(
        tpm={"present": False},
        virt={"is_vm": True},
        aws={"document_ok": False},
        ovh={"document_ok": False},
    )
    assert klass2 == "vm_unattested"
    klass3 = classify(
        tpm={"present": True},
        virt={"is_vm": True},
        aws={"document_ok": True},
        ovh={"document_ok": False},
    )
    assert klass3 == "vtpm"
    klass4 = classify(
        tpm={"present": True},
        virt={"is_vm": False},
        aws={"document_ok": False},
        ovh={"document_ok": False},
    )
    assert klass4 == "tpm_hardware"


def test_official_consensus_prefers_key_owner(monkeypatch) -> None:
    from src.artcb.consensus import replica_identity as rid

    monkeypatch.setattr(rid, "official_replica_id", lambda: "ovh-node-2")
    monkeypatch.setattr(
        rid,
        "local_identity_status",
        lambda: {
            "official_node_marker": "ovh-node-2",
            "key_owner": "ovh-node-1",
            "coherent": False,
            "mismatch": True,
        },
    )
    assert official_consensus_node_id() == "ovh-node-1"
