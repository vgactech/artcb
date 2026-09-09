#!/usr/bin/env python3
"""R289 live — AEP operational ledger for the Mac RFC1918 / Doppler probe.

Records what *this Python probe* did. Does not claim Cursor tool-call capture.
Does not claim model thinking was acquired: Cursor does not inject it.
visibility=private ≠ thinking stored. SSH FAIL may be COMPLETE_FOR_PROFILE.
CERTIFIED_100 stays false. N04 last. PRE_R273 GAP kept.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.mac_node_access import (  # noqa: E402
    TOKEN_ENV,
    doppler_secret_names,
    json_contains_private_key,
    probe_tcp,
    select_cloud_remote,
    token_present,
)
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS, SHARED_DOPPLER_PROJECT  # noqa: E402
from artcb.trace.aep import certify_provenance, lossless_input  # noqa: E402
from artcb.trace.agent_run import (  # noqa: E402
    AEP_POLICY_ID,
    AEP_POLICY_VERSION,
    AgentRunLedger,
    aep_policy_hash,
    sha256_json,
)
from artcb.trace.thinking import empty_thinking_states  # noqa: E402

HTTP = l265.HTTP
PROMPT_PATH = Path("/tmp/artcb_turn_prompt.txt")


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw = PROMPT_PATH.read_bytes() if PROMPT_PATH.is_file() else b""
    lossless = lossless_input(raw, truncated=False)
    health = {nid: l265._http("GET", f"{HTTP[nid]}/health", timeout=12) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (health[nid].get("git_sha") or "")[:40] for nid in OFFICIAL_COMPUTE_NODE_IDS}
    chain = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/chain/status", timeout=12)
    code_sha = shas.get("ovh-node-1") or ""
    led = AgentRunLedger(
        run_id=f"AR-289-{stamp}",
        agent_id="cursor-cloud-agent",
        prompt_hash=lossless.get("raw_hash") or "",
        code_sha=code_sha,
        policy_id=AEP_POLICY_ID,
        policy_version=AEP_POLICY_VERSION,
        policy_hash_value=aep_policy_hash(),
    )
    led.add(
        "INPUT_RECEIVED",
        status="PASS" if lossless.get("ok") else "FAIL",
        input_hash=str(lossless.get("raw_hash") or ""),
        detail={"raw_bytes": lossless.get("raw_bytes"), "thinking_included": False, "path": str(PROMPT_PATH)},
    )
    led.add(
        "ENVIRONMENT_START",
        status="PASS",
        actor="SYSTEM_ACTION",
        output_hash=sha256_json(shas),
        detail={"official_shas": shas, "height": chain.get("height"), "last_hash": chain.get("last_hash")},
    )

    present = token_present()
    led.add(
        "SECRET_LOOKUP",
        status="FAIL" if not present else "PASS",
        detail={"target": TOKEN_ENV, "result": "NOT_FOUND" if not present else "PRESENT", "value_printed": False},
    )

    shared = (os.environ.get("DOPPLER_TOKEN") or "").strip()
    names_dev = doppler_secret_names(shared, SHARED_DOPPLER_PROJECT, "dev") if shared else {"http": 0}
    led.add(
        "DOPPLER_READ",
        status="PASS" if names_dev.get("http") == 200 else "FAIL",
        output_hash=sha256_json({k: names_dev.get(k) for k in ("http", "n_names", "has_key_api_artcb_doppler_mac")}),
        detail={
            "project": SHARED_DOPPLER_PROJECT,
            "config": "dev",
            "http": names_dev.get("http"),
            "n_names": names_dev.get("n_names"),
            "result": "SUCCESS" if names_dev.get("http") == 200 else "FAIL",
        },
    )
    mac_in_dev = bool(names_dev.get("has_key_api_artcb_doppler_mac"))
    led.add(
        "DOPPLER_KEY_CHECK",
        status="FAIL" if not mac_in_dev else "PASS",
        detail={"key": TOKEN_ENV, "config": "dev", "result": "ABSENT" if not mac_in_dev else "PRESENT"},
    )
    names_prd = doppler_secret_names(shared, SHARED_DOPPLER_PROJECT, "prd") if shared else {"http": 0}
    led.add(
        "DOPPLER_READ",
        status="FAIL" if names_prd.get("http") != 200 else "PASS",
        detail={
            "project": SHARED_DOPPLER_PROJECT,
            "config": "prd",
            "http": names_prd.get("http"),
            "result": "HTTP_400" if names_prd.get("http") == 400 else names_prd.get("http"),
        },
    )

    remote = select_cloud_remote()
    led.add(
        "SSH_PREPARATION",
        status="SKIP",
        detail={
            "private_key_available": False,
            "remote_ok": remote.get("ok"),
            "remote_reason": remote.get("reason"),
            "rejected": remote.get("rejected"),
        },
    )
    tcp22 = probe_tcp("10.234.49.2", 22, timeout=5.0)
    led.add(
        "NETWORK_REQUEST",
        status="FAIL",
        detail={"target": "10.234.49.2:22", "result": tcp22.get("error") or "TIMEOUT", "ok": tcp22.get("ok")},
    )
    tcp8001 = probe_tcp("10.234.49.2", 8001, timeout=5.0)
    led.add(
        "NETWORK_REQUEST",
        status="FAIL",
        detail={"target": "10.234.49.2:8001", "result": tcp8001.get("error") or "TIMEOUT", "ok": tcp8001.get("ok")},
    )
    led.add(
        "DECISION",
        status="FAIL",
        detail={"mac_node": "NOT_REACHABLE", "tunnel": "ABSENT", "rfc1918": True},
    )

    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        led.add(
            "LIVE_VERIFICATION",
            status="PASS" if health[nid].get("git_sha") else "FAIL",
            output_hash=sha256_json({"git_sha": shas[nid], "status": health[nid].get("status")}),
            detail={"node_id": nid, "git_sha": shas[nid]},
            actor="SYSTEM_ACTION",
        )

    led.set_code_sha_end(shas.get("ovh-node-1") or "")
    led.add(
        "ENVIRONMENT_END",
        status="PASS",
        actor="SYSTEM_ACTION",
        detail={"code_sha_start": led.code_sha_start, "code_sha_end": led.code_sha_end},
    )
    thinking = empty_thinking_states(reason="cursor_runtime_did_not_inject_thinking")
    led.set_thinking_states(thinking)
    cert = certify_provenance(
        led.events,
        profile="mac_ssh_probe",
        lossless_ok=bool(lossless.get("ok")),
        cursor_runtime_instrumented=False,
        thinking_states=thinking,
    )
    exhaustive = certify_provenance(
        led.events, profile="exhaustive_agent", thinking_states=thinking
    )
    led.add(
        "FINAL_VERDICT",
        status="FAIL",
        detail={
            "ssh": "FAIL",
            "lan": "NOT_REACHABLE",
            "provenance_mac_ssh": cert["profile_certification"],
            "provenance_exhaustive": exhaustive["profile_certification"],
            "certified_100": False,
        },
    )
    # Re-certify including FINAL_VERDICT (already in events).
    cert = certify_provenance(
        led.events,
        profile="mac_ssh_probe",
        lossless_ok=bool(lossless.get("ok")),
        cursor_runtime_instrumented=False,
        thinking_states=thinking,
    )
    exhaustive = certify_provenance(
        led.events, profile="exhaustive_agent", thinking_states=thinking
    )
    ledger_path = ROOT / "logs" / f"289_aep_agent_run_{stamp}.json"
    ledger = led.write(ledger_path)
    ledger["lossless"] = {k: lossless[k] for k in lossless if k != "raw"}
    ledger["certify_mac_ssh"] = cert
    ledger["certify_exhaustive"] = exhaustive
    ledger["official_shas"] = shas
    ledger["ovh1_height"] = chain.get("height")
    ledger["ovh1_last_hash"] = chain.get("last_hash")
    if json_contains_private_key(ledger):
        print(json.dumps({"ok": False, "error": "refusing_to_print_secret_material"}))
        return 2
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    latest = ROOT / "logs" / "289_aep_live.json"
    latest.write_text(ledger_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps(
        {
            "run_id": ledger["run_id"],
            "event_count": len(led.events),
            "tip": ledger["tip"][:16],
            "certify_mac_ssh": cert["profile_certification"],
            "execution_trace_complete": cert["execution_trace_complete"],
            "exhaustive": exhaustive["profile_certification"],
            "ssh": "FAIL",
            "certified_100": False,
            "thinking_recorded": False,
            "thinking_available_from_runtime": False,
            "thinking_received": False,
            "thinking_private_stored": False,
            "thinking_public_hash_recorded": False,
            "thinking_integrity_verified": False,
            "official_shas": shas,
            "height": chain.get("height"),
            "wrote": str(ledger_path),
        },
        indent=2,
    ))
    if cert["certified_100"] or exhaustive["execution_trace_complete"]:
        return 2
    if cert["profile_certification"] != "COMPLETE_FOR_PROFILE":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
