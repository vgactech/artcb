"""263 — tip-attest Q=3, evidence sidecar signature, 2-node liveness.

Not PBFT view-change. Not production-ready BFT. No live SSH in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.chain.manager import ChainManager
from artcb.consensus.byzantine_evidence import EvidenceStore
from artcb.consensus.liveness import assess_liveness
from artcb.consensus.live_bft import n_f_q
from artcb.consensus.tip_attest import attest_tip, quorum_from_attests, verify_attest


ROOT = Path(__file__).resolve().parents[1]


def test_rule_and_autoprompt_require_completeness_a_to_z() -> None:
    rule = (ROOT / ".cursor" / "rules" / "artcb-live-node.mdc").read_text(encoding="utf-8")
    assert "Complétude A→Z" in rule
    assert "Ne jamais terminer un tour" in rule
    assert "Partition **2 nœuds**" in rule or "Partition 2 nœuds" in rule
    assert "PBFT" in rule
    prompt = (ROOT / "AUTO_PROMPT_ARTCB").read_text(encoding="utf-8")
    assert "Complétude A→Z" in prompt
    assert "Ne jamais terminer un tour" in prompt


def test_n_f_q_still_four_is_q3() -> None:
    n, f, q = n_f_q(4)
    assert (n, f, q) == (4, 1, 3)


def test_verify_attest_accepts_hybrid_ed25519_when_liboqs_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from artcb.consensus.tip_attest import canonical_message, producer_key_b64, sign_message

    chain = ChainManager(tmp_path / "b.jsonl", key_path=tmp_path / "k", enable_security=False)
    msg = canonical_message(height=1, last_hash="aa" * 32, git_sha="b" * 40, node_id="n1")
    ed, pqc = producer_key_b64(chain)
    row = {
        "height": 1,
        "last_hash": "aa" * 32,
        "git_sha": "b" * 40,
        "node_id": "n1",
        "message": msg,
        "signature": sign_message(chain, msg),
        "producer_ed25519_b64": ed,
        "producer_pqc_b64": pqc,
    }
    assert verify_attest(row) is True
    monkeypatch.setattr("artcb.crypto.pqc.pqc_available", lambda: False)
    monkeypatch.setattr("src.artcb.crypto.pqc.pqc_available", lambda: False)
    assert verify_attest(row) is True


def test_two_of_four_is_below_quorum() -> None:
    report = assess_liveness(
        include_self=False,
        peer_reachable=[
            ("http://152.228.144.34:8000", True, 1),
            ("http://151.80.107.29:8000", True, 1),
            ("http://51.44.222.232:8000", False, None),
            ("http://91.134.45.8:8000", False, None),
        ],
    )
    assert report.n == 4 and report.q == 3
    assert report.reachable == 2
    assert report.below_quorum is True
    assert report.partitioned is True


def test_tip_attest_quorum_three_of_four(tmp_path: Path) -> None:
    from artcb.consensus.tip_attest import canonical_message, producer_key_b64, sign_message

    height, last_hash, git_sha = 1081, "ab" * 32, "c" * 40
    signed = []
    for nid in ("ovh-node-1", "ovh-node-2", "aws-node-3"):
        chain = ChainManager(
            tmp_path / nid / "blocks.jsonl",
            key_path=tmp_path / nid / "chain.key",
            enable_security=False,
        )
        msg = canonical_message(height=height, last_hash=last_hash, git_sha=git_sha, node_id=nid)
        ed, pqc = producer_key_b64(chain)
        row = {
            "height": height,
            "last_hash": last_hash,
            "git_sha": git_sha,
            "node_id": nid,
            "message": msg,
            "signature": sign_message(chain, msg),
            "producer_ed25519_b64": ed,
            "producer_pqc_b64": pqc,
        }
        assert verify_attest(row) is True
        signed.append(row)
    chain4 = ChainManager(tmp_path / "n4" / "blocks.jsonl", key_path=tmp_path / "n4" / "chain.key", enable_security=False)
    msg4 = canonical_message(height=99, last_hash="ff" * 32, git_sha=git_sha, node_id="ovh-node-4")
    ed, pqc = producer_key_b64(chain4)
    signed.append(
        {
            "height": 99,
            "last_hash": "ff" * 32,
            "git_sha": git_sha,
            "node_id": "ovh-node-4",
            "message": msg4,
            "signature": sign_message(chain4, msg4),
            "producer_ed25519_b64": ed,
            "producer_pqc_b64": pqc,
        }
    )
    q = quorum_from_attests(signed, n=4)
    assert q["ok"] is True
    assert q["q"] == 3
    assert q["quorum_count"] == 3
    assert q["height"] == height
    assert q["not_pbft_view_change"] is True
    assert attest_tip(
        ChainManager(tmp_path / "solo" / "blocks.jsonl", key_path=tmp_path / "solo.key", enable_security=False),
        git_sha=git_sha,
        node_id="solo",
    )["not_pbft_view_change"] is True


def test_evidence_sidecar_detects_tamper(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.record(kind="hash_mismatch", reason="hash_mismatch", from_node_id="ovh-node-4", index=1)
    sha = store.summary()["sha256"]
    chain = ChainManager(tmp_path / "chain" / "blocks.jsonl", key_path=tmp_path / "chain.key", enable_security=False)
    from artcb.consensus.tip_attest import producer_key_b64, sign_message

    ed, pqc = producer_key_b64(chain)
    store.write_sidecar(
        {
            "sha256": sha,
            "signature": sign_message(chain, sha),
            "producer_ed25519_b64": ed,
            "producer_pqc_b64": pqc,
        }
    )
    assert store.summary()["current_matches_sidecar"] is True
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write('{"kind":"junk"}\n')
    sm = store.summary()
    assert sm["current_matches_sidecar"] is False
    assert sm["sha256"] != sha
    assert sm["signed_on_chain"] is False


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    return TestClient(create_app())


def test_http_tip_attest_and_evidence_sign(client: TestClient) -> None:
    state = client.app.state.artcb
    state.chain.append_block(
        graph_id="g0",
        graph_root="r0",
        pol_score=0.1,
        visibility="public",
        source="ai:memo",
    )
    att = client.get("/api/v1/consensus/tip-attest")
    assert att.status_code == 200
    body = att.json()
    assert body["not_pbft_view_change"] is True
    assert verify_attest(body) is True
    offered = {
        "visibility": "public",
        "index": len(state.chain._read_all_blocks()),
        "timestamp": "2026-09-08T00:00:00Z",
        "prev_hash": state.chain.last_hash(),
        "graph_root": "evil",
        "merkle_root": "evil",
        "pol_score": 0.1,
        "hash": "ff" * 32,
        "signature": "ed25519:00",
    }
    client.post("/api/v1/p2p/blocks/offer", json={"blocks": [offered], "from_node_id": "ovh-node-4"})
    client.post("/api/v1/p2p/blocks/offer", json={"blocks": [offered], "from_node_id": "aws-node-3"})
    signed = client.post("/api/v1/consensus/byzantine/evidence/sign")
    assert signed.status_code == 200
    ev = client.get("/api/v1/consensus/byzantine/evidence")
    assert ev.status_code == 200
    payload = ev.json()
    assert payload["authenticated"] is True
    assert payload["tampered"] is False
    assert payload["summary"]["count"] >= 2


def test_partition_script_uses_artcb263_comment() -> None:
    text = (ROOT / "scripts" / "artcb263_partition_node.sh").read_text(encoding="utf-8")
    assert "COMMENT=\"artcb263\"" in text
    assert "blocks.jsonl is never touched" in text
    assert "restore deletes ONLY those rules" in text
