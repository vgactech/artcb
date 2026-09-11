#!/usr/bin/env python3
"""R315 — quarantine a *local* divergent book (never wipe seeds).

Moves ``$ARTCB_DATA_DIR/chain/blocks.jsonl`` aside so a fresh bootstrap /
official-replica catch-up can start from an empty tip. The old file is kept
under ``data/quarantine/`` with a timestamp — not deleted.

Requires ``--i-understand-local-only`` and a prior FORK_* verdict from
``artcb_r315_fork_diagnose.py`` unless ``--force``.

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_r315_quarantine_local_book.py --dry-run
  PYTHONPATH=src:scripts python3 scripts/artcb_r315_quarantine_local_book.py --i-understand-local-only
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--i-understand-local-only",
        action="store_true",
        help="Required: only local Mac/sandbox book is moved; seeds untouched",
    )
    args = ap.parse_args()
    if not args.i_understand_local_only and not args.dry_run:
        print(json.dumps({"ok": False, "reason": "pass --i-understand-local-only or --dry-run"}))
        return 2

    data_dir = Path(args.data_dir or os.environ.get("ARTCB_DATA_DIR") or (ROOT / "data"))
    blocks = data_dir / "chain" / "blocks.jsonl"
    diag = ROOT / "logs" / "315_fork_diagnose_latest.json"
    verdict = None
    if diag.is_file():
        verdict = json.loads(diag.read_text(encoding="utf-8")).get("verdict")
    if verdict not in ("FORK_AT_BLOCK0", "FORK_AFTER_COMMON_PREFIX") and not args.force:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "refusing without FORK_* verdict (run artcb_r315_fork_diagnose.py) or --force",
                    "verdict": verdict,
                }
            )
        )
        return 3

    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    qdir = data_dir / "quarantine" / f"divergent_book_{ts}"
    dest = qdir / "blocks.jsonl"
    plan = {
        "ok": True,
        "action": "quarantine_local_book",
        "source": str(blocks),
        "dest": str(dest),
        "verdict": verdict,
        "dry_run": args.dry_run,
        "seeds_touched": False,
        "wipe": False,
        "note": "After quarantine: restart node empty → official/bootstrap catch-up; never new genesis",
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    if not blocks.is_file():
        plan["ok"] = False
        plan["reason"] = "blocks_missing"
        print(json.dumps(plan, indent=2))
        return 4
    qdir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(blocks), str(dest))
    # leave empty chain file so process can recreate
    blocks.parent.mkdir(parents=True, exist_ok=True)
    blocks.write_text("", encoding="utf-8")
    meta = qdir / "quarantine_meta.json"
    meta.write_text(json.dumps({**plan, "ts_ns": time.time_ns()}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
