#!/usr/bin/env python3
"""R329 — four-layer audit matrix + live tip/watchdog probe.

Does not invent architecture. Matrix cells marked MEASURED / CODE / OPEN.
CERTIFIED_100 always false until Issue #86 4-layer + auto-VC + restart live.
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


def get(url: str) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return e.code, {"detail": "http_error"}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:120]}


def code_matrix() -> list[dict]:
    """Data-flow matrix deduced from src/artcb/authz/domains.py + chain split."""
    try:
        from src.artcb.authz.domains import REPLICATION_MATRIX
    except ImportError:
        from artcb.authz.domains import REPLICATION_MATRIX  # type: ignore

    rows = []
    for key, meta in REPLICATION_MATRIX.items():
        rows.append(
            {
                "object": key,
                "layer": meta.get("layer"),
                "replication": meta.get("replication"),
                "content": meta.get("content"),
                "source": "src/artcb/authz/domains.py:REPLICATION_MATRIX",
                "status": "CODE",
            }
        )
    rows.append(
        {
            "object": "CHAIN_VISIBILITY",
            "layer": "note",
            "replication": "n/a",
            "content": "append_block accepts any string; HTTP /store allows public|private|group only; ORG is NOT a chain visibility",
            "source": "manager.py + routes.py + repo_scope.py",
            "status": "CODE",
        }
    )
    rows.append(
        {
            "object": "R328_LEDGERS",
            "layer": "storage",
            "replication": "public book vs private book",
            "content": "visibility=public → chain/public/blocks.jsonl; else (private|group|…) → chain/private/blocks.jsonl; legacy forensic",
            "source": "split_ledger.py + manager.py",
            "status": "CODE",
        }
    )
    rows.append(
        {
            "object": "ORG_ACL_IMPLICIT",
            "layer": "org",
            "replication": "n/a",
            "content": "No implicit org-membership READ on chain blocks; organization_id is ResourceIndex sidecar",
            "source": "authz/engine.py",
            "status": "GAP",
        }
    )
    return rows


def main() -> int:
    t0 = time.perf_counter_ns()
    commit = _git()
    mid = f"R329_{time.strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}"
    out: dict = {
        "measurement_id": mid,
        "ts_ns": time.time_ns(),
        "commit_sha": commit,
        "certified_100": False,
        "issue": 86,
        "scope": "PUBLIC→ORG→GROUP→PRIVATE audit + open R328 E/H/J",
        "vocabulary": {
            "chain_visibility": ["public", "private", "group"],
            "logical_domain": ["global", "org", "group", "user/resource/private"],
            "note": "ORG is domain+commitment, not a fourth ChainBlock.visibility value",
        },
        "flow_matrix": code_matrix(),
        "nodes": {},
        "criteria": {},
        "open": {
            "E_H_auto_view_change_live": "NOT_PROVEN",
            "J_restart_live_node": "NOT_PROVEN_ssh_timeout",
            "org_multi_tenant_acl_by_org_id": "GAP_policy_only",
            "group_third_ledger": "NOT_APPLICABLE_r328_maps_group_to_private_book",
        },
    }

    tips = []
    for nid, base in SEEDS.items():
        ch, health = get(f"{base}/api/v1/health")
        cs, st = get(f"{base}/api/v1/chain/status")
        cw, wd = get(f"{base}/api/v1/consensus/pbft/public-tip-watchdog")
        row = {
            "health_http": ch,
            "git_sha": str((health or {}).get("git_sha") or "")[:40],
            "status_http": cs,
            "public_last_index": (st or {}).get("public_last_index"),
            "public_last_hash": str((st or {}).get("public_last_hash") or "")[:16],
            "private_suffix_lines": (st or {}).get("private_suffix_lines"),
            "private_height": (st or {}).get("private_height"),
            "ledger_mode": (st or {}).get("ledger_mode"),
            "watchdog_hypothesis": (wd or {}).get("hypothesis"),
            "watchdog_pending": (wd or {}).get("pending_prepares"),
        }
        out["nodes"][nid] = row
        if row["public_last_index"] is not None:
            tips.append(int(row["public_last_index"]))

    out["criteria"]["M_sha_aligned"] = len({n["git_sha"][:12] for n in out["nodes"].values() if n.get("git_sha")}) == 1
    out["criteria"]["I_public_tip_equal"] = len(tips) == 4 and len(set(tips)) == 1
    out["criteria"]["K_split_ledger"] = all(out["nodes"][n].get("ledger_mode") == "split_v1" for n in SEEDS)
    out["criteria"]["O_certified_100"] = False
    out["criteria"]["four_layer_certified"] = False
    out["public_tips"] = tips
    out["dur_ns"] = time.perf_counter_ns() - t0

    out_dir = ROOT / "logs" / "R329"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "measurement.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    matrix_path = out_dir / "flow_matrix.json"
    matrix_path.write_text(json.dumps(out["flow_matrix"], indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "criteria": out["criteria"], "tips": tips, "open": out["open"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
