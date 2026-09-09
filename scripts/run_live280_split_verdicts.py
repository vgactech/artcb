#!/usr/bin/env python3
"""R280 — split platform verdicts. observed PASS ≠ crypto PASS ≠ CERTIFIED_100.

Does not recast CLOUD as TPM. Does not recast NOT_PROVEN as PASS.
Does not wipe the book.
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
        nid: l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/platform-attest", timeout=25)
        for nid in OFFICIAL_COMPUTE_NODE_IDS
    }
    compact = {}
    recast = False
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        p = platforms[nid]
        splits = p.get("split_verdicts") if isinstance(p.get("split_verdicts"), dict) else {}
        hw = p.get("hardware_tpm_attestation")
        overall = p.get("overall_platform_trust")
        if overall == "TPM_ATTESTED" and hw == "NOT_AVAILABLE":
            recast = True
        if p.get("certified_hardware_identity") and hw != "TPM_HARDWARE_ATTESTED":
            recast = True
        pin = ((p.get("aws_imds") or {}) if isinstance(p.get("aws_imds"), dict) else {}).get("rsa2048_pin")
        compact[nid] = {
            "sha": shas[nid],
            "class": p.get("platform_class"),
            "overall": overall,
            "trust_level": p.get("trust_level"),
            "split": splits,
            "crypto_verified": p.get("attestation_crypto_verified"),
            "certified_hardware": p.get("certified_hardware_identity"),
            "rsa2048_pin": pin,
            "instance_id": ((p.get("identity") or {}).get("provider") or {}).get("instance_id")
            if isinstance(p.get("identity"), dict)
            else None,
        }

    observed_ok = (
        all((c.get("split") or {}).get("platform_level_observed") == "PASS" for c in compact.values())
        and not recast
    )
    crypto_wrong_pass = any((c.get("split") or {}).get("platform_crypto_attestation") == "PASS" for c in compact.values())
    cert_wrong_pass = any((c.get("split") or {}).get("certification") == "PASS" for c in compact.values())
    results = {
        "platform_level_observed": _row("PASS" if observed_ok else "FAIL", recast=recast, nodes=compact),
        "platform_crypto_attestation": _row(
            "NOT_PROVEN",
            leaked_pass=crypto_wrong_pass,
            note="TPM/vTPM quote required; IID pin is not this field",
        ),
        "hardware_tpm": _row("NOT_AVAILABLE"),
        "certification": _row("FAIL", leaked_pass=cert_wrong_pass),
        "aws_iid_rsa2048_pin": _row(
            "MEASURED",
            nodes={nid: compact[nid].get("rsa2048_pin") for nid in compact},
            note="PASS here would be AWS pin only — still not platform_crypto_attestation",
        ),
        "n04_50": _row("FAIL", note="kept from R272/R278"),
        "c04_thousands": _row("NOT_PROVEN"),
        "tpm_quote": _row("NOT_PROVEN"),
        "certified_100": False,
        "production_ready": False,
    }
    if crypto_wrong_pass or cert_wrong_pass or recast:
        results["honesty_guard"] = _row("FAIL")
    else:
        results["honesty_guard"] = _row("PASS")

    artefact = write_campaign(
        ROOT,
        campaign_id=f"280_{stamp}",
        code_sha=shas.get("ovh-node-1", ""),
        runner="scripts/run_live280_split_verdicts.py",
        environment={"shas": shas},
        nodes={nid: {"health": health[nid], "platform": compact[nid]} for nid in OFFICIAL_COMPUTE_NODE_IDS},
        results=results,
        extra_manifest={"compact": compact},
    )
    out = {
        "stamp": stamp,
        "shas": shas,
        "results": {k: (v.get("status") if isinstance(v, dict) else v) for k, v in results.items()},
        "compact": compact,
        "artefact": artefact.get("root") if isinstance(artefact, dict) else None,
        "certified_100": False,
    }
    dest = ROOT / "logs" / f"280_split_verdicts_{stamp}.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if results["honesty_guard"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
