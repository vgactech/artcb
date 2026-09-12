#!/usr/bin/env python3
"""R330-E — classify every chain.height() / last_hash() call site.

Classes:
  SAFE_METRICS — observability / pagination / non-consensus
  RISK_CONSENSUS — could poison public PBFT index/tip if used as public tip
  FIXED_R328_R330 — was risk, now public tip
  LEGACY_FORENSIC — intentionally total/legacy book
  NEEDS_REVIEW — ambiguous
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# Manual classification overrides (path:line regex → class)
OVERRIDES: list[tuple[str, str, str]] = [
    (r"consensus_routes\.py", r"tip_public_private|public_last|_public_tip", "FIXED_R328_R330"),
    (r"manager\.py", r"write_certified|import_extending|_public_tip|tip_public_private", "FIXED_R328_R330"),
    (r"tip_attest\.py", r"public_height|attests_public_tip|tip_public_private", "FIXED_R328_R330"),
    (r"public_tip_watchdog\.py", r".*", "FIXED_R328_R330"),
    (r"routes\.py", r"height_total|tip_public_private|truncated", "SAFE_METRICS"),
    (r"devnet_routes\.py", r".*", "SAFE_METRICS"),
    (r"agent_protocol_routes\.py", r".*", "SAFE_METRICS"),
    (r"agent_context_contract\.py", r".*", "SAFE_METRICS"),
    (r"ai_routes\.py", r".*", "SAFE_METRICS"),
    (r"economics/", r".*", "SAFE_METRICS"),
    (r"mining/protocol\.py", r"last_hash", "NEEDS_REVIEW"),
    (r"p2p/sync\.py", r"local_height|local_tip", "RISK_CONSENSUS"),
    (r"p2p/official_replica\.py", r".*", "RISK_CONSENSUS"),
    (r"p2p_routes\.py", r".*", "NEEDS_REVIEW"),
]


def _git() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return ""


def classify(path: str, line: str) -> str:
    rel = path.replace(str(SRC) + "/", "")
    for path_re, line_re, cls in OVERRIDES:
        if re.search(path_re, rel) and re.search(line_re, line):
            return cls
    if "tip_public_private" in line or "public_last" in line or "_public_tip" in line:
        return "FIXED_R328_R330"
    if "height_total" in line or "legacy" in line.lower():
        return "LEGACY_FORENSIC"
    if any(x in rel for x in ("consensus", "pbft", "p2p")):
        return "RISK_CONSENSUS"
    return "NEEDS_REVIEW"


def main() -> int:
    pat = re.compile(r"\.(?:height|last_hash)\(\)")
    rows = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if not pat.search(line):
                continue
            if line.strip().startswith("#"):
                continue
            cls = classify(str(path), line)
            rows.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "line": i,
                    "code": line.strip()[:160],
                    "class": cls,
                }
            )
    summary: dict[str, int] = {}
    for r in rows:
        summary[r["class"]] = summary.get(r["class"], 0) + 1
    out = {
        "measurement_id": f"R330E_{time.strftime('%Y%m%dT%H%M%SZ')}",
        "ts_ns": time.time_ns(),
        "commit_sha": _git(),
        "certified_100": False,
        "summary": summary,
        "sites": rows,
        "risk_open": [r for r in rows if r["class"] == "RISK_CONSENSUS"],
        "note": "RISK_CONSENSUS sites must not drive public PBFT index; prefer tip_public_private()",
    }
    d = ROOT / "logs" / "R330"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "height_audit.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "summary": summary, "risk_count": len(out["risk_open"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
