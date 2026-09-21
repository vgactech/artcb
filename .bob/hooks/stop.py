#!/usr/bin/env python3
"""Bob IDE — Stop hook.

À la fin de chaque tour :
  - Archive le dernier message assistant + métadonnées dans bob_turns.jsonl
  - Publie un événement JOB_COMPLETED vers ARTCB via src.artcb.bob.job_completed
    (idempotent, outbox locale si ARTCB indisponible, retry via flush_outbox)
  - Tente aussi de rejouer les événements en attente (outbox flush)
  - Lance R392 auto-feedback et persiste AUDIT_STATUS (OK / FAILED / INCOMPLETE)
    R396-A : le returncode est contrôlé — l'échec ne bloque pas Bob mais devient observable.

Règle R396 : FAIL-OPEN EXECUTION, FAIL-CLOSED AUDIT STATUS.
  Une panne de feedback ne tue pas le tour, mais audit_status ≠ "ok" par défaut.

Jamais de secrets. includes_thinking=False toujours.
"""
from __future__ import annotations
import hashlib, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "data" / "trace"

# R396-A — Statuts d'audit possibles
AUDIT_OK = "ok"
AUDIT_FAILED = "failed"
AUDIT_INCOMPLETE = "incomplete"


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

    # --- R396-A : Auto-feedback post-session — FAIL-OPEN EXECUTION, FAIL-CLOSED AUDIT STATUS ---
    audit_status = AUDIT_INCOMPLETE
    audit_detail: dict = {}
    try:
        result = subprocess.run(
            ["python3", "scripts/artcb_r392_auto_feedback.py", "--since", "HEAD~1"],
            cwd=str(ROOT),
            timeout=25,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            audit_status = AUDIT_OK
            audit_detail = {"returncode": 0, "stderr_chars": len(result.stderr or "")}
        else:
            audit_status = AUDIT_FAILED
            audit_detail = {
                "returncode": result.returncode,
                "stderr": (result.stderr or "")[:400],  # tronqué, jamais de secrets
            }
    except subprocess.TimeoutExpired:
        audit_status = AUDIT_FAILED
        audit_detail = {"error": "timeout_expired", "timeout_s": 25}
    except Exception as exc:
        audit_status = AUDIT_FAILED
        audit_detail = {"error": type(exc).__name__, "msg": str(exc)[:200]}

    # Persistance de l'audit_status dans bob_turns.jsonl — toujours écrit, même en échec
    try:
        TRACE.mkdir(parents=True, exist_ok=True)
        audit_row = {
            "ts_ns": time.time_ns(),
            "kind": "bob_stop_audit",
            "session_id": session_id,
            "agent_id": "bob",
            "audit_status": audit_status,
            "feedback_script": "scripts/artcb_r392_auto_feedback.py",
            **audit_detail,
            "note": "R396-A — FAIL-OPEN execution, FAIL-CLOSED audit status",
        }
        with (TRACE / "bob_turns.jsonl").open("a") as fh:
            fh.write(json.dumps(audit_row, ensure_ascii=False) + "\n")
    except Exception:
        pass  # ne jamais bloquer la fin de session même si la trace échoue

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

    # R396-A — audit status toujours visible dans stdout
    audit_icon = {"ok": "✅", "failed": "❌", "incomplete": "⚠️"}.get(audit_status, "?")
    print(f"[ARTCB AUDIT] {audit_icon} feedback={audit_status} | agent=bob | session={session_id or '?'}")

    # --- R402 : Post-push health check artcb.me — FAIL-OPEN, visible dans stdout ---
    # Déclenché à chaque fin de session pour détecter les pannes immédiatement après push.
    # Ne bloque jamais la fin de tour. Résumé compact affiché.
    try:
        health_result = subprocess.run(
            ["python3", "scripts/artcb_r402_post_push_health.py", "--timeout", "12", "--quiet"],
            cwd=str(ROOT),
            timeout=45,          # 3 nœuds × 12s max + marge
            capture_output=True,
            text=True,
        )
        health_status = "ok" if health_result.returncode == 0 else "degraded_or_down"
        # Écriture trace nanoseconde
        try:
            TRACE.mkdir(parents=True, exist_ok=True)
            health_row = {
                "ts_ns": time.time_ns(),
                "kind": "bob_stop_health_check",
                "session_id": session_id,
                "health_status": health_status,
                "returncode": health_result.returncode,
                "stdout_tail": (health_result.stdout or "")[-200:],
                "note": "R402 — artcb.me + N2/N4/N3 IP directe",
            }
            with (TRACE / "bob_turns.jsonl").open("a") as fh:
                fh.write(json.dumps(health_row, ensure_ascii=False) + "\n")
        except Exception:
            pass
        health_icon = "✅" if health_result.returncode == 0 else "❌"
        # Affichage résumé compact (1 ligne) sans bloquer
        nodes_line = ""
        for line in (health_result.stdout or "").splitlines():
            if "nœuds UP" in line:
                nodes_line = line.strip()
                break
        print(f"[ARTCB HEALTH] {health_icon} {nodes_line or health_status}")
    except subprocess.TimeoutExpired:
        print("[ARTCB HEALTH] ⚠️ health check timeout (45s) — non bloquant")
    except Exception as exc:
        print(f"[ARTCB HEALTH] ⚠️ health check erreur: {type(exc).__name__}: {str(exc)[:80]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
