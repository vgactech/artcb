"""R331 — audit_sign forge: local key + wrong NodeID → binding reject."""

from __future__ import annotations

from pathlib import Path

# Use src.* so override_replica_registry hits the same module as verify_signed_detailed.
from src.artcb.chain.manager import ChainManager
from src.artcb.consensus.pbft_finality import (
    audit_sign_prepare,
    prepare_message,
    verify_prepare,
    verify_signed_detailed,
)
from src.artcb.consensus.replica_identity import (
    ReplicaKeyBinding,
    override_replica_registry,
    verify_replica_key_binding,
)
from src.artcb.consensus.tip_attest import producer_key_b64


def test_audit_sign_wrong_nodeid_fails_binding(tmp_path: Path) -> None:
    chain = ChainManager(tmp_path / "blocks.jsonl", key_path=tmp_path / "chain.key", enable_security=False)
    ed, pqc = producer_key_b64(chain)
    with override_replica_registry(
        {
            "ovh-node-1": ReplicaKeyBinding(node_id="ovh-node-1", ed25519_b64=ed, pqc_b64=pqc or ""),
            "ovh-node-2": ReplicaKeyBinding(
                node_id="ovh-node-2",
                ed25519_b64="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
                pqc_b64="",
            ),
        }
    ):
        ok_bind, _ = verify_replica_key_binding("ovh-node-1", ed, pqc or "")
        assert ok_bind is True
        forged = audit_sign_prepare(chain, claimed_replica_id="ovh-node-2", view=15, seq=500)
        assert forged["replica_id"] == "ovh-node-2"
        assert forged["producer_ed25519_b64"] == ed
        msg = prepare_message(view=15, seq=500, digest=forged["digest"], replica_id="ovh-node-2")
        ok, reason = verify_signed_detailed(forged, msg)
        assert ok is False
        assert reason == "invalid_replica_key_binding"
        assert verify_prepare(forged) is False
