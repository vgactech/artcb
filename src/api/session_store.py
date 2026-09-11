"""Session store durable — R322 (2026-09-11T21:40:00Z).

R320 stockait les sessions en mémoire process → restart = toutes sessions mortes.
Ce module persiste ``token_hash → record`` sous ``{ARTCB_DATA_DIR}/auth/sessions.json``
(hashes seulement — jamais le bearer brut ``sess_``).

Compat : API identique pour auth_routes (dict mutable partagé + flush).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.api.session_store")

_lock = threading.RLock()
_loaded = False


def sessions_path() -> Path:
    root = Path(os.getenv("ARTCB_DATA_DIR", "data"))
    return root / "auth" / "sessions.json"


def load_sessions(into: dict[str, dict[str, Any]]) -> int:
    """Charge le fichier dans ``into`` (merge). Retourne le nombre de records lus."""
    global _loaded
    path = sessions_path()
    with _lock:
        if not path.is_file():
            _loaded = True
            return 0
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("session store illisible %s : %s", path, type(exc).__name__)
            _loaded = True
            return 0
        if not isinstance(raw, dict):
            _loaded = True
            return 0
        now = time.time()
        n = 0
        for h, rec in raw.items():
            if not isinstance(h, str) or not isinstance(rec, dict):
                continue
            if float(rec.get("expires_at") or 0) <= now:
                continue
            into[h] = rec
            n += 1
        _loaded = True
        return n


def ensure_loaded(into: dict[str, dict[str, Any]]) -> None:
    if not _loaded:
        load_sessions(into)


def save_sessions(sessions: dict[str, dict[str, Any]]) -> None:
    """Écrit atomiquement le snapshot courant (records non expirés)."""
    path = sessions_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        payload = {
            h: rec
            for h, rec in sessions.items()
            if isinstance(rec, dict) and float(rec.get("expires_at") or 0) > now
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        tmp.replace(path)


def reset_for_tests() -> None:
    """Pytest only — vide le flag de charge (pas le fichier)."""
    global _loaded
    with _lock:
        _loaded = False
