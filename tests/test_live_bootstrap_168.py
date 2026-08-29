"""Live-node resolver + Settlement replay (rapport 168). No invented live numbers."""

from __future__ import annotations

from pathlib import Path

import pytest

from artcb.economics.economic_snapshot import AlreadySettled, SettlementLedger, settlement_id
from artcb.live import apply_key_to_environ, auth_headers, parse_env_file, resolve_api_key, resolve_api_url


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
