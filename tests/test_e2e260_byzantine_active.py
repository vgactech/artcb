"""260 — active Byzantine *sender*, not an honest-offline stop (259).

Eight checks from the 259 audit. Local only. No official node is stopped.
The book is never wiped. This is not PBFT / not production-ready BFT.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nacl import encoding, signing

from api.main import create_app
from artcb.chain import ffi
from artcb.chain.ffi import HASH_VERSION_V1
from artcb.chain.manager import ChainManager
from artcb.consensus.byzantine_evidence import EvidenceStore
from artcb.consensus.byzantine_guard import signature_envelope_ok
from artcb.p2p.official_replica import import_replica_blocks
from artcb.p2p.public_archive import PublicBlockArchive
from artcb.p2p.sync import P2PSyncService, decide_public_import


def _rehash(block: dict) -> dict:
    row = dict(block)
    version = int(row.get("hash_version") or HASH_VERSION_V1)
    eco = None
    if version >= 2:
        eco = str(row.get("economic_root") or (row.get("economics") or {}).get("economic_root") or "")
    row["hash"] = ffi.build_block_hash(
        int(row["index"]),
        str(row["timestamp"]),
        str(row["prev_hash"]),
        str(row["graph_root"]),
        str(row.get("merkle_root") or row["graph_root"]),
        float(row["pol_score"]),
        economic_root=eco,
    )
    return row


def _svc(chain: ChainManager, tmp: Path) -> P2PSyncService:
    svc = object.__new__(P2PSyncService)
    svc.chain = chain
    svc.archive = PublicBlockArchive(tmp)
    svc.symbol_sync = None
    svc.last_import_decisions = []
    return svc


def _pair(tmp_path: Path) -> tuple[ChainManager, ChainManager]:
    key = tmp_path / "chain.key"
    path_a = tmp_path / "a" / "blocks.jsonl"
    path_b = tmp_path / "b" / "blocks.jsonl"
    chain_a = ChainManager(path_a, key_path=key, enable_security=False)
    chain_a.append_block(
        graph_id="genesis",
        graph_root="root0",
        pol_score=0.0,
        visibility="public",
        block_reward=0,
        source="authz_commitment",
    )
    path_b.parent.mkdir(parents=True)
    path_b.write_text(path_a.read_text(encoding="utf-8"), encoding="utf-8")
    chain_b = ChainManager(path_b, key_path=key, enable_security=False)
    return chain_a, chain_b


def _honest_next(chain: ChainManager, graph_id: str = "honest") -> dict:
    chain.append_block(
        graph_id=graph_id,
        graph_root=f"root_{graph_id}",
        pol_score=0.4,
        visibility="public",
        block_reward=0,
        source="ai:memo",
    )
    return chain._read_all_blocks()[-1]


def test_signature_envelope_helper() -> None:
    assert signature_envelope_ok("ed25519:ab")
    assert signature_envelope_ok("hybrid:ed25519:aa|mldsa65:bb")
    assert not signature_envelope_ok("")
    assert not signature_envelope_ok("totally-forged")


def test_1_honest_nodes_still_converge(tmp_path: Path) -> None:
    honest_a, honest_b = _pair(tmp_path)
    svc = _svc(honest_b, tmp_path / "b")
    svc.import_public_blocks(
        [{"visibility": "public", "index": 1, "hash": "ff" * 32, "prev_hash": "00" * 32, "signature": "nope"}],
        from_node_id="ovh-node-4",
    )
    good = _honest_next(honest_a, "honest_progress")
    svc.import_public_blocks([good], from_node_id="ovh-node-1")
    assert svc.last_import_decisions[-1].action == "append"
    assert honest_b.last_hash() == honest_a.last_hash()


def test_2_invalid_block_rejected(tmp_path: Path) -> None:
    _a, honest = _pair(tmp_path)
    svc = _svc(honest, tmp_path / "b")
    before = honest.last_hash()
    svc.import_public_blocks(
        [{"visibility": "public", "index": 1, "hash": "x", "prev_hash": "y"}],
        from_node_id="ovh-node-4",
    )
    assert honest.last_hash() == before
    assert svc.last_import_decisions[-1].action == "reject"


def test_3_invalid_signature_rejected(tmp_path: Path) -> None:
    producer, honest = _pair(tmp_path)
    block = dict(_honest_next(producer, "sig"))
    block["signature"] = "not-a-real-signature"
    svc = _svc(honest, tmp_path / "b")
    before = honest.last_hash()
    height = len(honest._read_all_blocks())
    svc.import_public_blocks([block], from_node_id="ovh-node-4")
    assert honest.last_hash() == before
    assert len(honest._read_all_blocks()) == height
    assert svc.last_import_decisions[-1].reason == "invalid_signature"
    ev = EvidenceStore(tmp_path).list()
    assert any(row.get("kind") == "invalid_signature" for row in ev)


def test_3b_embedded_key_mismatch_rejected(tmp_path: Path) -> None:
    producer, honest = _pair(tmp_path)
    block = dict(_honest_next(producer, "sigkey"))
    other = signing.SigningKey.generate()
    block["producer_ed25519_b64"] = other.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii")
    svc = _svc(honest, tmp_path / "b")
    svc.import_public_blocks([block], from_node_id="ovh-node-4")
    assert svc.last_import_decisions[-1].reason == "invalid_signature"
    assert honest.last_hash() != block["hash"]


def test_4_inconsistent_hash_rejected(tmp_path: Path) -> None:
    producer, honest = _pair(tmp_path)
    block = dict(_honest_next(producer, "hash"))
    block["hash"] = "aa" * 32
    svc = _svc(honest, tmp_path / "b")
    before = honest.last_hash()
    svc.import_public_blocks([block], from_node_id="ovh-node-4")
    assert honest.last_hash() == before
    assert svc.last_import_decisions[-1].reason == "hash_mismatch"
    ev = EvidenceStore(tmp_path).list()
    assert any(row.get("kind") == "hash_mismatch" for row in ev)


def test_5_contradictory_proposals_detected(tmp_path: Path) -> None:
    producer, honest = _pair(tmp_path)
    x = dict(_honest_next(producer, "x"))
    genesis_line = (tmp_path / "a" / "blocks.jsonl").read_text(encoding="utf-8").splitlines()[0]
    (tmp_path / "c").mkdir(parents=True)
    (tmp_path / "c" / "blocks.jsonl").write_text(genesis_line + "\n", encoding="utf-8")
    y_src = ChainManager(tmp_path / "c" / "blocks.jsonl", key_path=tmp_path / "ck", enable_security=False)
    y = dict(_honest_next(y_src, "y"))
    assert x["index"] == y["index"]
    assert x["hash"] != y["hash"]
    svc = _svc(honest, tmp_path / "b")
    svc.import_public_blocks([x, y], from_node_id="ovh-node-4")
    reasons = [d.reason for d in svc.last_import_decisions]
    assert "extends_tip" in reasons
    assert "equivocation" in reasons
    assert honest.last_hash() == x["hash"]
    ev = EvidenceStore(tmp_path).list()
    assert any(row.get("kind") == "equivocation" for row in ev)


def test_6_faulty_peer_cannot_stall_progress(tmp_path: Path) -> None:
    producer, honest = _pair(tmp_path)
    tip = honest.last_hash()
    height = len(honest._read_all_blocks())
    svc = _svc(honest, tmp_path / "b")
    flood = []
    for i in range(12):
        flood.append(
            {
                "visibility": "public",
                "index": height,
                "timestamp": "2026-09-08T00:00:00Z",
                "prev_hash": "00" * 32,
                "graph_root": f"evil{i}",
                "merkle_root": f"evil{i}",
                "pol_score": 0.1,
                "hash": "ff" * 32,
                "signature": "ed25519:00",
            }
        )
    svc.import_public_blocks(flood, from_node_id="ovh-node-4")
    assert honest.last_hash() == tip
    assert len(honest._read_all_blocks()) == height
    good = _honest_next(producer, "after_flood")
    svc.import_public_blocks([good], from_node_id="ovh-node-1")
    assert honest.last_hash() == good["hash"]
    assert len(honest._read_all_blocks()) == height + 1


def test_7_restore_does_not_wipe_divergent_book(tmp_path: Path) -> None:
    """Diverged node keeps its lines; conflicting replica is evidence, not a wipe."""
    honest, diverged = _pair(tmp_path)
    good = _honest_next(honest, "canonical")
    _honest_next(diverged, "evil_local")
    before_lines = diverged.blocks_path.read_text(encoding="utf-8").count("\n")
    before_tip = diverged.last_hash()
    svc = _svc(diverged, tmp_path / "b")
    result = import_replica_blocks(svc, [good], from_node_id="ovh-node-1")
    assert result["imported"] == 0
    assert any(row.get("reason") == "equivocation" for row in result["rejected"])
    assert diverged.last_hash() == before_tip
    assert diverged.blocks_path.read_text(encoding="utf-8").count("\n") == before_lines


def test_7b_behind_node_still_catchup(tmp_path: Path) -> None:
    """259 path: behind, not diverged → replica still extends."""
    honest, behind = _pair(tmp_path)
    good = _honest_next(honest, "catchup")
    svc = _svc(behind, tmp_path / "b")
    result = import_replica_blocks(svc, [good], from_node_id="ovh-node-1")
    assert result["imported"] == 1
    assert behind.last_hash() == honest.last_hash()


def test_8_evidence_is_queryable(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.record(
        kind="equivocation",
        reason="equivocation",
        from_node_id="ovh-node-4",
        index=1078,
        hash_offered="aa",
        hash_held="bb",
    )
    rows = store.list()
    assert rows[-1]["from_node_id"] == "ovh-node-4"
    assert store.summary()["count"] == 1
    assert store.summary()["not_block_append_bft"] is True


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    return TestClient(create_app())


def test_http_offer_and_evidence_routes(client: TestClient) -> None:
    state = client.app.state.artcb
    state.chain.append_block(
        graph_id="g0",
        graph_root="r0",
        pol_score=0.1,
        visibility="public",
        source="ai:memo",
    )
    tip = state.chain.last_hash()
    height = len(state.chain._read_all_blocks())
    offered = {
        "visibility": "public",
        "index": height,
        "timestamp": "2026-09-08T00:00:00Z",
        "prev_hash": tip,
        "graph_root": "evil",
        "merkle_root": "evil",
        "pol_score": 0.1,
        "hash": "ff" * 32,
        "signature": "ed25519:00",
    }
    resp = client.post(
        "/api/v1/p2p/blocks/offer",
        json={"blocks": [offered], "from_node_id": "ovh-node-4"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tip_after"] == tip
    assert body["height_after"] == height
    assert body["decisions"][0]["reason"] == "hash_mismatch"
    ev = client.get("/api/v1/consensus/byzantine/evidence")
    assert ev.status_code == 200
    assert ev.json()["not_block_append_bft"] is True
    assert ev.json()["summary"]["count"] >= 1


def test_decide_equivocation_is_not_a_merge() -> None:
    held = {"index": 3, "hash": "aa" * 32}
    offered = {
        "visibility": "public",
        "index": 3,
        "hash": "bb" * 32,
        "prev_hash": "cc" * 32,
        "signature": "ed25519:00",
    }
    d = decide_public_import(
        offered,
        local_len=4,
        local_tip="dd" * 32,
        local_hashes={"aa" * 32},
        structure_ok=True,
        existing_at_index=held,
    )
    assert d.action == "reject"
    assert d.reason == "equivocation"
