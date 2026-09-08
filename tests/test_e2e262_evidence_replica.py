"""262 — evidence replica merge + digest. Creator-stop is live, not this file."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from artcb.consensus.byzantine_evidence import EvidenceStore
from artcb.p2p.official_replica import _safe_rel, list_replica_files, write_replica_files


def test_evidence_summary_has_sha256(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.record(kind="hash_mismatch", reason="hash_mismatch", from_node_id="ovh-node-4", index=1)
    sm = store.summary()
    assert sm["persistent"] is True
    assert sm["signed_on_chain"] is False
    assert len(sm["sha256"]) == 64
    assert sm["bytes"] > 0
    assert sm["count"] == 1


def test_consensus_evidence_is_replica_safe() -> None:
    assert _safe_rel("consensus/byzantine_evidence.jsonl") is not None
    assert _safe_rel("../etc/passwd") is None


def test_evidence_jsonl_merges_instead_of_wipe(tmp_path: Path) -> None:
    dest_dir = tmp_path / "dst"
    local = dest_dir / "consensus"
    local.mkdir(parents=True)
    (local / "byzantine_evidence.jsonl").write_text('{"kind":"local","ts_ns":1}\n', encoding="utf-8")
    incoming = b'{"kind":"local","ts_ns":1}\n{"kind":"remote","ts_ns":2}\n'
    result = write_replica_files(
        dest_dir,
        [
            {
                "path": "consensus/byzantine_evidence.jsonl",
                "sha256": hashlib.sha256(incoming).hexdigest(),
                "content_b64": base64.b64encode(incoming).decode("ascii"),
            }
        ],
    )
    assert result["written"] == 1
    text = (local / "byzantine_evidence.jsonl").read_text(encoding="utf-8")
    assert "local" in text and "remote" in text
    assert text.count("local") == 1


def test_list_replica_files_includes_evidence(tmp_path: Path) -> None:
    path = tmp_path / "consensus" / "byzantine_evidence.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"kind":"equivocation"}\n', encoding="utf-8")
    items = list_replica_files(tmp_path)
    rels = {i["path"] for i in items}
    assert "consensus/byzantine_evidence.jsonl" in rels
