#!/usr/bin/env python3
"""R284 live — classification honesty + raw evidence hashes.

Does not recast swtpm as L3. Does not recast UNKNOWN as BARE_METAL.
Does not recast PRE_R273 K1→Node2 GAP as PASS. Does not recast N04.
Does not wipe. CERTIFIED_100 stays false.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.consensus.campaign_artifacts import write_campaign  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402
from artcb.trace.agent_run import AgentRunLedger, sha256_json  # noqa: E402

HTTP = l265.HTTP
PROMPT_HASH_PATH = Path("/tmp/artcb_turn_prompt.txt")


def _row(status: str, **extra) -> dict:
    return {"status": status, "certified_100": False, **extra}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    prompt_hash = ""
    if PROMPT_HASH_PATH.is_file():
        prompt_hash = __import__("hashlib").sha256(PROMPT_HASH_PATH.read_bytes()).hexdigest()
    health = {nid: l265._http("GET", f"{HTTP[nid]}/health", timeout=12) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (health[nid].get("git_sha") or "")[:40] for nid in OFFICIAL_COMPUTE_NODE_IDS}
    platforms = {
        nid: l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/platform-attest", timeout=40)
        for nid in OFFICIAL_COMPUTE_NODE_IDS
    }
    led = AgentRunLedger(
        run_id=f"AR-284-{stamp}",
        agent_id="cursor-cloud-agent",
        prompt_hash=prompt_hash,
        code_sha=shas.get("ovh-node-1", ""),
    )
    led.add("INPUT_RECEIVED", status="PASS", input_hash=prompt_hash or "unset")
    compact = {}
    recast = False
    raw_hashes = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        p = platforms[nid]
        raw_hashes[nid] = sha256_json(p)
        led.add(
            "LIVE_VERIFICATION",
            status="PASS" if p.get("environment") else "FAIL",
            output_hash=raw_hashes[nid],
            detail={"node_id": nid, "actor": "SYSTEM_ACTION"},
            actor="SYSTEM_ACTION",
        )
        if p.get("certified_hardware_identity"):
            recast = True
        if p.get("environment") == "BARE_METAL":
            recast = True
        if p.get("tpm_kind") == "SOFTWARE_TPM" and p.get("trust_level") == 3:
            recast = True
        compact[nid] = {
            "sha": shas[nid],
            "raw_hash": raw_hashes[nid],
            "environment": p.get("environment"),
            "environment_certainty": p.get("environment_certainty"),
            "environment_profile": p.get("environment_profile"),
            "tpm_kind": p.get("tpm_kind"),
            "maximum_theoretical_level": p.get("maximum_theoretical_level"),
            "maximum_verified_level": p.get("maximum_verified_level"),
            "attested_level": p.get("attested_level") or p.get("trust_level"),
            "l3": p.get("l3"),
            "l4": p.get("l4"),
            "profile_certification": p.get("profile_certification"),
            "profile_certified_100": p.get("profile_certified_100"),
            "missing_requirements": p.get("missing_requirements"),
            "freshness_kind": p.get("freshness_kind"),
            "ek_provenance_verified": p.get("ek_provenance_verified"),
            "quote_signature_verified": p.get("quote_signature_verified"),
            "overall_precise": p.get("overall_platform_trust_precise"),
            "policy_hash": p.get("policy_hash"),
            "certified_hardware": p.get("certified_hardware_identity"),
        }

    ovh_ok = all(
        compact[nid].get("environment") == "CLOUD_VM"
        and compact[nid].get("l4") == "NOT_APPLICABLE"
        and compact[nid].get("tpm_kind") in {None, "ABSENT", ""}
        and compact[nid].get("profile_certification") == "PASS"
        and compact[nid].get("overall_precise") == "CLOUD_IDENTITY_OBSERVED"
        for nid in OFFICIAL_COMPUTE_NODE_IDS
        if nid.startswith("ovh-")
    )
    aws = compact.get("aws-node-3") or {}
    aws_ok = (
        aws.get("environment") == "CLOUD_VM"
        and aws.get("tpm_kind") == "NITROTPM"
        and aws.get("attested_level") == 3
        and aws.get("maximum_verified_level") == 3
        and aws.get("l4") == "NOT_APPLICABLE"
        and aws.get("profile_certification") == "PARTIAL"
        and aws.get("certified_hardware") is False
        and aws.get("freshness_kind") in {"LOCAL_GENERATED", "ABSENT"}
    )
    honesty = "FAIL" if recast else "PASS"
    led.add("FINAL_VERDICT", status=honesty, detail={"ovh_ok": ovh_ok, "aws_ok": aws_ok, "recast": recast})
    ledger_path = ROOT / "logs" / f"284_agent_run_{stamp}.json"
    ledger = led.write(ledger_path)

    results = {
        "unknown_not_bare_metal": _row("PASS" if ovh_ok and aws_ok else "FAIL"),
        "aws3_nitrotpm_not_swtpm": _row("PASS" if aws_ok else "FAIL", aws=aws),
        "ovh_l2_observed": _row("PASS" if ovh_ok else "FAIL"),
        "pre_r273_gap": _row("GAP", note="K1→Node2 before 41c9e1dd remains GAP, not retroactive PASS"),
        "n04_50": _row("FAIL", note="last — not replayed"),
        "c04_thousands": _row("NOT_PROVEN"),
        "verifier_challenge": _row("NOT_PROVEN"),
        "ek_manufacturer": _row("NOT_PROVEN"),
        "mac_rfc1918": _row("NOT_REACHABLE", note="10.234.49.2 not reachable from this cloud VM"),
        "honesty_guard": _row(honesty),
        "certified_100": False,
        "production_ready": False,
    }
    artefact = write_campaign(
        ROOT,
        campaign_id=f"284_{stamp}",
        code_sha=shas.get("ovh-node-1", ""),
        runner="scripts/run_live284_classify.py",
        environment={"shas": shas, "prompt_hash": prompt_hash, "policy_hash": ledger.get("policy_hash")},
        nodes={nid: {"health": health[nid], "platform": compact[nid], "raw_hash": raw_hashes[nid]} for nid in OFFICIAL_COMPUTE_NODE_IDS},
        results=results,
        extra_manifest={"compact": compact, "ledger_tip": ledger.get("tip")},
    )
    out = {
        "stamp": stamp,
        "shas": shas,
        "results": {k: (v.get("status") if isinstance(v, dict) else v) for k, v in results.items()},
        "compact": compact,
        "artefact": artefact.get("root") if isinstance(artefact, dict) else None,
        "ledger": str(ledger_path),
        "ledger_tip": ledger.get("tip"),
        "certified_100": False,
        "recast": recast,
    }
    dest = ROOT / "logs" / f"284_classify_{stamp}.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if honesty == "PASS" and ovh_ok and aws_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
