"""Nanosecond traces on HTTP and book writes. No live node."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.chain.manager import ChainManager
from artcb.trace.ns import emit, list_traces, summarize


def test_emit_and_summarize(tmp_path: Path) -> None:
    emit(tmp_path, {"kind": "http", "path": "/health", "dur_ns": 1200, "ok": True})
    emit(tmp_path, {"kind": "chain_append", "index": 1, "dur_ns": 8000, "ok": True})
    rows = list_traces(tmp_path, limit=10)
    assert len(rows) == 2
    assert all("ts_ns" in r for r in rows)
    s = summarize(rows)
    assert s["rows"] == 2
    assert s["dur_ns_min"] == 1200
    assert s["by_kind"]["http"] == 1


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    return TestClient(create_app())


def test_http_middleware_sets_header_and_file(client: TestClient) -> None:
    r = client.get("/api/v1/chain/status")
    assert r.status_code == 200
    assert r.headers.get("X-ARTCB-Trace-Ns")
    assert int(r.headers["X-ARTCB-Trace-Ns"]) > 0
    traced = client.get("/api/v1/trace?kind=http")
    assert traced.status_code == 200
    body = traced.json()
    assert body["unit"] == "nanosecond"
    assert body["includes_book"] is True
    assert body.get("includes_pbft") is True
    assert body.get("granularity") == "nanosecond"
    assert body["summary"]["rows"] >= 1


def test_append_block_emits_chain_append(tmp_path: Path) -> None:
    chain = ChainManager(tmp_path / "chain" / "blocks.jsonl", key_path=tmp_path / "k", enable_security=False)
    chain.append_block(graph_id="g", graph_root="r", pol_score=0.1, visibility="public", source="ai:memo")
    rows = list_traces(tmp_path, kind="chain_append")
    assert rows
    assert rows[-1]["kind"] == "chain_append"
    assert rows[-1]["ok"] is True
    assert int(rows[-1]["dur_ns"]) > 0
