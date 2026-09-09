"""R292 — model thinking ≠ visibility=private; five AEP thinking states."""

from __future__ import annotations

import hashlib

import pytest

from artcb.live import ingest_thinking_file, thinking_file_skipped_reason
from artcb.memory.repo_scope import chain_visibility
from artcb.trace.aep import certify_provenance
from artcb.trace.agent_run import AgentRunLedger
from artcb.trace.thinking import (
    derive_thinking_recorded,
    empty_thinking_states,
    thinking_states,
    verify_thinking_integrity_chain,
)


def test_private_lane_is_not_model_thinking_acquisition() -> None:
    assert chain_visibility("private") == "private"
    states = empty_thinking_states()
    assert states["thinking_available_from_runtime"] is False
    assert states["thinking_received"] is False
    assert states["thinking_private_stored"] is False
    assert states["thinking_public_hash_recorded"] is False
    assert states["thinking_integrity_verified"] is False
    assert states["thinking_recorded"] is False
    assert states["acquisition"] == "NOT_PROVEN"
    assert derive_thinking_recorded({"thinking_private_stored": False, "thinking_integrity_verified": True}) is False
    assert derive_thinking_recorded({"thinking_private_stored": True, "thinking_integrity_verified": False}) is False
    fake_private = thinking_states(private_stored=True)
    assert fake_private["thinking_recorded"] is False


def test_integrity_requires_four_matching_hashes() -> None:
    raw = b"model-cot-bytes"
    digest = hashlib.sha256(raw).hexdigest()
    missing = verify_thinking_integrity_chain(raw=raw, payload=raw)
    assert missing["verified"] is False
    assert missing["reason"] == "missing_stage"
    assert "received" in missing["missing"]
    mismatch = verify_thinking_integrity_chain(
        raw=raw,
        payload=raw,
        received_sha256=digest,
        stored_sha256="00" * 32,
    )
    assert mismatch["verified"] is False
    assert mismatch["reason"] == "hash_mismatch"
    ok = verify_thinking_integrity_chain(
        raw=raw,
        payload=raw,
        received_sha256=digest,
        stored_sha256=digest,
    )
    assert ok["verified"] is True
    assert ok["sha256"] == digest


def test_http_200_without_stored_hash_is_not_integrity(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_http(method, url, *, api_key=None, body=None, timeout=20):
        calls.append(method)
        if method == "POST":
            return 200, {"block_index": 42, "block_hash": "ab" * 32, "graph_id": "ai_memo_x"}
        return 200, {"block_index": 42, "content_sha256": ""}

    monkeypatch.setattr("artcb.live.http_json", fake_http)
    path = tmp_path / "thinking.txt"
    path.write_text("full thinking", encoding="utf-8")
    out = ingest_thinking_file(path, url="https://example.test", api_key="artcb_" + ("ab" * 32))
    assert out["ingest_http"] == 200
    assert out["thinking_received"] is True
    assert out["thinking_private_stored"] is True
    assert out["thinking_integrity_verified"] is False
    assert out["thinking_recorded"] is False
    assert out["integrity"]["reason"] == "missing_stage"
    assert "POST" in calls and "GET" in calls


def test_full_hash_chain_sets_integrity(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "full thinking"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def fake_http(method, url, *, api_key=None, body=None, timeout=20):
        if method == "POST":
            assert body["visibility"] == "private"
            assert body["inject_context"] is False
            assert body["content"] == raw
            return 200, {
                "block_index": 7,
                "block_hash": "cd" * 32,
                "content_sha256": digest,
            }
        return 200, {"block_index": 7, "content_sha256": digest}

    monkeypatch.setattr("artcb.live.http_json", fake_http)
    path = tmp_path / "thinking.txt"
    path.write_text(raw, encoding="utf-8")
    out = ingest_thinking_file(path, url="https://example.test", api_key="artcb_" + ("ab" * 32))
    assert out["thinking_integrity_verified"] is True
    assert out["thinking_recorded"] is True
    assert out["thinking_public_hash_recorded"] is True
    assert out["acquisition"] == "RECEIVED_AND_INTEGRITY_VERIFIED"


def test_certify_does_not_treat_private_lane_as_thinking_recorded() -> None:
    led = AgentRunLedger(run_id="AR-292", agent_id="x", prompt_hash="a", code_sha="0" * 40)
    led.add("INPUT_RECEIVED", status="PASS")
    led.add("FINAL_VERDICT", status="PASS")
    cert = certify_provenance(
        led.events,
        profile="exhaustive_agent",
        thinking_recorded=True,
        thinking_states=empty_thinking_states(),
    )
    assert cert["thinking_recorded"] is False
    assert cert["thinking_available_from_runtime"] is False
    assert cert["execution_trace_complete"] is False
    assert cert["certified_100"] is False
    assert "CURSOR_RUNTIME_HOOK" in cert["missing_events"]


def test_cursor_skip_reason_is_acquisition_not_storage() -> None:
    reason = thinking_file_skipped_reason("")
    assert "ARTCB_INGEST_THINKING_FILE unset" in reason
    assert "visibility=private" in reason
    assert thinking_file_skipped_reason("/no/such") == "file_missing"
