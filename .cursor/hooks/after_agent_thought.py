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

try:
    from artcb_dns_fix import install as _dns_install  # noqa: E402
except Exception:  # noqa: BLE001
    def _dns_install() -> None:  # type: ignore[misc]
        return None

THINK_DIR = ROOT / "data" / "trace" / "thinking"
NOTIF = ROOT / "data" / "trace" / "artcb_send_notifications.jsonl"
HOOK_ENV = Path.home() / ".artcb" / "cursor_hooks.env"
AGENT_ENV = Path.home() / ".artcb" / "cursor_agent.env"


def _load_env_files() -> None:
    """Load ~/.artcb/*.env into os.environ without overriding explicit exports."""
    for path in (AGENT_ENV, HOOK_ENV):
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:  # noqa: BLE001
            continue


def _ingest_enabled() -> bool:
    """R313: default ON when API key present; explicit 0/false/off disables."""
    raw = (os.getenv("ARTCB_INGEST_THINKING") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    # default: ingest if we have a key (operator: activate everything necessary)
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    return len(key) >= 16


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
    _dns_install()
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
            "source": "cursor_afterAgentThought",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    # Prefer public book; fall back to local Mac replica if public still unreachable.
    bases = [base]
    for alt in ("https://artcb.me", "https://n1.artcb.me", "http://127.0.0.1:8001"):
        if alt not in bases:
            bases.append(alt)
    last: dict = {"skipped": True, "reason": "no_endpoint", "http": 0, "block_index": None, "block_hash": None}
    for b in bases:
        req = urllib.request.Request(
            f"{b.rstrip('/')}/api/v1/ai/memo",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:200]}
                return {
                    "skipped": False,
                    "http": resp.status,
                    "block_index": parsed.get("block_index") or parsed.get("index"),
                    "block_hash": parsed.get("block_hash") or parsed.get("hash"),
                    "reason": f"ok via {b}",
                    "api_url": b,
                }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            last = {
                "skipped": True,
                "http": exc.code,
                "reason": f"{b}:{detail}",
                "block_index": None,
                "block_hash": None,
                "api_url": b,
            }
            # auth errors: no point trying other hosts with same key shape
            if exc.code in (401, 403):
                return last
        except Exception as exc:  # noqa: BLE001
            last = {
                "skipped": True,
                "http": 0,
                "reason": f"{b}:{type(exc).__name__}:{exc}"[:220],
                "block_index": None,
                "block_hash": None,
                "api_url": b,
            }
            continue
    return last


def main() -> int:
    _load_env_files()
    _dns_install()
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
    # Layer 3 only: exact hook payload (sha256 = of this raw text, not of the .md wrapper).
    (THINK_DIR / "latest.raw.txt").write_text(text, encoding="utf-8")
    (THINK_DIR / f"{ts_ns}.raw.txt").write_text(text, encoding="utf-8")
    meta = {
        "ts_ns": ts_ns,
        "chars": len(text),
        "sha256_raw": sha,
        "duration_ms": payload.get("duration_ms"),
        "source": "cursor_afterAgentThought.stdin.text",
        "layer": 3,
        "ui_equals_hook": "NOT_PROVEN_BY_ARCHITECTURE",
        "note": (
            "Layer2 Cursor UI Thinking is visual-only; equality with this payload "
            "requires manual/visual compare. Layer1 private CoT is never here."
        ),
    }
    (THINK_DIR / "latest.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    body = (
        f"# Thinking surfacé Cursor — {ts_ns}\n\n"
        f"layer=3 (hook afterAgentThought) chars={len(text)} sha256_raw={sha}\n"
        f"ui_equals_hook=NOT_PROVEN_BY_ARCHITECTURE\n\n"
        f"---\n\n{text}\n"
    )
    (THINK_DIR / f"{ts_ns}.md").write_text(body, encoding="utf-8")
    (THINK_DIR / "latest.md").write_text(body, encoding="utf-8")

    # Visible badge for humans/future users (Cursor accordion label stays
    # "Thought briefly" — product UI cannot be renamed via hooks).
    badge = ROOT / "data" / "trace" / "ARTCB_THINKING.md"
    badge.write_text(
        (
            "# ARTCB thinking\n\n"
            f"**capture=ACTIVE** · layer=3 (afterAgentThought) · ts_ns=`{ts_ns}`\n\n"
            f"- sha256_raw: `{sha}`\n"
            f"- chars: `{len(text)}`\n"
            f"- cursor_ui_label: `Thought briefly` (NOT renamable)\n"
            f"- this_file: proof that ARTCB hook auto-captured surfaced thinking\n"
            f"- raw: `data/trace/thinking/latest.raw.txt`\n"
            f"- artcb_private: "
            f"{'attempted if ARTCB_INGEST_THINKING=1' if True else ''}\n\n"
            "---\n\n"
            f"{text[:4000]}\n"
        ),
        encoding="utf-8",
    )

    ingest = _ingest_enabled()
    sent = {
        "ts_ns": ts_ns,
        "kind": "thinking_surfaced",
        "visibility": "private",
        "chars": len(text),
        "sha256": sha,
        "sha256_raw": sha,
        "file": str(THINK_DIR / "latest.raw.txt"),
        "file_md": str(THINK_DIR / "latest.md"),
        "badge": str(badge),
        "layer": 3,
        "ui_equals_hook": "NOT_PROVEN_BY_ARCHITECTURE",
        "cursor_ui_label": "Thought briefly",
        "marker_scan": "R312_UI_HOOK_MARKER_8842" in text,
    }
    if not text.strip():
        sent.update({"skipped": True, "reason": "empty_thought", "http": 0, "block_index": None, "block_hash": None})
    elif not ingest:
        sent.update({"skipped": True, "reason": "ARTCB_INGEST_THINKING disabled", "http": 0, "block_index": None, "block_hash": None})
    else:
        result = _post_memo(
            content=f"[cursor_thinking_surfaced ts_ns={ts_ns}]\n{text}",
            visibility="private",
            tags=["thinking", "cursor", "r310", "r313"],
        )
        sent.update(result)
    _notify(sent)
    # UI↔hook proof sidecar: always record whether known markers were in payload
    proof = ROOT / "data" / "trace" / "ui_hook_marker_proof.jsonl"
    proof.parent.mkdir(parents=True, exist_ok=True)
    with proof.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts_ns": ts_ns,
                    "sha256_raw": sha,
                    "chars": len(text),
                    "has_R312_UI_HOOK_MARKER_8842": "R312_UI_HOOK_MARKER_8842" in text,
                    "ingest": ingest,
                    "artcb_http": sent.get("http"),
                    "artcb_block": sent.get("block_index"),
                    "artcb_reason": sent.get("reason"),
                    "note": (
                        "If Cursor UI Thinking shows R312_UI_HOOK_MARKER_8842 and "
                        "has_R312_UI_HOOK_MARKER_8842=true here, UI≈hook for that block."
                    ),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
