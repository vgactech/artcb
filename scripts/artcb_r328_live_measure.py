#!/usr/bin/env python3
"""R328 — live measure: split ledger deploy, ovh1 public import, tip×4, watchdog.

Never wipe. Never invent 717. CERTIFIED_100 stays false unless all criteria pass.
"""

from __future__ import annotations

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


def get(url: str, *, auth: bool = False, method: str = "GET", body: dict | None = None) -> tuple[int, dict | None]:
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if auth and len(key) >= 16:
        h["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    try:
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return e.code, {"detail": "http_error"}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:160]}


def main() -> int:
    t0 = time.perf_counter_ns()
    commit = _git()
    mid = f"R328_{time.strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}"
    out: dict = {
        "measurement_id": mid,
        "ts_ns": time.time_ns(),
        "commit_sha": commit,
        "certified_100": False,
        "criteria": {},
        "nodes": {},
        "watchdog": {},
        "import_1141": {},
    }

    tips = []
    for nid, base in SEEDS.items():
        c_h, health = get(f"{base}/api/v1/health")
        c_s, st = get(f"{base}/api/v1/chain/status")
        c_w, wd = get(f"{base}/api/v1/consensus/pbft/public-tip-watchdog")
        c_v, view = get(f"{base}/api/v1/consensus/pbft/view")
        row = {
            "health_http": c_h,
            "git_sha": str((health or {}).get("git_sha") or "")[:40],
            "status_http": c_s,
            "public_last_index": (st or {}).get("public_last_index"),
            "public_last_hash": str((st or {}).get("public_last_hash") or "")[:16],
            "private_suffix_lines": (st or {}).get("private_suffix_lines"),
            "ledger_mode": (st or {}).get("ledger_mode"),
            "height_total": (st or {}).get("height"),
            "view": (view or {}).get("view"),
            "primary": (view or {}).get("primary"),
            "watchdog_http": c_w,
            "watchdog_hypothesis": (wd or {}).get("hypothesis"),
            "watchdog_pending": (wd or {}).get("pending_prepares"),
            "watchdog_age_sec": (wd or {}).get("age_sec"),
        }
        out["nodes"][nid] = row
        if row["public_last_index"] is not None:
            tips.append(int(row["public_last_index"]))
        out["watchdog"][nid] = {
            "http": c_w,
            "hypothesis": (wd or {}).get("hypothesis"),
            "pending": (wd or {}).get("pending_prepares"),
        }

    # Try to fetch cert+block 1141 from n3 and install on ovh1 if lagging
    c_cert, d_cert = get(
        "https://n3.artcb.me/api/v1/consensus/pbft/certificate?seq=1141", auth=True
    )
    cert = (d_cert or {}).get("certificate") if c_cert == 200 else None
    c_blk, d_blk = get("https://n3.artcb.me/api/v1/chain/block/1141")
    block = d_blk if c_blk == 200 and isinstance(d_blk, dict) else None
    # API nests under "block"
    if block and isinstance(block.get("block"), dict):
        block = block["block"]
    if not (isinstance(block, dict) and block.get("hash")):
        block = None
    out["import_1141"]["cert_http"] = c_cert
    out["import_1141"]["block_http"] = c_blk
    if cert and block:
        ic, ib = get(
            "https://artcb.me/api/v1/consensus/pbft/certificate",
            auth=True,
            method="POST",
            body={"certificate": cert, "block": block},
        )
        out["import_1141"]["ovh1_install_http"] = ic
        out["import_1141"]["ovh1_install_body"] = {
            k: ib.get(k) for k in ("ok", "wrote", "reason", "detail") if isinstance(ib, dict)
        }
        # refresh ovh1 status
        _, st1 = get("https://artcb.me/api/v1/chain/status")
        out["import_1141"]["ovh1_public_after"] = (st1 or {}).get("public_last_index")
        out["import_1141"]["ovh1_private_suffix_after"] = (st1 or {}).get("private_suffix_lines")

    shas = {n: out["nodes"][n]["git_sha"] for n in SEEDS}
    out["criteria"]["M_sha_live_eq_commit"] = all(
        (shas[n] or "").startswith(commit[:12]) or shas[n] == commit for n in SEEDS
    ) and len({s[:12] for s in shas.values() if s}) == 1
    out["criteria"]["I_public_tip_4_of_4"] = len(tips) == 4 and len(set(tips)) == 1
    out["criteria"]["K_ledger_mode_split"] = any(
        out["nodes"][n].get("ledger_mode") == "split_v1" for n in SEEDS
    )
    ovh_priv = out["nodes"]["ovh-node-1"].get("private_suffix_lines") or 0
    ovh_pub = out["nodes"]["ovh-node-1"].get("public_last_index")
    peer_pub = out["nodes"]["ovh-node-2"].get("public_last_index")
    out["criteria"]["C_ovh1_import_with_private_suffix"] = bool(
        ovh_priv and ovh_priv > 0 and ovh_pub is not None and peer_pub is not None and ovh_pub == peer_pub
    )
    out["criteria"]["O_certified_100"] = False
    out["dur_ns"] = time.perf_counter_ns() - t0

    out_dir = ROOT / "logs" / "R328"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "measurement.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "criteria": out["criteria"], "tips": tips}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
