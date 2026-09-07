"""Live-node resolver + Settlement replay (rapport 168). No invented live numbers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from artcb.economics.economic_snapshot import AlreadySettled, SettlementLedger, settlement_id
from artcb.live import (
    apply_key_to_environ,
    auth_headers,
    compact_memory_snapshot,
    parse_env_file,
    resolve_api_key,
    resolve_api_url,
)


def test_resolve_url_default() -> None:
    assert resolve_api_url().startswith("http")


def test_parse_env_file_and_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / "cursor_agent.env"
    env.write_text("ARTCB_API_KEY=artcb_" + ("ab" * 32) + "\nARTCB_API_URL=http://example.test\n")
    parsed = parse_env_file(env)
    assert parsed["ARTCB_API_KEY"].startswith("artcb_")
    monkeypatch.delenv("ARTCB_API_KEY", raising=False)
    monkeypatch.delenv("ARTCB_NODE_API_KEY", raising=False)
    monkeypatch.setenv("ARTCB_API_KEY", parsed["ARTCB_API_KEY"])
    assert resolve_api_key().startswith("artcb_")
    apply_key_to_environ(parsed["ARTCB_API_KEY"])
    headers = auth_headers()
    assert headers["Authorization"].startswith("Bearer artcb_")


def test_compact_memory_snapshot_uses_last_memo_not_chat() -> None:
    snap = compact_memory_snapshot(
        chain={"height": 9, "last_hash": "623d6e78" + "ab" * 28, "last_index": 8, "chain_valid": True},
        memory={
            "count": 1,
            "memos": [
                {
                    "block_index": 8,
                    "memo_type": "lesson",
                    "graph_id": "ai_memo_05a709e390c3",
                }
            ],
        },
        kcg_stats={"knowledge_count": 1, "total_consults": 1, "total_uses": 1},
        context={"total_ai_memos": 1, "prompt_ready": "Chaîne: 9 blocs | 1 memos IA gravés\n" + ("x" * 300)},
    )
    assert snap["chain_height"] == 9
    assert snap["last_index"] == 8
    assert snap["ai_memory_count"] == 1
    assert snap["last_memo_graph_id"] == "ai_memo_05a709e390c3"
    assert snap["kcg_knowledge_count"] == 1
    assert snap["kcg_uses"] == 1
    assert len(snap["ai_context_prompt_head"]) == 240
    assert "artcb_" not in json.dumps(snap)


def test_replay_same_workid_does_not_double_consume(tmp_path: Path) -> None:
    ledger = SettlementLedger(tmp_path / "ledger.json")
    sid = settlement_id(work_id="WorkID-X", snapshot_digest="snapdigest", protocol_version="167-distributed-snapshot")
    first = ledger.consume(sid, work_id="WorkID-X", node_id="A", epoch=1)
    with pytest.raises(AlreadySettled):
        ledger.consume(sid, work_id="WorkID-X", node_id="B", epoch=1)
    with pytest.raises(AlreadySettled):
        ledger.consume("other-sid", work_id="WorkID-X", node_id="C", epoch=1)
    assert ledger.count_for_work("WorkID-X") == 1
    assert first["settlement_id"] == sid
