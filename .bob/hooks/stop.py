#!/usr/bin/env python3
"""Bob IDE — Stop hook.

À la fin de chaque tour :
  - Archive le dernier message assistant + métadonnées dans bob_turns.jsonl
  - Publie un événement JOB_COMPLETED vers ARTCB via src.artcb.bob.job_completed
    (idempotent, outbox locale si ARTCB indisponible, retry via flush_outbox)
  - Tente aussi de rejouer les événements en attente (outbox flush)

Fail-open. Jamais de secrets. includes_thinking=False toujours.
"""
from __future__ import annotations
import hashlib, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "data" / "trace"


def _count_tools(session_id: str | None) -> int:
    """Compte les outils utilisés dans cette session depuis bob_tool_usage.jsonl."""
    path = TRACE / "bob_tool_usage.jsonl"
    if not path.exists():
        return 0
    count = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if not session_id or row.get("session_id") == session_id:
                        count += 1
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return count


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = payload.get("session_id")
    last_msg = str(payload.get("last_assistant_message") or "")

    # --- Archive locale (bob_turns.jsonl) ---
    artcb_result: dict = {}
    try:
        TRACE.mkdir(parents=True, exist_ok=True)
        tool_count = _count_tools(session_id)
        row = {
            "ts_ns": time.time_ns(),
            "kind": "bob_stop",
            "session_id": session_id,
            "chars": len(last_msg),
            "sha256": hashlib.sha256(last_msg.encode()).hexdigest(),
            "artcb_bound": False,  # sera mis à True si JOB_COMPLETED commis
            "note": "bob_ide_hook_stop",
        }
        with (TRACE / "bob_turns.jsonl").open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        tool_count = 0

    # --- Publication JOB_COMPLETED vers ARTCB ---
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from src.artcb.bob.job_completed import publish_job_completed, flush_outbox

        artcb_result = publish_job_completed(
            session_id=session_id,
            last_assistant_message=last_msg,
            tool_count=tool_count,
        )

        # Mettre à jour bob_turns.jsonl avec artcb_bound=True si commis
        artcb_status = artcb_result.get("artcb_status", "error")
        if artcb_status in {"committed", "already_committed"}:
            try:
                update_row = {
                    "ts_ns": time.time_ns(),
                    "kind": "bob_stop_artcb_commit",
                    "session_id": session_id,
                    "artcb_bound": True,
                    "event_id": artcb_result.get("event_id"),
                    "job_id": artcb_result.get("job_id"),
                    "block_index": artcb_result.get("block_index"),
                    "block_hash": artcb_result.get("block_hash"),
                    "graph_id": artcb_result.get("graph_id"),
                    "raw_hash": artcb_result.get("raw_hash"),
                    "includes_thinking": False,
                    "includes_system_prompt": False,
                }
                with (TRACE / "bob_turns.jsonl").open("a") as fh:
                    fh.write(json.dumps(update_row, ensure_ascii=False) + "\n")
            except Exception:
                pass

        # Retry outbox (spooled précédents)
        try:
            flush_outbox()
        except Exception:
            pass

    except Exception:
        # Fail-open : ne jamais bloquer la fin de tour Bob
        artcb_result = {"artcb_status": "error", "note": "bob_job_completed_unavailable"}

    # --- R394-C : Auto-feedback post-session (fail-open) ---
    try:
        import subprocess as _sp
        _sp.run(
            ["python3", "scripts/artcb_r392_auto_feedback.py", "--since", "HEAD~1"],
            cwd=str(ROOT),
            timeout=25,
            capture_output=True,  # ne pas polluer stdout du hook
        )
    except Exception:
        pass  # fail-open — ne jamais bloquer la fin de session

    # --- Stdout → contexte Bob ---
    status = artcb_result.get("artcb_status", "error")
    event_id = artcb_result.get("event_id", "?")
    block_idx = artcb_result.get("block_index", "?")
    block_hash = artcb_result.get("block_hash", "?")
    if status in {"committed", "already_committed"}:
        print(f"[ARTCB JOB_COMPLETED] ✅ {status} | event={event_id[:16]}... | block={block_idx} | hash={str(block_hash)[:12]}...")
    elif status == "spooled":
        print(f"[ARTCB JOB_COMPLETED] 📦 spooled (ARTCB indisponible) | event={event_id[:16]}... | outbox={artcb_result.get('outbox','?')}")
    else:
        print(f"[ARTCB JOB_COMPLETED] ⚠️  {status} — trace locale conservée")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
