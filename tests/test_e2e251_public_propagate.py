"""Phase 251 — public tip-extend + official replica + flux. No live node."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.chain.manager import ChainManager
from artcb.p2p.flux import append_flux, list_flux, summarize_flux
from artcb.p2p.official_replica import (
    import_replica_blocks,
    list_replica_blocks,
    replica_peer_allowed,
    write_replica_files,
)
from artcb.p2p.public_archive import PublicBlockArchive
from artcb.p2p.sync import P2PSyncService, decide_public_import


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
        source="genesis",
    )
    path_b.parent.mkdir(parents=True)
    path_b.write_text(path_a.read_text(encoding="utf-8"), encoding="utf-8")
    chain_b = ChainManager(path_b, key_path=key, enable_security=False)
    return chain_a, chain_b


def test_replica_allowlist() -> None:
    assert replica_peer_allowed("152.228.144.34")
    assert replica_peer_allowed("151.80.107.29")
    assert replica_peer_allowed("51.44.222.232")
    assert replica_peer_allowed("91.134.45.8")
    assert replica_peer_allowed("127.0.0.1")
    assert replica_peer_allowed("testclient")
    assert not replica_peer_allowed("8.8.8.8")
    assert not replica_peer_allowed("1.2.3.4")


def test_public_extends_tip_and_private_stays_off_anonymous(tmp_path: Path) -> None:
    chain_a, chain_b = _pair(tmp_path)
    chain_a.append_block(
        graph_id="pub1",
        graph_root="r1",
        pol_score=0.4,
        visibility="public",
        block_reward=0,
        source="ai:memo",
    )
    pub = chain_a._read_all_blocks()[-1]
    chain_a.append_block(
        graph_id="priv1",
        graph_root="r2",
        pol_score=0.4,
        visibility="private",
        block_reward=0,
        source="ai:ingest",
    )
    priv = chain_a._read_all_blocks()[-1]
    svc = _svc(chain_b, tmp_path / "arch")
    local = chain_b._read_all_blocks()
    pub_decision = decide_public_import(
        pub,
        local_len=len(local),
        local_tip=chain_b.last_hash(),
        local_hashes={str(r.get("hash") or "") for r in local},
        structure_ok=P2PSyncService.verify_block_structure(pub),
    )
    assert pub_decision.action == "append"
    imported = svc.import_public_blocks([pub, priv], from_node_id="ovh1")
    assert imported >= 1
    assert chain_b.last_hash() == pub["hash"]
    assert all(b.get("visibility") != "private" for b in chain_b._read_all_blocks())
    reasons = {d.reason for d in svc.last_import_decisions}
    assert "not_public" in reasons


def test_official_replica_imports_private_then_public(tmp_path: Path) -> None:
    chain_a, chain_b = _pair(tmp_path)
    chain_a.append_block(
        graph_id="priv_mid",
        graph_root="rm",
        pol_score=0.3,
        visibility="private",
        source="ai:ingest",
    )
    chain_a.append_block(
        graph_id="pub_after",
        graph_root="rp",
        pol_score=0.3,
        visibility="public",
        source="ai:ingest",
    )
    svc_b = _svc(chain_b, tmp_path / "arch")
    extra = chain_a._read_all_blocks()[1:]
    result = import_replica_blocks(svc_b, extra)
    assert result["imported"] == 2
    assert result["rejected"] == []
    assert len(chain_b._read_all_blocks()) == len(chain_a._read_all_blocks())
    assert chain_b.last_hash() == chain_a.last_hash()
    vis = {b.get("visibility") for b in chain_b._read_all_blocks()}
    assert vis == {"public", "private"}


def test_flux_jsonl_and_summary(tmp_path: Path) -> None:
    append_flux(
        tmp_path,
        {
            "kind": "official_replica_blocks",
            "peer": "ovh-node-2",
            "rtt_ms": 12.5,
            "bytes_wire": 400,
            "pushed": 20,
            "imported": 20,
            "ok": True,
        },
    )
    append_flux(tmp_path, {"kind": "official_replica_blocks", "peer": "aws-node-3", "ok": False, "error": "timeout"})
    rows = list_flux(tmp_path, limit=10)
    assert len(rows) == 2
    summary = summarize_flux(rows)
    assert summary["ok"] == 1
    assert summary["errors"] == 1
    assert summary["bytes_wire_ok"] == 400
    assert summary["ingest_1065_had_no_inter_node_flux"] is True


def test_replica_file_write_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "graphs").mkdir(parents=True)
    payload = b'{"graph_id":"ing_test"}'
    (src / "graphs" / "ing_test.json").write_bytes(payload)
    import base64

    written = write_replica_files(
        tmp_path / "dst",
        [
            {
                "path": "graphs/ing_test.json",
                "sha256": __import__("hashlib").sha256(payload).hexdigest(),
                "content_b64": base64.b64encode(payload).decode("ascii"),
            },
            {"path": "../etc/passwd", "content_b64": base64.b64encode(b"x").decode("ascii")},
        ],
    )
    assert written["written"] == 1
    assert written["rejected"] == 1
    assert (tmp_path / "dst" / "graphs" / "ing_test.json").read_bytes() == payload


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    return TestClient(create_app())


def test_replica_http_loopback_lists_private(client: TestClient) -> None:
    state = client.app.state.artcb
    state.chain.append_block(
        graph_id="priv_http",
        graph_root="rh",
        pol_score=0.2,
        visibility="private",
        source="ai:ingest",
    )
    state.chain.append_block(
        graph_id="pub_http",
        graph_root="rph",
        pol_score=0.2,
        visibility="public",
        source="ai:memo",
    )
    pub = client.get("/api/v1/p2p/blocks/public")
    assert pub.status_code == 200
    assert all(b.get("visibility") == "public" for b in pub.json()["blocks"])
    replica = client.get("/api/v1/p2p/replica/blocks")
    assert replica.status_code == 200
    vis = {b.get("visibility") for b in replica.json()["blocks"]}
    assert "private" in vis
    assert "public" in vis
    flux = client.get("/api/v1/p2p/flux")
    assert flux.status_code == 200
    assert flux.json()["ingest_1065_had_no_inter_node_flux"] is True
    status = client.get("/api/v1/p2p/status")
    assert status.json()["official_replica_full_book"] is True
    assert status.json()["private_never_synced"] is True


def test_list_replica_blocks_limit(tmp_path: Path) -> None:
    chain_a, _ = _pair(tmp_path)
    for i in range(5):
        chain_a.append_block(
            graph_id=f"x{i}",
            graph_root=f"r{i}",
            pol_score=0.1,
            visibility="private" if i % 2 else "public",
            source="ai:ingest",
        )
    svc = _svc(chain_a, tmp_path / "arch")
    chunk = list_replica_blocks(svc, from_index=2, limit=2)
    assert len(chunk) == 2
    assert int(chunk[0]["index"]) == 2
