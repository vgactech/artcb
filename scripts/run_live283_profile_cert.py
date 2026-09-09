#!/usr/bin/env python3
"""R283 live — environment-profile certification on the four official VMs.

Does not recast L3 as L4. Does not recast L2 as TPM. Does not recast N04.
Does not wipe. CERTIFIED_100 stays false unless every applicable requirement
of the detected profile is PASS (freshness + EK included for L3).
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

HTTP = l265.HTTP


def _row(status: str, **extra) -> dict:
    return {"status": status, "certified_100": False, **extra}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    health = {nid: l265._http("GET", f"{HTTP[nid]}/health", timeout=12) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (health[nid].get("git_sha") or "")[:40] for nid in OFFICIAL_COMPUTE_NODE_IDS}
    platforms = {
        nid: l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/platform-attest", timeout=40)
        for nid in OFFICIAL_COMPUTE_NODE_IDS
    }

    compact = {}
    recast = False
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        p = platforms[nid]
        splits = p.get("split_verdicts") if isinstance(p.get("split_verdicts"), dict) else {}
        q = (p.get("tpm") or {}).get("quote") if isinstance(p.get("tpm"), dict) else {}
        if not isinstance(q, dict):
            q = {}
        hw = p.get("hardware_tpm_attestation")
        if p.get("certified_hardware_identity") and hw != "TPM_HARDWARE_ATTESTED":
            recast = True
        if p.get("overall_platform_trust") == "TPM_ATTESTED" and hw in {"NOT_APPLICABLE", "NOT_AVAILABLE"}:
            recast = True
        if p.get("l4") == "PASS" and p.get("environment") in {"CLOUD_VM", "VM"}:
            recast = True
        if p.get("trust_level") == 4 and p.get("virt", {}).get("is_vm"):
            recast = True
        compact[nid] = {
            "sha": shas[nid],
            "environment": p.get("environment"),
            "environment_profile": p.get("environment_profile"),
            "maximum_supported_level": p.get("maximum_supported_level"),
            "attested_level": p.get("attested_level") or p.get("trust_level"),
            "class": p.get("platform_class"),
            "overall": p.get("overall_platform_trust"),
            "l3": p.get("l3") or splits.get("l3"),
            "l4": p.get("l4") or splits.get("l4"),
            "profile_certification": p.get("profile_certification") or splits.get("certification"),
            "profile_certified_100": p.get("profile_certified_100"),
            "hardware_tpm": hw,
            "crypto": splits.get("platform_crypto_attestation"),
            "certification": splits.get("certification"),
            "quote_verified": q.get("verified"),
            "quote_reason": q.get("reason"),
            "quote_kind": q.get("kind"),
            "quote_freshness": p.get("quote_freshness"),
            "ek_ak_provenance": p.get("ek_ak_provenance"),
            "quote_node_binding": p.get("quote_node_binding"),
            "certified_hardware": p.get("certified_hardware_identity"),
            "instance_id": ((p.get("identity") or {}).get("provider") or {}).get("instance_id")
            if isinstance(p.get("identity"), dict)
            else None,
        }

    ovh_ids = [nid for nid in OFFICIAL_COMPUTE_NODE_IDS if nid.startswith("ovh-")]
    aws = compact.get("aws-node-3") or {}
    ovh_ok = all(
        (compact[nid].get("environment") == "CLOUD_VM")
        and compact[nid].get("maximum_supported_level") == 2
        and compact[nid].get("attested_level") == 2
        and compact[nid].get("l4") == "NOT_APPLICABLE"
        and compact[nid].get("l3") == "NOT_REACHABLE"
        and compact[nid].get("profile_certification") == "PASS"
        and compact[nid].get("certified_hardware") is False
        for nid in ovh_ids
    )
    aws_ok = (
        aws.get("environment") == "CLOUD_VM"
        and aws.get("maximum_supported_level") == 3
        and aws.get("attested_level") == 3
        and aws.get("l3") == "PASS"
        and aws.get("l4") == "NOT_APPLICABLE"
        and aws.get("quote_verified") is True
        and aws.get("certified_hardware") is False
        and aws.get("profile_certification") in {"PARTIAL", "PASS"}
        and aws.get("profile_certified_100") is not True
    )
    l4_na = all(c.get("l4") == "NOT_APPLICABLE" for c in compact.values())
    # FAIL is allowed only for recast or identity mismatch — none of the four
    # official nodes should FAIL just because L4 is inapplicable.
    fail_for_missing_l4 = any(c.get("profile_certification") == "FAIL" for c in compact.values())
    honesty = "PASS"
    if recast:
        honesty = "FAIL"
    if any(c.get("certified_hardware") for c in compact.values()):
        honesty = "FAIL"
    if any(c.get("l4") == "PASS" for c in compact.values()):
        honesty = "FAIL"

    results = {
        "policy_environment_first": _row("PASS" if ovh_ok and aws_ok and l4_na else "FAIL", ovh_ok=ovh_ok, aws_ok=aws_ok),
        "l4_not_applicable_on_vms": _row("PASS" if l4_na else "FAIL", nodes={nid: compact[nid].get("l4") for nid in compact}),
        "ovh_l2_profile": _row("PASS" if ovh_ok else "FAIL"),
        "aws3_l3_not_l4": _row("PASS" if aws_ok else "FAIL", aws=aws),
        "no_fail_for_inapplicable_l4": _row("PASS" if not fail_for_missing_l4 else "FAIL"),
        "profile_certified_100": _row("FAIL", nodes={nid: compact[nid].get("profile_certified_100") for nid in compact}),
        "n04_50": _row("FAIL", note="kept from R272 — last, not replayed"),
        "c04_thousands": _row("NOT_PROVEN"),
        "ek_manufacturer": _row("NOT_PROVEN"),
        "honesty_guard": _row(honesty),
        "certified_100": False,
        "production_ready": False,
    }

    artefact = write_campaign(
        ROOT,
        campaign_id=f"283_{stamp}",
        code_sha=shas.get("ovh-node-1", ""),
        runner="scripts/run_live283_profile_cert.py",
        environment={"shas": shas},
        nodes={nid: {"health": health[nid], "platform": compact[nid]} for nid in OFFICIAL_COMPUTE_NODE_IDS},
        results=results,
        extra_manifest={"compact": compact, "recast": recast},
    )
    out = {
        "stamp": stamp,
        "shas": shas,
        "results": {k: (v.get("status") if isinstance(v, dict) else v) for k, v in results.items()},
        "compact": compact,
        "artefact": artefact.get("root") if isinstance(artefact, dict) else None,
        "certified_100": False,
        "recast": recast,
    }
    dest = ROOT / "logs" / f"283_profile_cert_{stamp}.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    policy_pass = results["policy_environment_first"]["status"] == "PASS"
    honesty_pass = results["honesty_guard"]["status"] == "PASS"
    return 0 if policy_pass and honesty_pass and not recast else 1


if __name__ == "__main__":
    raise SystemExit(main())
