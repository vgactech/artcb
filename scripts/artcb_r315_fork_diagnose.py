#!/usr/bin/env python3
"""R315 — explain P2P pull received>0 / imported=0 (Mac vs seed).

Compares local blocks.jsonl to a seed HTTPS tip/parent chain and runs the
same ``decide_public_import`` rules used by anonymous P2P.

Never wipes. Never invents continuity. Prints a machine-readable verdict:

  FORK_AT_BLOCK0 | BEHIND_SAME_CHAIN | FILTER_ONLY | EMPTY_CAN_BOOTSTRAP

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_r315_fork_diagnose.py
  PYTHONPATH=src:scripts python3 scripts/artcb_r315_fork_diagnose.py --sync
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def _get(url: str, *, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _post(url: str, *, timeout: float = 180.0) -> dict:
    req = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={
            "Authorization": f"Bearer {_key()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _load_local(blocks_path: Path) -> list[dict]:
    if not blocks_path.is_file():
        return []
    out: list[dict] = []
    for line in blocks_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", default="http://127.0.0.1:8001")
    ap.add_argument("--seed", default="https://artcb.me")
    ap.add_argument(
        "--blocks",
        default="",
        help="Local blocks.jsonl (default: $ARTCB_DATA_DIR/chain/blocks.jsonl or ./data/...)",
    )
    ap.add_argument("--sync", action="store_true", help="Also POST /p2p/sync to artcb.me peer")
    ap.add_argument("--out", default="logs/315_fork_diagnose_latest.json")
    args = ap.parse_args()
    _dns_install()
    t0 = time.time_ns()

    data_dir = (os.environ.get("ARTCB_DATA_DIR") or "").strip() or str(ROOT / "data")
    blocks_path = Path(args.blocks) if args.blocks else Path(data_dir) / "chain" / "blocks.jsonl"
    local = _load_local(blocks_path)

    mac_st = _get(f"{args.mac.rstrip('/')}/api/v1/p2p/status")
    seed_st = _get(f"{args.seed.rstrip('/')}/api/v1/p2p/status")

    by_idx: dict[int, list[dict]] = collections.defaultdict(list)
    for b in local:
        try:
            by_idx[int(b.get("index", -1))].append(b)
        except (TypeError, ValueError):
            continue
    dup = {i: len(v) for i, v in by_idx.items() if len(v) > 1}
    vis = dict(collections.Counter(str(b.get("visibility")) for b in local))
    tip = local[-1] if local else None
    b0 = by_idx.get(0, [None])[-1]

    seed0 = (_get(f"{args.seed.rstrip('/')}/api/v1/chain/block/0").get("block") or {})
    idx_cmp = []
    max_i = max(by_idx) if by_idx else -1
    for i in range(0, min(max_i, 32) + 1):
        mac_h = str((by_idx.get(i) or [{}])[-1].get("hash") or "")
        try:
            sb = _get(f"{args.seed.rstrip('/')}/api/v1/chain/block/{i}").get("block") or {}
            sh = str(sb.get("hash") or "")
        except Exception as exc:  # noqa: BLE001
            idx_cmp.append({"index": i, "error": type(exc).__name__})
            continue
        idx_cmp.append(
            {
                "index": i,
                "mac_hash": mac_h,
                "seed_hash": sh,
                "equal": bool(mac_h and sh and mac_h == sh),
                "mac_visibility": (by_idx.get(i) or [{}])[-1].get("visibility"),
                "seed_visibility": sb.get("visibility"),
            }
        )

    same_b0 = bool(b0 and seed0.get("hash") and str(b0.get("hash")) == str(seed0.get("hash")))
    if not local:
        verdict = "EMPTY_CAN_BOOTSTRAP"
    elif not same_b0:
        verdict = "FORK_AT_BLOCK0"
    elif tip and any(not row.get("equal") for row in idx_cmp if "equal" in row):
        verdict = "FORK_AFTER_COMMON_PREFIX"
    else:
        verdict = "BEHIND_SAME_CHAIN"

    # Simulate decide_public_import against sample seed public blocks
    from src.artcb.p2p.sync import decide_public_import

    local_tip = str((tip or {}).get("hash") or ("0" * 64))
    local_len = int((tip or {}).get("index", -1)) + 1 if tip else 0
    local_hashes = {str(b.get("hash")) for b in local if b.get("hash")}
    reasons: collections.Counter[tuple[str, str]] = collections.Counter()
    samples = []
    for i in list(range(0, 5)) + ([local_len - 1, local_len, local_len + 1] if tip else []):
        if i < 0:
            continue
        try:
            sb = _get(f"{args.seed.rstrip('/')}/api/v1/chain/block/{i}").get("block") or {}
        except Exception:
            continue
        d = decide_public_import(
            sb,
            local_len=local_len,
            local_tip=local_tip,
            local_hashes=local_hashes,
            structure_ok=True,
        )
        reasons[(d.action, d.reason)] += 1
        samples.append(
            {
                "index": sb.get("index"),
                "action": d.action,
                "reason": d.reason,
                "prev_hash": sb.get("prev_hash"),
                "expected_prev": local_tip,
                "expected_index": local_len,
            }
        )

    sync_result = None
    if args.sync:
        peer = "peer_artcb_me_443"
        try:
            sync_result = _post(f"{args.mac.rstrip('/')}/api/v1/p2p/sync/{peer}")
        except Exception as exc:  # noqa: BLE001
            sync_result = {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:200]}

    report = {
        "ts_ns": time.time_ns(),
        "dur_ns": time.time_ns() - t0,
        "verdict": verdict,
        "certified_100": False,
        "blocks_path": str(blocks_path),
        "local_lines": len(local),
        "local_tip_index": (tip or {}).get("index"),
        "local_tip_hash": (tip or {}).get("hash"),
        "local_visibility_counts": vis,
        "duplicate_indices": dup,
        "mac_status": {
            "network_id": mac_st.get("network_id"),
            "genesis_hash": mac_st.get("genesis_hash"),
            "last_hash": mac_st.get("last_hash"),
            "public_blocks_local": mac_st.get("public_blocks_local"),
            "public_blocks_incoming": mac_st.get("public_blocks_incoming"),
            "anonymous_p2p_public_only": mac_st.get("anonymous_p2p_public_only"),
            "official_replica_full_book": mac_st.get("official_replica_full_book"),
        },
        "seed_status": {
            "network_id": seed_st.get("network_id"),
            "genesis_hash": seed_st.get("genesis_hash"),
            "last_hash": seed_st.get("last_hash"),
            "public_blocks_local": seed_st.get("public_blocks_local"),
        },
        "block0": {
            "mac": (b0 or {}).get("hash"),
            "seed": seed0.get("hash"),
            "equal": same_b0,
            "label_network_id_equal": mac_st.get("network_id") == seed_st.get("network_id"),
            "label_genesis_hash_equal": mac_st.get("genesis_hash") == seed_st.get("genesis_hash"),
            "note": "Same genesis_hash LABEL ≠ same block-0 content hash",
        },
        "index_compare": idx_cmp,
        "decide_public_import_sample": samples,
        "decide_tally": {f"{a}:{r}": c for (a, r), c in reasons.most_common()},
        "sync": sync_result,
        "recovery_without_wipe": {
            "do_not": ["force_import", "rewrite_prev_hash", "wipe_seed_books", "new_genesis"],
            "do": [
                "quarantine_local_divergent_book",
                "preserve_private_sandbox_offline",
                "bootstrap_empty_or_official_replica_from_seed",
                "only_append_when_prev_hash_and_index_extend_tip",
            ],
            "why_imported_0": (
                "Anonymous P2P imports public blocks only via decide_public_import. "
                "A private divergent Mac tip cannot be extended by seed public blocks "
                "whose prev_hash belongs to the seed chain."
            ),
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "verdict": verdict, "out": str(out), **{k: report[k] for k in ("local_lines", "block0", "decide_tally")}}, indent=2))
    return 0 if verdict in ("BEHIND_SAME_CHAIN", "EMPTY_CAN_BOOTSTRAP") else 1


if __name__ == "__main__":
    raise SystemExit(main())
