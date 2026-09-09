"""R289 — AEP lossless operational provenance (not private thinking)."""

from __future__ import annotations

import json
from pathlib import Path

from artcb.trace.aep import (
    EVENT_CATALOG,
    certify_provenance,
    lossless_input,
    verify_hash_chain,
)
from artcb.trace.agent_run import AEP_POLICY_ID, AgentRunLedger, aep_policy_hash, sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
R284_LOG = ROOT / "logs" / "284_agent_run_20260909T161106Z.json"


def test_lossless_forbids_silent_truncation() -> None:
    raw = b"hello world"
    ok = lossless_input(raw, truncated=False)
    assert ok["ok"] is True
    assert ok["raw_hash"] == sha256_bytes(raw)
    assert ok["thinking_included"] is False
    bad = lossless_input(raw, truncated=True)
    assert bad["ok"] is False
    assert bad["reason"] == "silent_truncation"
    declared = lossless_input(raw, truncated=True, transformation_id="clip-v1", transformed=b"hello")
    assert declared["ok"] is True
    assert declared["transformation_id"] == "clip-v1"


def test_r284_six_events_are_partial_exhaustive() -> None:
    data = json.loads(R284_LOG.read_text(encoding="utf-8"))
    events = data["events"]
    assert len(events) == 6
    assert [e["action"] for e in events] == [
        "INPUT_RECEIVED",
        "LIVE_VERIFICATION",
        "LIVE_VERIFICATION",
        "LIVE_VERIFICATION",
        "LIVE_VERIFICATION",
        "FINAL_VERDICT",
    ]
    exhaustive = certify_provenance(events, profile="exhaustive_agent")
    assert exhaustive["execution_trace_complete"] is False
    assert exhaustive["certified_100"] is False
    assert exhaustive["e2e_agent_artcb"] == "NOT_PROVEN"
    assert exhaustive["thinking_recorded"] is False
    summary = certify_provenance(events, profile="r284_classify_summary")
    assert summary["profile_certification"] == "COMPLETE_FOR_SUMMARY"
    ssh = certify_provenance(events, profile="mac_ssh_probe")
    assert ssh["profile_certification"] == "PARTIAL"
    assert "SECRET_LOOKUP" in ssh["missing_events"]


def test_ssh_fail_can_be_provenance_complete_for_profile() -> None:
    led = AgentRunLedger(
        run_id="AR-289-TEST",
        agent_id="cursor-cloud-agent",
        prompt_hash="abc",
        code_sha="0" * 40,
        policy_id=AEP_POLICY_ID,
        policy_version="289.1",
        policy_hash_value=aep_policy_hash(),
    )
    led.add("INPUT_RECEIVED", status="PASS")
    led.add("ENVIRONMENT_START", status="PASS", actor="SYSTEM_ACTION")
    led.add("SECRET_LOOKUP", status="FAIL", detail={"target": "KEY_API_ARTCB_DOPPLER_MAC", "result": "NOT_FOUND"})
    led.add("DOPPLER_READ", status="PASS", detail={"project": "artcb-blockchain", "config": "dev"})
    led.add("DOPPLER_KEY_CHECK", status="FAIL", detail={"key": "KEY_API_ARTCB_DOPPLER_MAC", "result": "ABSENT"})
    led.add("SSH_PREPARATION", status="SKIP", detail={"private_key_available": False})
    led.add("NETWORK_REQUEST", status="FAIL", detail={"target": "10.234.49.2:22", "result": "TIMEOUT"})
    led.add("DECISION", status="FAIL", detail={"mac_node": "NOT_REACHABLE"})
    led.add("ENVIRONMENT_END", status="PASS", actor="SYSTEM_ACTION")
    led.add("FINAL_VERDICT", status="FAIL", detail={"ssh": "FAIL", "provenance": "COMPLETE_FOR_PROFILE"})
    assert verify_hash_chain(led.events) is True
    cert = certify_provenance(led.events, profile="mac_ssh_probe", lossless_ok=True)
    assert cert["profile_certification"] == "COMPLETE_FOR_PROFILE"
    assert cert["execution_trace_complete"] is True
    assert cert["certified_100"] is False
    assert cert["tool_trace_complete"] is False
    dumped = json.dumps(led.write(Path("/tmp/artcb_aep_test.json")))
    assert "BEGIN" not in dumped
    assert "thinking" not in dumped.lower() or "not recorded" in dumped.lower()


def test_missing_failure_event_is_a_gap() -> None:
    led = AgentRunLedger(run_id="AR-289-GAP", agent_id="x", prompt_hash="a", code_sha="0" * 40)
    led.add("INPUT_RECEIVED", status="PASS")
    led.add("FINAL_VERDICT", status="PASS")
    cert = certify_provenance(led.events, profile="mac_ssh_probe")
    assert cert["profile_certification"] in {"PARTIAL", "NOT_PROVEN"}
    assert cert["execution_trace_complete"] is False
    assert "SECRET_LOOKUP" in cert["missing_events"]


def test_event_catalog_has_no_private_thinking() -> None:
    assert "PRIVATE_THINKING" not in EVENT_CATALOG
    assert "CHAIN_OF_THOUGHT" not in EVENT_CATALOG
    assert "SSH_ATTEMPT" in EVENT_CATALOG
    assert "SECRET_LOOKUP" in EVENT_CATALOG
