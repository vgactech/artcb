#!/usr/bin/env python3
"""R311/R312 — on Cursor `stop`, ingest turn bundle + optional chat ping.

Fail open. `followup_message` is OPT-IN (`ARTCB_THINKING_STOP_PING=1`) because
Cursor auto-submits it as the next user message (loop_limit applies).

Always refreshes data/trace/ARTCB_THINKING.md status line via LAST_ARTCB_SEND.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    status = str(payload.get("status") or "")
    loop_count = int(payload.get("loop_count") or 0)

    marker = ROOT / "data" / "trace" / "last_stop_hook.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {"ts_ns": time.time_ns(), "status": status, "loop_count": loop_count},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.setdefault("ARTCB_API_URL", "https://artcb.me")
    script = ROOT / "scripts" / "artcb_turn_bundle_ingest.py"
    if script.is_file():
        try:
            subprocess.run(
                [sys.executable, str(script)],
                cwd=str(ROOT),
                env=env,
                timeout=120,
                check=False,
                capture_output=True,
            )
        except Exception:  # noqa: BLE001
            pass

    out: dict = {}
    ping = (os.getenv("ARTCB_THINKING_STOP_PING") or "").strip() in {"1", "true", "yes", "on"}
    # One-shot style: only when completed and first auto-loop slot, opt-in.
    if ping and status == "completed" and loop_count == 0:
        meta_path = ROOT / "data" / "trace" / "thinking" / "latest.meta.json"
        sha = "?"
        chars = "?"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                sha = str(meta.get("sha256_raw") or "?")[:16]
                chars = meta.get("chars")
            except json.JSONDecodeError:
                pass
        last = ROOT / "data" / "trace" / "LAST_ARTCB_SEND.md"
        send_line = "see LAST_ARTCB_SEND.md"
        if last.is_file():
            for line in last.read_text(encoding="utf-8").splitlines():
                if "skipped:" in line or "http:" in line or "block_index:" in line:
                    send_line = line.strip("- ").strip()
                    break
        out["followup_message"] = (
            f"ARTCB thinking capture ACTIVE (Cursor UI still says « Thought briefly » — "
            f"not renamable). sha={sha}… chars={chars}. Badge: data/trace/ARTCB_THINKING.md. "
            f"Send: {send_line}"
        )

    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
