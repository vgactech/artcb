#!/usr/bin/env python3
"""R310 — write surfaced thinking to a plain file + optional ARTCB private memo.

Cursor afterAgentThought stdin JSON →:
  1) data/trace/agent_thoughts.jsonl (via artcb_reason_log)
  2) data/trace/thinking/latest.md + thinking/<ts_ns>.md  (always, human-readable)
  3) if ARTCB_INGEST_THINKING=1 and API key present: POST memo visibility=private
  4) append data/trace/artcb_send_notifications.jsonl (what was actually sent)

Never prints thinking to stdout. Fail open.
Operator 2026-09-10T19:15:00Z: want thinking on ARTCB (private by default).
Historical ban (rules 17/40) = ~~thinking never on-chain~~ for *automatic* public;
private agent-mediated path is now allowed when ARTCB_INGEST_THINKING=1.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from artcb_reason_log import append_reason  # noqa: E402

THINK_DIR = ROOT / "data" / "trace" / "thinking"
NOTIF = ROOT / "data" / "trace" / "artcb_send_notifications.jsonl"


def _notify(row: dict) -> None:
    NOTIF.parent.mkdir(parents=True, exist_ok=True)
    with NOTIF.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    latest = ROOT / "data" / "trace" / "LAST_ARTCB_SEND.md"
    lines = [
        f"# Dernier envoi ARTCB — {row.get('ts_ns')}",
        "",
        f"- kind: `{row.get('kind')}`",
        f"- visibility: `{row.get('visibility')}`",
        f"- http: `{row.get('http')}`",
        f"- skipped: `{row.get('skipped')}`",
        f"- reason: `{row.get('reason')}`",
        f"- chars: `{row.get('chars')}`",
        f"- sha256: `{row.get('sha256')}`",
        f"- block_index: `{row.get('block_index')}`",
        f"- block_hash: `{row.get('block_hash')}`",
        "",
    ]
    latest.write_text("\n".join(lines), encoding="utf-8")


def _post_memo(*, content: str, visibility: str, tags: list[str]) -> dict:
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    base = (os.environ.get("ARTCB_API_URL") or "https://artcb.me").rstrip("/")
    if len(key) < 16:
        return {"skipped": True, "reason": "api_key_missing", "http": 0}
    body = json.dumps(
        {
            "content": content[:120_000],
            "visibility": visibility,
            "memo_type": "agent_thought_surfaced",
            "tags": tags,
            "includes_thinking": True,
            "source": "cursor_afterAgentThought",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/v1/ai/memo",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:200]}
            return {
                "skipped": False,
                "http": resp.status,
                "block_index": parsed.get("block_index") or parsed.get("index"),
                "block_hash": parsed.get("block_hash") or parsed.get("hash"),
                "reason": "ok",
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return {"skipped": True, "http": exc.code, "reason": detail, "block_index": None, "block_hash": None}
    except Exception as exc:  # noqa: BLE001
        return {"skipped": True, "http": 0, "reason": f"{type(exc).__name__}:{exc}"[:200], "block_index": None, "block_hash": None}


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    text = str(payload.get("text") or "")
    ts_ns = time.time_ns()
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    extra = {"ts_ns": ts_ns, "sha256": sha}
    if payload.get("duration_ms") is not None:
        extra["duration_ms"] = payload.get("duration_ms")

    dest = (os.getenv("ARTCB_THOUGHT_LOG") or "").strip()
    append_reason(
        kind="afterAgentThought",
        text=text,
        extra=extra,
        path=Path(dest) if dest else None,
    )

    THINK_DIR.mkdir(parents=True, exist_ok=True)
    body = (
        f"# Thinking surfacé Cursor — {ts_ns}\n\n"
        f"chars={len(text)} sha256={sha}\n\n"
        f"---\n\n{text}\n"
    )
    (THINK_DIR / f"{ts_ns}.md").write_text(body, encoding="utf-8")
    (THINK_DIR / "latest.md").write_text(body, encoding="utf-8")

    ingest = (os.getenv("ARTCB_INGEST_THINKING") or "").strip() in {"1", "true", "yes", "on"}
    sent = {
        "ts_ns": ts_ns,
        "kind": "thinking_surfaced",
        "visibility": "private",
        "chars": len(text),
        "sha256": sha,
        "file": str(THINK_DIR / "latest.md"),
    }
    if not text.strip():
        sent.update({"skipped": True, "reason": "empty_thought", "http": 0, "block_index": None, "block_hash": None})
    elif not ingest:
        sent.update({"skipped": True, "reason": "ARTCB_INGEST_THINKING unset (file-only)", "http": 0, "block_index": None, "block_hash": None})
    else:
        result = _post_memo(
            content=f"[cursor_thinking_surfaced ts_ns={ts_ns}]\n{text}",
            visibility="private",
            tags=["thinking", "cursor", "r310"],
        )
        sent.update(result)
    _notify(sent)
    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
