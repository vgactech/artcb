#!/usr/bin/env python3
"""R317 — Mac catch-up from seed after local quarantine (autonomous).

Pulls the seed book via authenticated ``GET /api/v1/chain`` (all visibilities
the key can read), then ``import_extending_block(require_public=False)`` into
the local ``ARTCB_DATA_DIR`` chain. Preserves quarantine forensics.

Never wipes seeds. Never invents genesis. Never rewrites prev_hash.

Usage (Mac node should be STOPPED to avoid file races):
  PYTHONPATH=src:scripts python3 scripts/artcb_r317_mac_catchup_from_seed.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
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


def _get(url: str, *, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {_key()}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_seed_blocks(seed: str, *, max_height_hint: int = 5000) -> list[dict]:
    """Walk from_index; on empty page, probe forward for sparse indices."""
    out: dict[int, dict] = {}
    from_index = 0
    empty_streak = 0
    while from_index < max_height_hint and empty_streak < 80:
        url = f"{seed.rstrip('/')}/api/v1/chain?from_index={from_index}&limit=256"
        try:
            page = _get(url)
        except Exception:
            empty_streak += 1
            from_index += 1
            continue
        blocks = page.get("blocks") or []
        if not blocks:
            empty_streak += 1
            # jump probe: try individual indices ahead
            found = False
            for probe in range(from_index, min(from_index + 50, max_height_hint)):
                try:
                    one = _get(f"{seed.rstrip('/')}/api/v1/chain/block/{probe}").get("block")
                    if one:
                        out[int(one["index"])] = one
                        from_index = int(one["index"]) + 1
                        empty_streak = 0
                        found = True
                        break
                except Exception:
                    continue
            if not found:
                from_index += 1
            continue
        empty_streak = 0
        for b in blocks:
            try:
                i = int(b.get("index"))
            except (TypeError, ValueError):
                continue
            out[i] = b
        from_index = max(out) + 1 if out else from_index + 1
    return [out[i] for i in sorted(out)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="https://artcb.me")
    ap.add_argument("--data-dir", default="")
    ap.add_argument("--out", default="logs/317_mac_catchup_latest.json")
    ap.add_argument("--max-blocks", type=int, default=5000)
    args = ap.parse_args()
    _dns_install()
    t0 = time.time_ns()
    if len(_key()) < 16:
        print(json.dumps({"ok": False, "reason": "api_key_missing"}))
        return 2

    data_dir = Path(args.data_dir or os.environ.get("ARTCB_DATA_DIR") or (ROOT / "data"))
    blocks_path = data_dir / "chain" / "blocks.jsonl"
    blocks_path.parent.mkdir(parents=True, exist_ok=True)

    seed_status = _get(f"{args.seed.rstrip('/')}/api/v1/chain/status")
    remote_blocks = fetch_seed_blocks(args.seed, max_height_hint=int(seed_status.get("height") or 2000) + 50)
    # also fetch tip block if missing
    try:
        tip_i = int(seed_status.get("height") or 0) - 1
        if tip_i >= 0 and tip_i not in {int(b["index"]) for b in remote_blocks}:
            b = _get(f"{args.seed.rstrip('/')}/api/v1/chain/block/{tip_i}").get("block")
            if b:
                remote_blocks.append(b)
                remote_blocks.sort(key=lambda x: int(x.get("index") or 0))
    except Exception:
        pass

    from src.artcb.chain.manager import ChainManager

    chain = ChainManager(blocks_path=blocks_path, key_path=data_dir / "chain.key", enable_security=False)
    imported = 0
    skipped = 0
    rejected: list[dict] = []
    decisions = Counter()

    for b in remote_blocks:
        before = chain.height()
        tip = chain.last_hash()
        idx = int(b.get("index") or -1)
        # already have?
        existing = None
        try:
            existing = chain.get_block(idx)
        except Exception:
            existing = None
        if existing and str(existing.get("hash")) == str(b.get("hash")):
            skipped += 1
            decisions["duplicate"] += 1
            continue
        ok = False
        try:
            ok = bool(
                chain.import_extending_block(
                    b, require_public=False, from_node_id="r317_seed_catchup"
                )
            )
        except Exception as exc:  # noqa: BLE001
            rejected.append({"index": idx, "error": type(exc).__name__, "detail": str(exc)[:160]})
            decisions["exception"] += 1
            # stop on hard break to avoid writing past a hole incorrectly
            break
        if ok:
            imported += 1
            decisions["append"] += 1
        else:
            rejected.append(
                {
                    "index": idx,
                    "reason": "import_failed",
                    "expected_index": before,
                    "expected_prev": tip,
                    "got_prev": b.get("prev_hash"),
                    "visibility": b.get("visibility"),
                    "has_pbft_cert": isinstance(b.get("pbft_cert"), dict),
                }
            )
            decisions["reject"] += 1
            # contiguous import: stop at first reject
            break

    report = {
        "ts_ns": time.time_ns(),
        "dur_ns": time.time_ns() - t0,
        "certified_100": False,
        "seed": args.seed,
        "seed_status": {
            "height": seed_status.get("height"),
            "last_hash": seed_status.get("last_hash"),
            "block_count": seed_status.get("block_count"),
        },
        "fetched": len(remote_blocks),
        "fetched_visibility": dict(Counter(str(b.get("visibility")) for b in remote_blocks)),
        "imported": imported,
        "skipped_duplicate": skipped,
        "decisions": dict(decisions),
        "rejected_head": rejected[:20],
        "local_height_after": chain.height(),
        "local_tip_after": chain.last_hash(),
        "quarantine_untouched": True,
        "seeds_wiped": False,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": imported > 0 or skipped > 0, **{k: report[k] for k in ("fetched", "imported", "local_height_after", "local_tip_after", "decisions", "rejected_head")}}, indent=2)[:4000])
    return 0 if report["local_height_after"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
