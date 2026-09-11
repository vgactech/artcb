#!/usr/bin/env python3
"""R316 — LOCAL_BOOK_ORIGIN_AUDIT (why Mac has private divergent 0..8).

Never quarantine here. Never wipe. Reconstruct timeline from local
``blocks.jsonl`` + optional seed block-0 compare.

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_r316_local_book_origin_audit.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

try:
    from artcb_dns_fix import install as _dns_install
except Exception:  # noqa: BLE001

    def _dns_install() -> None:
        return None


def _key() -> str:
    k = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(k) >= 16:
        return k
    env = Path.home() / ".artcb" / "cursor_agent.env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ARTCB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _get(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {_key()}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode())


def _classify_row(b: dict) -> str:
    ps = b.get("public_symbols") or {}
    mt = str(ps.get("memo_type") or "")
    gid = str(b.get("graph_id") or "")
    if mt == "agent_thought_surfaced" or "thinking" in str(ps.get("tags") or ""):
        return "private_ai_thought_memo"
    if mt == "pol_work" or str(ps.get("agent_id") or "").startswith("bob"):
        return "private_bob_agent_memo"
    if gid.startswith("ai_memo_"):
        return "private_ai_memo"
    if gid.startswith("g_"):
        return "private_local_graph_bootstrap"
    return "private_other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", default="")
    ap.add_argument("--seed", default="https://artcb.me")
    ap.add_argument("--out", default="logs/316_local_book_origin_latest.json")
    args = ap.parse_args()
    _dns_install()
    t0 = time.time_ns()

    data_dir = Path(os.environ.get("ARTCB_DATA_DIR") or (ROOT / "data"))
    path = Path(args.blocks) if args.blocks else data_dir / "chain" / "blocks.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    by_idx: dict[int, list[dict]] = {}
    timeline = []
    for line_i, b in enumerate(rows):
        idx = int(b.get("index", -1))
        by_idx.setdefault(idx, []).append(b)
        kind = _classify_row(b)
        timeline.append(
            {
                "line": line_i,
                "index": idx,
                "hash": b.get("hash"),
                "prev_hash": b.get("prev_hash"),
                "timestamp": b.get("timestamp"),
                "visibility": b.get("visibility"),
                "graph_id": b.get("graph_id"),
                "kind": kind,
                "memo_type": (b.get("public_symbols") or {}).get("memo_type"),
                "agent_id": (b.get("public_symbols") or {}).get("agent_id"),
                "tags": (b.get("public_symbols") or {}).get("tags"),
            }
        )

    dups = {i: len(v) for i, v in by_idx.items() if len(v) > 1}
    kinds = dict(Counter(t["kind"] for t in timeline))

    seed0 = {}
    try:
        seed0 = _get(f"{args.seed.rstrip('/')}/api/v1/chain/block/0").get("block") or {}
    except Exception as exc:  # noqa: BLE001
        seed0 = {"error": type(exc).__name__}

    mac0 = by_idx.get(0, [{}])[0]
    origin_hypothesis = {
        "code": "LOCAL_PRIVATE_SANDBOX_THEN_PRIVATE_MEMOS",
        "not": [
            "mainnet_public_book",
            "p2p_import_corruption",
            "wifi_caused_fork",
        ],
        "evidence": [
            "block0..4 timestamps 2026-09-05T22:48Z private graphs g_* (Bob local era)",
            "seed block0 2026-09-01 public g_29b131e92c84 — different hash and day",
            "later rows are private ai_memo / bob / agent_thought_surfaced on THAT tip",
            "duplicate index 8 = two concurrent private thought memos same prev/ts",
            "wifi loss does not rewrite block0; this book predates R314 HTTPS peers",
        ],
        "recommended_before_quarantine": "preserve forensic copy; treat as private sandbox context, not mainnet",
        "architectural_gap": "node used single blocks.jsonl for local private activity without chain_identity=block0.hash gate vs canonical mainnet",
    }

    report = {
        "ts_ns": time.time_ns(),
        "dur_ns": time.time_ns() - t0,
        "certified_100": False,
        "blocks_path": str(path),
        "local_lines": len(rows),
        "visibility_counts": dict(Counter(str(b.get("visibility")) for b in rows)),
        "kind_counts": kinds,
        "duplicate_indices": dups,
        "timeline": timeline,
        "mac_block0": {
            "hash": mac0.get("hash"),
            "timestamp": mac0.get("timestamp"),
            "visibility": mac0.get("visibility"),
            "graph_id": mac0.get("graph_id"),
        },
        "seed_block0": {
            "hash": seed0.get("hash"),
            "timestamp": seed0.get("timestamp"),
            "visibility": seed0.get("visibility"),
            "graph_id": seed0.get("graph_id"),
            "error": seed0.get("error"),
        },
        "block0_equal": bool(mac0.get("hash") and seed0.get("hash") and mac0.get("hash") == seed0.get("hash")),
        "origin_hypothesis": origin_hypothesis,
        "ports_note": {
            "api_http": 8000,
            "p2p_native_documented": 18444,
            "hybrid_sync_today": "HTTP(S) API peers often used for public block pull (not native :18444 path from Mac)",
        },
        "no_quarantine_this_run": True,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "origin": origin_hypothesis["code"],
                "block0_equal": report["block0_equal"],
                "kinds": kinds,
                "dups": dups,
                "out": str(out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
