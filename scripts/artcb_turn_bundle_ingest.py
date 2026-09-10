#!/usr/bin/env python3
"""R310 — end-of-turn bundle → ARTCB scopes public/org/group/private + notification.

Uses POST /api/v1/ai/ingest-batch (scopes) — memo visibility is only public|private.
Org/group map to private chain bodies with logical scope tags (repo_scope).

Notification: data/trace/LAST_ARTCB_SEND.md + artcb_send_notifications.jsonl
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

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTIF = ROOT / "data" / "trace" / "artcb_send_notifications.jsonl"
LATEST = ROOT / "data" / "trace" / "LAST_ARTCB_SEND.md"


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True, timeout=30).strip()
    except Exception:
        return ""


def _notify(rows: list[dict]) -> None:
    NOTIF.parent.mkdir(parents=True, exist_ok=True)
    with NOTIF.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    lines = ["# Envois ARTCB de ce tour", ""]
    for row in rows:
        lines.append(
            f"- **{row.get('kind')}** scope=`{row.get('scope')}` http=`{row.get('http')}` "
            f"skipped=`{row.get('skipped')}` reason=`{(row.get('reason') or '')[:120]}` "
            f"block=`{row.get('block_index')}`"
        )
    lines.append("")
    LATEST.write_text("\n".join(lines), encoding="utf-8")


def _post_batch(*, scope: str, kind: str, source_text: str, files: list[dict]) -> dict:
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    base = (os.environ.get("ARTCB_API_URL") or "https://artcb.me").rstrip("/")
    sha = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    row = {
        "ts_ns": time.time_ns(),
        "kind": kind,
        "scope": scope,
        "chars": len(source_text),
        "sha256": sha,
    }
    if len(key) < 16:
        return {**row, "skipped": True, "reason": "api_key_missing", "http": 0, "block_index": None}
    body = json.dumps(
        {
            "batch_id": f"r310-{scope}-{int(time.time())}",
            "scope": scope,
            "kind": kind,
            "source_text": source_text[:390_000],
            "files": files,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/v1/ai/ingest-batch",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
            return {
                **row,
                "skipped": False,
                "http": resp.status,
                "reason": "ok",
                "block_index": parsed.get("block_index") or parsed.get("index") or (parsed.get("result") or {}).get("block_index"),
                "block_hash": parsed.get("block_hash") or parsed.get("hash"),
                "raw_keys": list(parsed)[:12] if isinstance(parsed, dict) else [],
            }
    except urllib.error.HTTPError as exc:
        return {
            **row,
            "skipped": True,
            "http": exc.code,
            "reason": exc.read().decode("utf-8", errors="replace")[:240],
            "block_index": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {**row, "skipped": True, "http": 0, "reason": f"{type(exc).__name__}:{exc}"[:200], "block_index": None}


def _post_memo_public(source_text: str) -> dict:
    """Public chain writes go through /ai/memo (PBFT path), not ingest-batch."""
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    base = (os.environ.get("ARTCB_API_URL") or "https://artcb.me").rstrip("/")
    sha = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    row = {"ts_ns": time.time_ns(), "kind": "turn_public", "scope": "public", "chars": len(source_text), "sha256": sha}
    if len(key) < 16:
        return {**row, "skipped": True, "reason": "api_key_missing", "http": 0, "block_index": None}
    body = json.dumps(
        {"content": source_text[:120_000], "visibility": "public", "memo_type": "turn_public", "tags": ["turn", "public", "r310"], "includes_thinking": False},
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        f"{base}/api/v1/ai/memo",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
            return {**row, "skipped": False, "http": resp.status, "reason": "ok", "block_index": parsed.get("block_index") or parsed.get("index"), "block_hash": parsed.get("block_hash")}
    except urllib.error.HTTPError as exc:
        return {**row, "skipped": True, "http": exc.code, "reason": exc.read().decode("utf-8", errors="replace")[:240], "block_index": None}
    except Exception as exc:  # noqa: BLE001
        return {**row, "skipped": True, "http": 0, "reason": f"{type(exc).__name__}:{exc}"[:200], "block_index": None}


def main() -> int:
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--short")
    diffstat = _git("diff", "--stat", "HEAD")
    prompt = Path("/tmp/artcb_turn_prompt.txt")
    prompt_txt = prompt.read_text(encoding="utf-8", errors="replace") if prompt.exists() else ""
    think_latest = ROOT / "data" / "trace" / "thinking" / "latest.md"
    think_txt = think_latest.read_text(encoding="utf-8", errors="replace") if think_latest.exists() else ""

    rows = []
    rows.append(
        _post_memo_public(f"# Turn public\nHEAD={head}\n\n## user_query\n{prompt_txt[:80_000]}\n")
    )
    rows.append(
        _post_batch(
            scope="organization",
            kind="turn_org_diff",
            source_text=f"# Turn organization\nHEAD={head}\n\n## status\n{status[:30_000]}\n\n## diffstat\n{diffstat[:30_000]}\n",
            files=[
                {"path": "turn/git_status.txt", "text": status[:30_000], "sha256": hashlib.sha256(status.encode()).hexdigest()},
                {"path": "turn/diffstat.txt", "text": diffstat[:30_000], "sha256": hashlib.sha256(diffstat.encode()).hexdigest()},
            ],
        )
    )
    rows.append(
        _post_batch(
            scope="group",
            kind="turn_group_ci",
            source_text=f"# Turn group\nHEAD={head}\nCI=workflow_dispatch\nCERTIFIED_100=false\n",
            files=[{"path": "turn/ci_pointer.md", "text": f"HEAD={head}\nCERTIFIED_100=false\n", "sha256": hashlib.sha256(head.encode()).hexdigest()}],
        )
    )
    rows.append(
        _post_batch(
            scope="private",
            kind="turn_private_thinking",
            source_text=(
                f"# Turn private thinking\nHEAD={head}\n"
                f"CoT privé modèle: NOT claimed on-disk.\n"
                f"Surfaced thinking below (hook afterAgentThought).\n\n{think_txt[:80_000]}\n"
            ),
            files=[
                {
                    "path": "turn/thinking_latest.md",
                    "text": think_txt[:80_000] or "(no surfaced thinking yet)",
                    "sha256": hashlib.sha256((think_txt or "empty").encode()).hexdigest(),
                }
            ],
        )
    )
    _notify(rows)
    print(json.dumps({"ok": True, "rows": [{k: r.get(k) for k in ("kind", "scope", "http", "skipped", "reason", "block_index")} for r in rows]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
