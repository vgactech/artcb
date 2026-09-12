#!/usr/bin/env python3
"""R330-A — live probe: ORG/GROUP commitments visible as public projections ×4.

Does NOT claim body replication. Measures:
  - GET /authz/orgs projection on each seed (hashes only)
  - public tip equality
  - ledger_mode split_v1
authorized_nodes ≠ body copied (documented OPEN).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
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


def get(url: str) -> tuple[int, dict | list | None]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=30
        ) as r:
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
    out: dict = {
        "measurement_id": f"R330A_{time.strftime('%Y%m%dT%H%M%SZ')}",
        "ts_ns": time.time_ns(),
        "commit_sha": _git(),
        "certified_100": False,
        "four_layer_certified": False,
        "issues_still_open": ["#77", "#86"],
        "nodes": {},
        "criteria": {},
        "open": {
            "org_body_multi_node_replication": "NOT_PROVEN",
            "authorized_nodes_implies_copy": False,
            "auto_view_change": "NOT_PROVEN",
            "restart_live": "NOT_PROVEN",
        },
    }
    tips = []
    org_hash_sets = []
    for nid, base in SEEDS.items():
        ch, health = get(f"{base}/api/v1/health")
        cs, st = get(f"{base}/api/v1/chain/status")
        co, orgs = get(f"{base}/api/v1/authz/orgs")
        org_list = []
        if isinstance(orgs, dict):
            org_list = list(orgs.get("orgs") or [])
        hashes = sorted(
            {
                str(o.get("content_hash") or "")[:16]
                for o in org_list
                if isinstance(o, dict) and o.get("content_hash")
            }
        )
        # Ensure projection never leaks founder
        leak = any("founder_address" in (o or {}) for o in org_list if isinstance(o, dict))
        row = {
            "health_http": ch,
            "git_sha": str((health or {}).get("git_sha") or "")[:40] if isinstance(health, dict) else "",
            "public_last_index": (st or {}).get("public_last_index") if isinstance(st, dict) else None,
            "public_last_hash": str((st or {}).get("public_last_hash") or "")[:16] if isinstance(st, dict) else "",
            "private_suffix_lines": (st or {}).get("private_suffix_lines") if isinstance(st, dict) else None,
            "ledger_mode": (st or {}).get("ledger_mode") if isinstance(st, dict) else None,
            "orgs_http": co,
            "org_count": len(org_list),
            "org_hash_prefix_set": hashes,
            "org_projection_leak_founder": leak,
            "sample_projection": (org_list[0].get("projection") if org_list else None),
        }
        out["nodes"][nid] = row
        if row["public_last_index"] is not None:
            tips.append(int(row["public_last_index"]))
        org_hash_sets.append(tuple(hashes))

    out["criteria"]["I_public_tip_equal"] = len(tips) == 4 and len(set(tips)) == 1
    out["criteria"]["K_split"] = all(out["nodes"][n].get("ledger_mode") == "split_v1" for n in SEEDS)
    out["criteria"]["org_list_http_ok"] = all(out["nodes"][n].get("orgs_http") == 200 for n in SEEDS)
    out["criteria"]["org_no_founder_leak"] = all(
        not out["nodes"][n].get("org_projection_leak_founder") for n in SEEDS
    )
    # Hash sets may differ if orgs were never anchored on that node — document honesty
    out["criteria"]["org_commitment_sets_equal"] = len(set(org_hash_sets)) == 1
    out["criteria"]["org_body_replicated"] = False  # never claim from this probe
    out["criteria"]["O_certified_100"] = False
    out["public_tips"] = tips
    out["dur_ns"] = time.perf_counter_ns() - t0

    d = ROOT / "logs" / "R330"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "measurement.json"
    # merge with height audit if present
    height_path = d / "height_audit.json"
    if height_path.is_file():
        out["height_audit_summary"] = json.loads(height_path.read_text()).get("summary")
        out["height_risk_count"] = len(json.loads(height_path.read_text()).get("risk_open") or [])
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "criteria": out["criteria"], "tips": tips}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
