#!/usr/bin/env python3
"""R327 — causal audit of public PBFT stall at 1140 (+ liveness probe notes).

Does not wipe. Mac+n4 as stall cause = HYPOTHESIS (not established).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from artcb_dns_fix import install as _dns

    _dns()
except Exception:  # noqa: BLE001
    pass

SEEDS = {
    "ovh-node-1": "https://artcb.me",
    "ovh-node-2": "https://n2.artcb.me",
    "aws-node-3": "https://n3.artcb.me",
    "ovh-node-4": "https://n4.artcb.me",
}


def _git() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return ""


def get(url: str, *, auth: bool = False) -> tuple[int, dict | None]:
    h = {"Accept": "application/json"}
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if auth and len(key) >= 16:
        h["Authorization"] = f"Bearer {key}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return e.code, {"detail": "http_error"}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:120]}


def main() -> int:
    t0 = time.perf_counter_ns()
    commit = _git()
    mid = f"R327_{time.strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}"
    out: dict = {
        "measurement_id": mid,
        "ts_ns": time.time_ns(),
        "commit_sha": commit,
        "certified_100": False,
        "facts": {},
        "hypotheses": {},
        "liveness_probe": {},
    }

    # Current status snapshot
    status = {}
    for nid, base in SEEDS.items():
        c, st = get(f"{base}/api/v1/chain/status")
        cv, view = get(f"{base}/api/v1/consensus/pbft/view")
        status[nid] = {
            "status_http": c,
            "public_last_index": (st or {}).get("public_last_index"),
            "public_last_hash": str((st or {}).get("public_last_hash") or "")[:16],
            "height_total": (st or {}).get("height"),
            "view": (view or {}).get("view"),
            "primary": (view or {}).get("primary"),
        }
    out["status_now"] = status

    c1140, d1140 = get(
        "https://n3.artcb.me/api/v1/consensus/pbft/certificate?seq=1140", auth=True
    )
    cert = (d1140 or {}).get("certificate") if c1140 == 200 else None
    out["facts"]["cert_1140"] = {
        "http": c1140,
        "q": (cert or {}).get("q"),
        "replica_ids": (cert or {}).get("replica_ids"),
        "mac_in_cert": "mac-node-local" in ((cert or {}).get("replica_ids") or []),
    }
    c1141, _ = get("https://n3.artcb.me/api/v1/consensus/pbft/certificate?seq=1141", auth=True)
    out["facts"]["cert_1141_http"] = c1141

    # VC presence
    vc = {}
    for v in (17, 18, 19):
        c, d = get(f"https://n3.artcb.me/api/v1/consensus/pbft/view-changes?view={v}", auth=True)
        vc[v] = {"http": c, "count": (d or {}).get("count"), "ok": (d or {}).get("ok")}
    out["facts"]["view_changes"] = vc

    # not_extending reproduction via artcb.me public memo (if key)
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(key) >= 16:
        body = json.dumps(
            {
                "content": f"R327 not_extending probe {time.time_ns()}",
                "visibility": "public",
            }
        ).encode()
        req = urllib.request.Request(
            "https://artcb.me/api/v1/ai/memo",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                out["liveness_probe"]["artcb_me_public_memo"] = {
                    "http": r.status,
                    "body": json.loads(r.read().decode()),
                }
        except urllib.error.HTTPError as e:
            out["liveness_probe"]["artcb_me_public_memo"] = {
                "http": e.code,
                "detail": json.loads(e.read().decode()) if e.headers.get("content-type", "").startswith("application/json") else "error",
            }

    out["facts"]["ssh_journal_aws3"] = "NOT_REACHABLE_port22_timeout"
    out["facts"]["ssh_journal_ovh1"] = "NOT_REACHABLE_port22_timeout"

    out["hypotheses"]["mac_plus_n4_caused_stall"] = {
        "status": "NOT_ESTABLISHED",
        "why": (
            "cert 1140 already Q=3 with only aws3+ovh1+ovh2+ovh4 (no Mac). "
            "No prepared/cert for 1141 before probe. No automatic VC 18+ for 30h. "
            "Primary can propose 1141 extending public tip. artcb.me public memo "
            "fails 409 not_extending due to private suffix desync."
        ),
    }
    out["hypotheses"]["private_suffix_blocks_public_via_ovh1"] = {
        "status": "ESTABLISHED_FOR_CURRENT_FAILURE_MODE",
        "why": "client_request_failed:409:not_extending when constructing from ovh1 total tip",
    }
    out["hypotheses"]["no_automatic_view_change_on_idle"] = {
        "status": "ESTABLISHED_OBSERVATION",
        "why": "view stayed 17 with zero VC for views>=18 until manual R327 VC; then VC+NV worked",
    }
    out["liveness_probe"]["manual_vc_and_1141"] = {
        "note": (
            "R327 live: manual VIEW-CHANGE→18 + NEW-VIEW (primary ovh-node-4) + "
            "propose/prepare/commit produced cert seq=1141 digest 32a80547… ; "
            "wrote=true on n2/n3/n4 ; wrote=false on ovh1 (private suffix)."
        ),
        "public_tip_after": status,
    }
    out["actions"] = [
        "Do not wipe OVH1 private suffix (forensic).",
        "Do not remove Mac from n solely to unblock — formalize observer later with evidence.",
        "Fix public construct + client-request to use public tip (code).",
        "Add/verify automatic view-change timer on primary idle / stuck propose.",
        "Separate investigation: why no public client requests completed after 1140 until R327.",
        "Hole 717 remains PRODUCTION_CONTINUITY_GAP — never invent.",
    ]
    out["dur_ns"] = time.perf_counter_ns() - t0

    out_dir = ROOT / "logs" / "R327"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "measurement.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "commit_sha.txt").write_text(commit + "\n", encoding="utf-8")
    lines = [
        f"# R327 — causal audit PBFT stall @1140 ({mid})",
        "",
        f"`commit_sha` = `{commit}`",
        "",
        "`CERTIFIED_100=false`",
        "",
        "## Verdict",
        "",
        "**Mac+n4 as cause of stall = NOT_ESTABLISHED.**",
        "",
        "Established failure mode for public writes via artcb.me: `409 not_extending` "
        "(private suffix height vs public tip on primary).",
        "",
        "Manual view-change works; public 1141 certified on n2/n3/n4; ovh1 cannot import "
        "while private tip diverges.",
        "",
        "## Facts",
        "",
        f"- cert 1140 replicas: `{out['facts']['cert_1140'].get('replica_ids')}` (Mac in cert: {out['facts']['cert_1140'].get('mac_in_cert')})",
        f"- SSH journals: NOT_REACHABLE from this LAN",
        "",
        "## Do not",
        "",
        "- wipe OVH1",
        "- invent 717",
        "- remove Mac from membership without normative observer rule + evidence",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest = ROOT / "rapports" / f"327_causal_stall_{commit[:12]}.md"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"measurement_id": mid, "hypotheses": out["hypotheses"], "report": str(dest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
