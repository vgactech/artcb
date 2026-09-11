#!/usr/bin/env python3
"""R324 — inventory blockchain gap after 716 (never invent blocks).

Scans public /chain/block/{i} on seeds for presence of 717 and any child of tip_716.
"""

from __future__ import annotations

import json
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

TIP716 = "f79f6a1a71896e619f6d66cc998bbc918b2eb1d4649f3dcad2d6349cb6c9dd37"
SEEDS = (
    "https://artcb.me",
    "https://n2.artcb.me",
    "https://n3.artcb.me",
    "https://n4.artcb.me",
)


def _get(url: str) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=25
        ) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__}


def main() -> int:
    t0 = time.perf_counter_ns()
    out: dict = {"ts_ns": time.time_ns(), "tip716_hash": TIP716, "seeds": {}, "certified_100": False}
    for base in SEEDS:
        row: dict = {"base": base}
        code, health = _get(f"{base}/health")
        row["health_http"] = code
        if isinstance(health, dict):
            row["git_sha"] = str(health.get("git_sha") or "")[:12]
            row["height"] = health.get("height") or health.get("chain_height")
        for idx in (716, 717, 1073, 1074, 1140):
            c, body = _get(f"{base}/api/v1/chain/block/{idx}")
            blk = (body or {}).get("block") if isinstance(body, dict) else None
            if c == 200 and isinstance(blk, dict):
                row[f"block_{idx}"] = {
                    "hash": str(blk.get("hash") or "")[:16],
                    "prev": str(blk.get("prev_hash") or "")[:16],
                    "prev_is_tip716": str(blk.get("prev_hash") or "") == TIP716,
                }
            else:
                row[f"block_{idx}"] = {"http": c}
        # sample a few indices in the hole for presence
        hole_hits = []
        for idx in range(717, 730):
            c, _ = _get(f"{base}/api/v1/chain/block/{idx}")
            if c == 200:
                hole_hits.append(idx)
        row["present_in_717_729"] = hole_hits
        out["seeds"][base] = row
    out["717_exists_anywhere"] = any(
        isinstance(r.get("block_717"), dict) and "hash" in r["block_717"]
        for r in out["seeds"].values()
    )
    out["child_of_tip716_found"] = any(
        (r.get(f"block_{i}") or {}).get("prev_is_tip716")
        for r in out["seeds"].values()
        for i in (717, 1073, 1074, 1140)
    )
    out["verdict"] = (
        "HOLE_CONFIRMED_NO_CHILD"
        if not out["717_exists_anywhere"] and not out["child_of_tip716_found"]
        else "NEEDS_MANUAL_REVIEW"
    )
    out["dur_ns"] = time.perf_counter_ns() - t0
    path = ROOT / "logs" / "324_hole716_inventory.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"wrote {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
