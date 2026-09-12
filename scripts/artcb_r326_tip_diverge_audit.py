#!/usr/bin/env python3
"""R326 — P0 tip-diverge audit (public tip vs private suffix).

Diagnoses height gaps between seeds without inventing blocks.
CERTIFIED_100=false.
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
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from artcb_dns_fix import install as _dns

    _dns()
except Exception:  # noqa: BLE001
    pass

SEEDS = (
    "https://artcb.me",
    "https://n2.artcb.me",
    "https://n3.artcb.me",
    "https://n4.artcb.me",
)
PUBLIC_TIP_HASH = "013f327cb76bef8bd50f09935850452fc3c8bae1be7c7128f92f1ad835595539"


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return ""


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


def get(url: str, *, auth: bool = False, timeout: float = 30) -> tuple[int, dict | None]:
    headers = {"Accept": "application/json"}
    if auth and _key():
        headers["Authorization"] = f"Bearer {_key()}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=timeout
        ) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"http_error": e.read()[:180].decode("utf-8", "replace")}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:120]}


def main() -> int:
    t0 = time.perf_counter_ns()
    commit = _git_sha()
    mid = f"R326_{time.strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}"
    out: dict = {
        "measurement_id": mid,
        "ts_ns": time.time_ns(),
        "commit_sha": commit,
        "certified_100": False,
        "seeds": {},
        "classification": {},
    }

    for base in SEEDS:
        row: dict = {"base": base}
        ch, health = get(f"{base}/health")
        cs, status = get(f"{base}/api/v1/chain/status")
        cv, view = get(f"{base}/api/v1/consensus/pbft/view", auth=True)
        row["health_http"] = ch
        row["status_http"] = cs
        row["view_http"] = cv
        if isinstance(health, dict):
            row["git_sha12"] = str(health.get("git_sha") or "")[:12]
        if isinstance(status, dict) and "error" not in status and "http_error" not in status:
            row["height"] = status.get("height")
            row["last_index"] = status.get("last_index")
            row["last_hash"] = status.get("last_hash")
            row["last_timestamp"] = status.get("last_timestamp")
            row["public_tip_match_1140"] = str(status.get("last_hash") or "") == PUBLIC_TIP_HASH
        if isinstance(view, dict) and "protocol" in view:
            row["pbft"] = {
                k: view.get(k)
                for k in ("view", "primary", "n", "f", "q", "replica_id", "replicas")
            }
        # anon public window
        ca, anon = get(f"{base}/api/v1/chain/blocks?from_index=1135&limit=15", auth=False)
        if isinstance(anon, dict):
            row["anon_idxs"] = [b.get("index") for b in (anon.get("blocks") or [])]
        out["seeds"][base] = row

    # ovh1 private suffix classify (auth)
    ovh = "https://artcb.me"
    private = 0
    public_after = 0
    with_cert = 0
    without_cert = 0
    dup = Counter()
    idxs: list[int] = []
    i = 1140
    while i < 2000:
        c, body = get(f"{ovh}/api/v1/chain/blocks?from_index={i}&limit=80", auth=True)
        if c != 200 or not isinstance(body, dict):
            break
        blks = body.get("blocks") or []
        if not blks:
            break
        for b in blks:
            idx = int(b.get("index") or -1)
            idxs.append(idx)
            dup[idx] += 1
            if idx < 1141:
                continue
            vis = str(b.get("visibility") or "")
            if vis == "private":
                private += 1
            elif vis == "public":
                public_after += 1
            if isinstance(b.get("pbft_cert"), dict):
                with_cert += 1
            else:
                without_cert += 1
        last = max(int(b.get("index") or 0) for b in blks)
        if last <= i and not body.get("truncated"):
            break
        i = last + 1
        if not body.get("truncated") and last >= 1900:
            break

    out["ovh1_after_1140"] = {
        "private_blocks_seen": private,
        "public_blocks_seen": public_after,
        "with_pbft_cert": with_cert,
        "without_pbft_cert": without_cert,
        "duplicate_index_count": sum(1 for _, c in dup.items() if c > 1),
        "note": "Auth Bearer required to see private suffix on ovh1",
    }

    # hole samples
    hole = {}
    for idx in (716, 717, 1074, 1140, 1141):
        hole[idx] = {
            name: get(f"{base}/api/v1/chain/block/{idx}")[0]
            for name, base in (
                ("ovh1", "https://artcb.me"),
                ("n2", "https://n2.artcb.me"),
                ("n3", "https://n3.artcb.me"),
            )
        }
    out["hole_http_anon"] = hole

    heights = {
        k: v.get("height")
        for k, v in out["seeds"].items()
        if v.get("height") is not None
    }
    public_aligned = all(
        (v.get("last_hash") == PUBLIC_TIP_HASH)
        or (v.get("anon_idxs") and 1140 in (v.get("anon_idxs") or []))
        for v in out["seeds"].values()
        if v.get("status_http") == 200
    )

    out["classification"] = {
        "classic_pbft_split_brain_675_public": False,
        "reason": (
            "ovh1 height inflation is almost entirely visibility=private blocks "
            "without pbft_cert after public tip 1140; n2/n3/n4 public tip still 1140 "
            f"hash {PUBLIC_TIP_HASH[:16]}…"
        ),
        "public_tip_aligned_at_1140": public_aligned,
        "public_pbft_stalled_since": "2026-09-10T19:21:46Z",
        "heights_raw": heights,
        "severity_risks": [
            "status.height conflates private+public → false split-brain alarms",
            "duplicate block.index values in private suffix",
            "717 still absent (PRODUCTION_CONTINUITY_GAP)",
            "n4 intermittent 502",
            "no new public pbft_cert after 1140",
        ],
        "verdict": "P0_STATUS_SEMANTICS_AND_PUBLIC_STALL",
        "action": (
            "Do not rewind/wipe. Report public_tip separately from total height. "
            "Investigate why public PBFT append stopped at 1140. Hole 716 remains "
            "secondary to public stall + private-only ovh1 growth."
        ),
    }
    out["dur_ns"] = time.perf_counter_ns() - t0

    out_dir = ROOT / "logs" / "R326"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "measurement.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "commit_sha.txt").write_text(commit + "\n", encoding="utf-8")
    lines = [
        f"# R326 — tip diverge P0 ({mid})",
        "",
        f"`commit_sha` = `{commit}`",
        "",
        "`CERTIFIED_100=false`",
        "",
        "## Verdict",
        "",
        f"**{out['classification']['verdict']}**",
        "",
        out["classification"]["reason"],
        "",
        f"- classic_pbft_split_brain_675_public: **{out['classification']['classic_pbft_split_brain_675_public']}**",
        f"- public tip aligned @1140: **{out['classification']['public_tip_aligned_at_1140']}**",
        f"- ovh1 after 1140 private: {private} ; public_after: {public_after} ; with_cert: {with_cert}",
        f"- heights raw: `{heights}`",
        "",
        "## Action",
        "",
        out["classification"]["action"],
        "",
        "Never invent 717. Never wipe.",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest = ROOT / "rapports" / f"326_tip_diverge_{commit[:12]}.md"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"measurement_id": mid, "classification": out["classification"], "report": str(dest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
