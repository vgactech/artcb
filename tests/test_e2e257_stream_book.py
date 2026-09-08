"""257 — book offset index, NDJSON stream, O(1) status. No live node."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.bridges.manager import SUPPORTED_CHAINS, BridgeManager
from artcb.chain.book_index import BookIndex
from artcb.chain.manager import ChainManager
from artcb.trace.ns import list_traces


def test_book_index_o1_get_and_rebuild(tmp_path: Path) -> None:
    path = tmp_path / "chain" / "blocks.jsonl"
    chain = ChainManager(path, key_path=tmp_path / "k", enable_security=False)
    for i in range(12):
        chain.append_block(
            graph_id=f"g{i}",
            graph_root="r",
            pol_score=0.1,
            visibility="public",
            source="ai:memo",
        )
    assert chain.height() == 12
    last = chain.get_block(11)
    assert last is not None
    assert last["index"] == 11
    assert last["graph_id"] == "g11"
    assert chain.block_index_for_graph("g3") == 3
    assert chain.get_block(3)["graph_id"] == "g3"
    assert chain.chain_valid_tip() is True
    # rebuild from jsonl only
    off = path.with_name(path.name + ".off")
    off.unlink()
    book = BookIndex(path)
    assert book.height() == 12
    assert book.get_block(0)["graph_id"] == "g0"
    traces = list_traces(tmp_path, kind="book_rebuild")
    assert traces
    assert int(traces[-1]["dur_ns"]) >= 0


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    return TestClient(create_app())


def test_status_is_tip_not_full_verify(client: TestClient) -> None:
    state = client.app.state.artcb
    state.chain.append_block(
        graph_id="g-status",
        graph_root="r",
        pol_score=0.2,
        visibility="public",
        source="ai:memo",
    )

    def boom(*_a, **_k):
        raise AssertionError("full verify must not run on default /chain/status")

    state.chain.verify = boom  # type: ignore[method-assign]
    r = client.get("/api/v1/chain/status")
    assert r.status_code == 200
    body = r.json()
    assert body["height"] == 1
    assert body["chain_valid"] is True
    assert body["verify_mode"] == "tip"
    assert r.headers.get("X-ARTCB-Trace-Ns")
    one = client.get("/api/v1/chain/block/0")
    assert one.status_code == 200
    assert one.json()["block"]["graph_id"] == "g-status"


def test_chain_stream_ndjson(client: TestClient) -> None:
    state = client.app.state.artcb
    for i in range(6):
        state.chain.append_block(
            graph_id=f"stream{i}",
            graph_root="r",
            pol_score=0.1,
            visibility="public",
            source="ai:memo",
        )
    r = client.get("/api/v1/chain/stream?from_index=2&limit=3")
    assert r.status_code == 200
    assert "ndjson" in r.headers.get("content-type", "")
    rows = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    assert len(rows) == 3
    assert rows[0]["index"] == 2
    assert rows[-1]["index"] == 4
    listed = client.get("/api/v1/chain?from_index=4&limit=2")
    assert listed.status_code == 200
    assert listed.json()["count"] == 2


def test_search_does_not_scan_book(client: TestClient) -> None:
    state = client.app.state.artcb
    state.chain.append_block(
        graph_id="search-g",
        graph_root="r",
        pol_score=0.4,
        visibility="public",
        source="ai:memo",
    )

    def boom(*_a, **_k):
        raise AssertionError("search must not list the whole book")

    state.chain.list_blocks = boom  # type: ignore[method-assign]
    state.vectors.search = lambda *_a, **_k: [{"graph_id": "search-g", "score": 0.99}]
    r = client.get("/api/v1/chain/search?q=continuite")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert body["results"][0]["block"]["block_index"] == 0


def test_sse_max_seconds_returns(client: TestClient) -> None:
    r = client.get("/api/v1/ai/events?max_seconds=0.2")
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    assert "connected" in r.text


def test_bridges_status_all_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(self, chain: str, *, timeout: float = 15) -> dict:
        time.sleep(0.35)
        return {"chain": chain, "status": "ok", "timeout": timeout}

    monkeypatch.setattr(BridgeManager, "ping_chain", slow)
    t0 = time.perf_counter()
    rows = BridgeManager().status_all()
    elapsed = time.perf_counter() - t0
    assert len(rows) == len(SUPPORTED_CHAINS)
    assert elapsed < 1.4
