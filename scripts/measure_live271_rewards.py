#!/usr/bin/env python3
"""Dump live block_reward from genesis on ovh-node-1 (no wipe, no secrets)."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_live265_pbft_e2e as l265  # noqa: E402

CODE = r"""
import json
from collections import Counter
from datetime import datetime
p="/home/ubuntu/artcb/data/chain/blocks.jsonl"
rows=[]
with open(p) as f:
    for line in f:
        line=line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
sats=[int(r.get("block_reward") or 0) for r in rows]
def parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z","+00:00"))
    except Exception:
        return None
out={"n": len(rows), "first_index": rows[0].get("index") if rows else None, "last_index": rows[-1].get("index") if rows else None,
     "sum_satoshi": sum(sats), "sum_artcb": sum(sats)/1e8, "min_sat": min(sats) if sats else None, "max_sat": max(sats) if sats else None,
     "unique_rewards": len(set(sats)), "zeros": sats.count(0), "genesis_50": sats.count(5_000_000_000),
     "fast_1s_floor": sats.count(8_333_333), "top": Counter(sats).most_common(16), "series": []}
prev=None
for r in rows:
    dt=parse(r.get("timestamp"))
    dts=(dt-prev).total_seconds() if dt and prev else None
    out["series"].append({"index": r.get("index"), "reward_satoshi": int(r.get("block_reward") or 0),
        "reward_artcb": int(r.get("block_reward") or 0)/1e8, "dt_s": dts, "visibility": r.get("visibility"),
        "pbft": bool(r.get("pbft_cert")), "ts": str(r.get("timestamp") or "")[:19]})
    prev=dt
    print(json.dumps(out), file=open("/tmp/271_rewards.json","w"))
    print("WROTE", out["n"], out["sum_artcb"])
"""


def main() -> int:
    row = l265._ssh("ovh-node-1", "python3 -c " + shlex.quote(CODE), timeout=120)
    scp = subprocess.run(
        ["scp", "-i", str(Path.home() / ".ssh" / "artcb_ovh_deploy"), "-o", "StrictHostKeyChecking=no",
         "ubuntu@152.228.144.34:/tmp/271_rewards.json", str(ROOT / "logs" / "271_rewards_live.json")],
        capture_output=True, text=True, timeout=60, check=False,
    )
    dest = ROOT / "logs" / "271_rewards_live.json"
    data = {}
    if dest.is_file():
        data = json.loads(dest.read_text(encoding="utf-8"))
    data["ssh_rc"] = row.get("returncode")
    data["scp_rc"] = scp.returncode
    dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: data.get(k) for k in ("n", "sum_artcb", "min_sat", "max_sat", "zeros", "genesis_50", "fast_1s_floor", "top")}, indent=2))
    return 0 if data.get("n") else 1


if __name__ == "__main__":
    raise SystemExit(main())
