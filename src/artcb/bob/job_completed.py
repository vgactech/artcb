"""ARTCB — Bob IDE → JOB_COMPLETED persistence.

Transforme la fin d'un tour Bob en événement durable gravé dans ARTCB.

Architecture :
  - Collecte les traces brutes depuis data/trace/*.jsonl (outils, prompts, turns)
  - Produit un paquet JOB_COMPLETED structuré (raw_tool_events, raw_outputs, etc.)
  - Hash SHA-256 du contenu (raw_hash)
  - Tente la publication vers ARTCB via POST /api/v1/agent/events (idempotent)
  - En cas d'échec réseau → spooling dans data/trace/outbox/ (retry automatique)
  - Retourne block_index + block_hash + graph_id si commis

Règles absolues :
  - includes_thinking = False  (thinking interne jamais transmis)
  - includes_system_prompt = False
  - Aucun secret / credential / private_key dans le paquet
  - Idempotence : même event_id → already_committed (pas de doublon)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ARTCB_API_URL = os.environ.get("ARTCB_API_URL", "http://152.228.144.34:8000")
ARTCB_API_KEY = os.environ.get("ARTCB_API_KEY", "")

# Patterns de secrets à redacter avant tout envoi
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"dp\.st\.[A-Za-z0-9._-]{10,}", re.I),        # tokens Doppler
    re.compile(r"artcb_[a-f0-9]{40,}", re.I),                # API keys ARTCB
    re.compile(r"-----BEGIN.*?PRIVATE KEY-----.*?-----END.*?PRIVATE KEY-----", re.S),
    re.compile(r"\"(password|secret|private_key|seed_hex|token)\"\s*:\s*\"[^\"]{4,}\"", re.I),
    re.compile(r"amelie92"),                                   # mot de passe connu exposé
]

OUTBOX_DIR = Path(__file__).resolve().parents[3] / "data" / "trace" / "outbox"
TRACE_DIR = Path(__file__).resolve().parents[3] / "data" / "trace"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact_secrets(text: str) -> str:
    """Remplace les secrets détectés par [REDACTED]."""
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_sha() -> str:
    try:
        root = Path(__file__).resolve().parents[3]
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root), text=True, timeout=5,
        ).strip()
    except Exception:
        return "unknown"


def _git_changed_files() -> list[str]:
    """Fichiers modifiés depuis le dernier commit."""
    try:
        root = Path(__file__).resolve().parents[3]
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(root), text=True, timeout=5,
        )
        return [f.strip() for f in out.splitlines() if f.strip()]
    except Exception:
        return []


def _read_jsonl_tail(path: Path, n: int = 50) -> list[dict[str, Any]]:
    """Lit les n dernières lignes d'un fichier JSONL."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        return []
    return rows[-n:]


def _redact_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Applique _redact_secrets sur chaque valeur string de chaque ligne."""
    result = []
    for row in rows:
        cleaned: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, str):
                cleaned[k] = _redact_secrets(v)
            else:
                cleaned[k] = v
        result.append(cleaned)
    return result


def _collect_raw_traces(session_id: str | None) -> dict[str, Any]:
    """Collecte et redacte les traces brutes pertinentes pour cette session.

    CORRECTION P0-A : la redaction est appliquée ICI, avant toute écriture
    sur disque (outbox) et avant le POST. Le paquet final ne contient jamais
    de données brutes non redactées.
    """
    def _filter(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not session_id:
            return rows
        return [r for r in rows if r.get("session_id") == session_id or "session_id" not in r]

    tool_rows  = _redact_rows(_filter(_read_jsonl_tail(TRACE_DIR / "bob_tool_usage.jsonl", 200)))
    turn_rows  = _redact_rows(_filter(_read_jsonl_tail(TRACE_DIR / "bob_turns.jsonl", 50)))
    prompt_rows = _redact_rows(_filter(_read_jsonl_tail(TRACE_DIR / "bob_prompts.jsonl", 50)))
    pretool_rows = _redact_rows(_filter(_read_jsonl_tail(TRACE_DIR / "bob_pretooluse.jsonl", 200)))

    return {
        "raw_tool_events": tool_rows,
        "raw_turns": turn_rows,
        "raw_prompts": prompt_rows,
        "raw_pretool_events": pretool_rows,
        "includes_thinking": False,
        "includes_system_prompt": False,
    }


def _make_event_id(
    *,
    repo_sha: str,
    session_id: str | None,
    prompt_hash: str,
    tool_hash: str,
) -> str:
    """Identifiant déterministe — CORRECTION P0-B : aucun timestamp dans l'identité.

    Même travail logique (même repo_sha + session + prompts + outils)
    → même event_id, quelle que soit l'heure de la tentative.
    """
    canonical = json.dumps({
        "repo_sha": repo_sha,
        "session_id": session_id or "nosession",
        "prompt_hash": prompt_hash,
        "tool_hash": tool_hash,
    }, sort_keys=True, ensure_ascii=False)
    return "evt_" + hashlib.sha256(canonical.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Paquet JOB_COMPLETED
# ---------------------------------------------------------------------------

def build_job_completed(
    *,
    session_id: str | None = None,
    last_assistant_message: str = "",
    tool_count: int = 0,
    error_count: int = 0,
    status: str = "completed",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit le paquet JOB_COMPLETED — trace brute redactée, aucun résumé.

    P0-A : toutes les traces sont redactées AVANT toute écriture sur disque.
    P0-B : event_id déterministe — aucun timestamp dans l'identité logique.
    """
    ts_ns = time.time_ns()
    repo_sha = _git_sha()
    changed_files = _git_changed_files()

    # Traces collectées ET redactées dès la collecte (P0-A)
    raw_traces = _collect_raw_traces(session_id)

    # Redaction du message assistant
    raw_output = _redact_secrets(last_assistant_message)

    # Hashes canoniques pour l'identité déterministe (P0-B)
    prompt_hash = _sha256(json.dumps(raw_traces["raw_prompts"], sort_keys=True, ensure_ascii=False))
    tool_hash   = _sha256(json.dumps(raw_traces["raw_tool_events"], sort_keys=True, ensure_ascii=False))

    # event_id : déterministe, sans timestamp (P0-B)
    event_id = _make_event_id(
        repo_sha=repo_sha,
        session_id=session_id,
        prompt_hash=prompt_hash,
        tool_hash=tool_hash,
    )

    # job_id : dérivé de l'event_id (déterministe aussi)
    job_id = "job_" + hashlib.sha256(event_id.encode()).hexdigest()[:24]

    # Hash du contenu canonique (calculé sur les données déjà redactées)
    canonical = json.dumps({
        "event_id": event_id,
        "session_id": session_id,
        "repo_sha": repo_sha,
        "raw_output": raw_output,
        "tool_hash": tool_hash,
        "prompt_hash": prompt_hash,
        "changed_files": changed_files,
    }, sort_keys=True, ensure_ascii=False)
    raw_hash = _sha256(canonical)

    # Paquet final : 100 % redacté — prêt pour outbox ET pour POST (P0-A)
    packet: dict[str, Any] = {
        "event_type": "JOB_COMPLETED",
        "event_id": event_id,
        "job_id": job_id,
        "session_id": session_id,
        "provider": "bob",
        "agent_id": "bob_ide_agent",
        "repo": "vgactech/artcb",
        "repo_sha": repo_sha,
        "completed_at_ns": ts_ns,
        "completed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_ns / 1e9)),
        "status": status,
        "tool_count": tool_count,
        "error_count": error_count,
        "changed_files": changed_files,
        # Traces brutes redactées (P0-A)
        "raw_output": raw_output,
        "raw_tool_events": raw_traces["raw_tool_events"],
        "raw_turns": raw_traces["raw_turns"],
        "raw_prompts": raw_traces["raw_prompts"],
        "raw_pretool_events": raw_traces["raw_pretool_events"],
        # Hashes d'identité (P0-B)
        "prompt_hash": prompt_hash,
        "tool_hash": tool_hash,
        # Intégrité
        "raw_hash": raw_hash,
        "content_sha256": raw_hash,
        # Sécurité
        "includes_thinking": False,
        "includes_system_prompt": False,
        "secrets_redacted": True,
        "redaction_applied_before_outbox": True,
        "visibility": "private",
    }
    if extra:
        packet.update(extra)
    return packet


# ---------------------------------------------------------------------------
# Publication ARTCB
# ---------------------------------------------------------------------------

def _post_to_artcb(packet: dict[str, Any]) -> dict[str, Any]:
    """Envoie le paquet vers POST /api/v1/agent/events.

    P0-A : le packet est déjà entièrement redacté à ce stade.
    La redaction ici est une dernière passe de sécurité défensive,
    mais ne doit pas être le seul point de protection.
    """
    import urllib.request
    import urllib.error

    # Le packet est déjà redacté (P0-A) — sérialisation directe
    # La passe _redact_secrets est conservée comme défense en profondeur
    content = _redact_secrets(json.dumps(packet, ensure_ascii=False))

    body = json.dumps({
        "event_id": packet["event_id"],
        "kind": "job_completed",
        "content": content,
        "visibility": packet.get("visibility", "private"),
        "tags": ["bob_ide", "job_completed", "artcb_trace"],
        "session_id": packet.get("session_id") or "bob_session",
    }).encode("utf-8")

    url = f"{ARTCB_API_URL.rstrip('/')}/api/v1/agent/events"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ARTCB_API_KEY}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_err = exc.read().decode("utf-8", errors="replace")[:512]
        return {"status": "http_error", "code": exc.code, "detail": body_err}
    except Exception as exc:
        return {"status": "network_error", "detail": str(exc)}


def _spool_outbox(packet: dict[str, Any]) -> Path:
    """Sauvegarde le paquet dans l'outbox locale pour retry ultérieur."""
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    fname = OUTBOX_DIR / f"job_completed_{packet['event_id']}.json"
    fname.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
    fname.chmod(0o600)
    return fname


def _mark_outbox_committed(packet: dict[str, Any], result: dict[str, Any]) -> None:
    """Met à jour le fichier outbox avec le résultat du commit."""
    fname = OUTBOX_DIR / f"job_completed_{packet['event_id']}.json"
    if fname.exists():
        merged = {**packet, "artcb_commit": result, "artcb_committed_at": time.time()}
        fname.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")


def flush_outbox() -> list[dict[str, Any]]:
    """Tente de rejouer tous les événements en attente dans l'outbox."""
    if not OUTBOX_DIR.exists():
        return []
    results = []
    for f in sorted(OUTBOX_DIR.glob("job_completed_*.json")):
        try:
            packet = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if packet.get("artcb_commit", {}).get("status") in {"committed", "already_committed"}:
            continue  # déjà commis
        result = _post_to_artcb(packet)
        status = result.get("status")
        if status in {"committed", "already_committed"}:
            _mark_outbox_committed(packet, result)
        results.append({"event_id": packet.get("event_id"), "status": status, "detail": result})
    return results


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def publish_job_completed(
    *,
    session_id: str | None = None,
    last_assistant_message: str = "",
    tool_count: int = 0,
    error_count: int = 0,
    status: str = "completed",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit + publie un JOB_COMPLETED.

    Returns:
        dict avec les clés :
          - event_id, job_id, raw_hash
          - artcb_status : "committed" | "already_committed" | "spooled" | "error"
          - block_index, block_hash, graph_id (si commis)
    """
    packet = build_job_completed(
        session_id=session_id,
        last_assistant_message=last_assistant_message,
        tool_count=tool_count,
        error_count=error_count,
        status=status,
        extra=extra,
    )

    # Spooling local immédiat (preuve locale avant envoi réseau)
    _spool_outbox(packet)

    # Tentative publication ARTCB
    result = _post_to_artcb(packet)
    artcb_status = result.get("status", "error")

    if artcb_status in {"committed", "already_committed"}:
        _mark_outbox_committed(packet, result)
        return {
            "event_id": packet["event_id"],
            "job_id": packet["job_id"],
            "raw_hash": packet["raw_hash"],
            "artcb_status": artcb_status,
            "block_index": result.get("memo", {}).get("block_index") or result.get("block_index"),
            "block_hash": result.get("memo", {}).get("block_hash") or result.get("block_hash"),
            "graph_id": result.get("memo", {}).get("graph_id") or result.get("graph_id"),
            "includes_thinking": False,
            "includes_system_prompt": False,
        }

    # ARTCB indisponible → spoolé, sera rejoué
    return {
        "event_id": packet["event_id"],
        "job_id": packet["job_id"],
        "raw_hash": packet["raw_hash"],
        "artcb_status": "spooled",
        "artcb_error": result,
        "outbox": str(OUTBOX_DIR / f"job_completed_{packet['event_id']}.json"),
        "includes_thinking": False,
        "includes_system_prompt": False,
    }
