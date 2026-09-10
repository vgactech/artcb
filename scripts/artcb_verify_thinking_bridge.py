#!/usr/bin/env python3
"""R311 — verify thinking bridge: hook raw ↔ local files ↔ optional ARTCB memo.

Four layers (do not mix):
  1) model private CoT — never available here
  2) Cursor UI Thinking panel — visual only; NOT proven equal to (3) by architecture
  3) afterAgentThought surfaced payload — what the hook receives (text field)
  4) ARTCB private memo — only if ARTCB_INGEST_THINKING=1 and HTTP ok

Compares sha256 of (3) across latest.raw.txt, notifications jsonl, and memo body
prefix when block_index is known.

Usage:
  PYTHONPATH=src python3 scripts/artcb_verify_thinking_bridge.py
  PYTHONPATH=src python3 scripts/artcb_verify_thinking_bridge.py --fetch-artcb
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

try:
    from artcb_dns_fix import install as _artcb_dns_install
    _artcb_dns_install()
except Exception:
    pass

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THINK = ROOT / "data" / "trace" / "thinking"
NOTIF = ROOT / "data" / "trace" / "artcb_send_notifications.jsonl"
LAST = ROOT / "data" / "trace" / "LAST_ARTCB_SEND.md"


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _load_raw() -> tuple[str, str]:
    raw_path = THINK / "latest.raw.txt"
    if raw_path.is_file():
        return raw_path.read_text(encoding="utf-8"), "latest.raw.txt"
    md = THINK / "latest.md"
    if not md.is_file():
        return "", "missing"
    body = md.read_text(encoding="utf-8")
    if "\n---\n\n" in body:
        text = body.split("\n---\n\n", 1)[1]
        if text.endswith("\n"):
            text = text[:-1]
        return text, "latest.md(parsed)"
    return body, "latest.md(full)"


def _last_notif() -> dict:
    if not NOTIF.is_file():
        return {}
    last = {}
    for line in NOTIF.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("kind") == "thinking_surfaced":
            last = row
    return last


def _fetch_memo(block_index: int) -> dict:
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    base = (os.environ.get("ARTCB_API_URL") or "https://artcb.me").rstrip("/")
    if len(key) < 16:
        return {"ok": False, "reason": "api_key_missing"}
    # Prefer AI memo by index if exposed; fall back to chain tip scan via context
    url = f"{base}/api/v1/ai/memo/{block_index}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"ok": True, "http": resp.status, "body": json.loads(resp.read().decode())}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}:{exc}"[:240]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-artcb", action="store_true")
    args = ap.parse_args()

    text, source = _load_raw()
    meta_path = THINK / "latest.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    notif = _last_notif()
    local_sha = _sha(text) if text else None
    meta_sha = meta.get("sha256_raw")
    notif_sha = notif.get("sha256")

    report = {
        "layers": {
            "1_private_cot": "NOT_AVAILABLE",
            "2_cursor_ui_thinking": "VISUAL_ONLY_NOT_PROVEN_EQUAL_TO_HOOK",
            "3_hook_surfaced": source,
            "4_artcb": "checked_below" if args.fetch_artcb else "not_fetched",
        },
        "chars": len(text),
        "sha256_local_raw": local_sha,
        "sha256_meta": meta_sha,
        "sha256_notif": notif_sha,
        "match_local_meta": bool(local_sha and meta_sha and local_sha == meta_sha),
        "match_local_notif": bool(local_sha and notif_sha and local_sha == notif_sha),
        "notif_skipped": notif.get("skipped"),
        "notif_reason": notif.get("reason"),
        "notif_http": notif.get("http"),
        "block_index": notif.get("block_index"),
        "block_hash": notif.get("block_hash"),
        "last_send_md_exists": LAST.is_file(),
        "verdict_hook_to_files": None,
        "verdict_to_artcb": None,
        "ui_equals_hook": "NOT_PROVEN_BY_ARCHITECTURE",
    }

    if not text:
        report["verdict_hook_to_files"] = "FAIL_NO_LOCAL_THINKING"
    elif report["match_local_notif"] and (meta_sha is None or report["match_local_meta"]):
        report["verdict_hook_to_files"] = "PASS"
    else:
        report["verdict_hook_to_files"] = "FAIL_HASH_MISMATCH"

    if args.fetch_artcb and notif.get("block_index") is not None:
        fetched = _fetch_memo(int(notif["block_index"]))
        report["artcb_fetch"] = {k: fetched.get(k) for k in ("ok", "http", "reason")}
        body = fetched.get("body") or {}
        content = ""
        if isinstance(body, dict):
            content = str(
                body.get("content_text")
                or body.get("content")
                or body.get("text")
                or body.get("memo")
                or ""
            )
        # Memo prefixes with [cursor_thinking_surfaced ts_ns=...]
        m = re.search(r"\[cursor_thinking_surfaced[^\]]*\]\n(.*)$", content, re.S)
        artcb_text = m.group(1) if m else content
        artcb_sha = _sha(artcb_text) if artcb_text else None
        report["sha256_artcb_payload"] = artcb_sha
        report["match_local_artcb"] = bool(local_sha and artcb_sha and local_sha == artcb_sha)
        report["verdict_to_artcb"] = (
            "PASS" if report["match_local_artcb"] else "FAIL_OR_ENDPOINT_SHAPE"
        )
    elif notif.get("skipped"):
        report["verdict_to_artcb"] = f"SKIPPED:{notif.get('reason')}"
    elif notif.get("http") in (200, 201):
        report["verdict_to_artcb"] = "SENT_HTTP_OK_FETCH_TO_COMPARE"
    else:
        report["verdict_to_artcb"] = "NOT_SENT"

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["verdict_hook_to_files"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
