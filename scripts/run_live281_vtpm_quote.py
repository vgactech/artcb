#!/usr/bin/env python3
"""R281 live — vTPM/TPM quote on the four official VMs.

Does not recast cloud identity as a quote.
Does not recast guest swtpm as hypervisor vTPM.
Does not recast N04. Does not wipe. CERTIFIED_100 stays false.
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
PROBE = (
    "echo TPM0=$(test -e /dev/tpm0 && echo yes || echo no); "
    "echo TPMRM=$(test -e /dev/tpmrm0 && echo yes || echo no); "
    "echo NSM=$(test -e /dev/nsm && echo yes || echo no); "
    "echo VIRT=$(systemd-detect-virt 2>/dev/null); "
    "echo TOOLS=$(command -v tpm2_quote >/dev/null && echo yes || echo no); "
    "lsmod | grep -i tpm || echo NO_TPM_MOD"
)


def _row(status: str, **extra) -> dict:
    return {"status": status, "certified_100": False, **extra}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    health = {nid: l265._http("GET", f"{HTTP[nid]}/health", timeout=12) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (health[nid].get("git_sha") or "")[:40] for nid in OFFICIAL_COMPUTE_NODE_IDS}
    probes = {}
    platforms = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        probes[nid] = l265._ssh(nid, PROBE, timeout=25)
        platforms[nid] = l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/platform-attest", timeout=25)

    compact = {}
    recast = False
    fake_l3 = False
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        p = platforms[nid]
        splits = p.get("split_verdicts") if isinstance(p.get("split_verdicts"), dict) else {}
        q = (p.get("tpm") or {}).get("quote") if isinstance(p.get("tpm"), dict) else {}
        if not isinstance(q, dict):
            q = {}
        if p.get("overall_platform_trust") in {"TPM_ATTESTED", "VTPM_ATTESTED"} and q.get("reason") == "DEVICE_ABSENT":
            recast = True
            fake_l3 = True
        if p.get("certified_hardware_identity") and p.get("hardware_tpm_attestation") != "TPM_HARDWARE_ATTESTED":
            recast = True
        compact[nid] = {
            "sha": shas[nid],
            "probe_stdout": (probes[nid].get("stdout") or "")[:400],
            "class": p.get("platform_class"),
            "trust_level": p.get("trust_level"),
            "overall": p.get("overall_platform_trust"),
            "split": splits,
            "quote_reason": q.get("reason"),
            "quote_verified": q.get("verified"),
            "quote_kind": q.get("kind"),
            "crypto_verified": p.get("attestation_crypto_verified"),
            "certified_hardware": p.get("certified_hardware_identity"),
        }

    device_absent = all(c.get("quote_reason") == "DEVICE_ABSENT" for c in compact.values())
    crypto_all_np = all((c.get("split") or {}).get("platform_crypto_attestation") == "NOT_PROVEN" for c in compact.values())
    cert_fail = all((c.get("split") or {}).get("certification") == "FAIL" for c in compact.values())
    results = {
        "hypervisor_vtpm_device": _row("NOT_AVAILABLE" if device_absent else "MEASURED", nodes=compact),
        "vtpm_quote": _row("NOT_PROVEN" if device_absent else ("PASS" if any(c.get("quote_verified") for c in compact.values()) else "NOT_PROVEN")),
        "platform_crypto_attestation": _row("NOT_PROVEN" if crypto_all_np else "FAIL"),
        "hardware_tpm": _row("NOT_AVAILABLE"),
        "certification": _row("FAIL" if cert_fail else "FAIL"),
        "honesty_guard": _row("FAIL" if recast or fake_l3 else "PASS", recast=recast, fake_l3=fake_l3),
        "n04_50": _row("FAIL", note="deferred — last after other necessary proofs"),
        "c04_thousands": _row("NOT_PROVEN"),
        "ci_github": _row("NOT_PROVEN", note="tests.yml is workflow_dispatch only; combined status empty is not CI PASS"),
        "certified_100": False,
        "production_ready": False,
        "note": (
            "Current four VMs have no /dev/tpm0. Quote path is implemented and "
            "fail-closed. Guest swtpm is not claimed as vTPM. Bare-metal L4 is "
            "for user/bare-metal servers, not invented here."
        ),
    }
    artefact = write_campaign(
        ROOT,
        campaign_id=f"281_{stamp}",
        code_sha=shas.get("ovh-node-1", ""),
        runner="scripts/run_live281_vtpm_quote.py",
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
    dest = ROOT / "logs" / f"281_vtpm_quote_{stamp}.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if results["honesty_guard"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
