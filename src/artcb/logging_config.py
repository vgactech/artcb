"""Configuration logging ARTCB — mode DEBUG par défaut (PROTOCOLE).

Nommage des fichiers de log :
    YYYYMMDD_artcb_startup_<node_suffix>.json

<node_suffix> est dérivé de ARTCB_NODE_WALLET_ADDRESS (8 derniers chars
de l'adresse wallet) ou du hostname si la variable n'est pas encore
disponible au moment du logging. Cela garantit que N1 et N2 (ou toute
machine différente travaillant sur le même clone git) produisent des
fichiers de log distincts et ne se pileront pas mutuellement lors d'un
commit/push.

Exemples :
  N1 → logs/20260808_artcb_startup_n1.artcb.me.json
  N2 → logs/20260808_artcb_startup_n2.artcb.me.json
  Dev local → logs/20260808_artcb_startup_artcb1abc123.json
"""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import UTC, datetime
from pathlib import Path


def _node_suffix() -> str:
    """Retourne un suffixe unique à ce nœud pour les noms de fichiers de log.

    Ordre de priorité :
    1. ARTCB_NODE_WALLET_ADDRESS  → 12 derniers chars de l'adresse wallet
    2. ARTCB_NODE_PUBLIC_URL      → hostname extrait de l'URL
    3. Hostname système           → fallback final
    """
    wallet = os.getenv("ARTCB_NODE_WALLET_ADDRESS", "").strip()
    if wallet:
        # "artcb1q3r5m6kz9p2..." → "kz9p2..." (12 derniers chars = unique et lisible)
        return wallet[-12:]
    url = os.getenv("ARTCB_NODE_PUBLIC_URL", "").strip()
    if url:
        # "https://n1.artcb.me" → "n1.artcb.me"
        return url.split("//", 1)[-1].rstrip("/").split("/")[0]
    return socket.gethostname()


class JsonLineFormatter(logging.Formatter):
    """JSONL formatter shared by every ARTCB logger in one startup run."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "startup_id": os.getenv("ARTCB_STARTUP_ID"),
            "node": _node_suffix(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _debug_enabled() -> bool:
    value = os.getenv("ARTCB_DEBUG", "true").lower()
    return value in {"1", "true", "yes", "on"}


def setup_logging(module: str) -> logging.Logger:
    level_name = os.getenv("ARTCB_LOG_LEVEL", "DEBUG" if _debug_enabled() else "INFO")
    level = getattr(logging, level_name.upper(), logging.DEBUG)

    log_dir = Path(os.getenv("ARTCB_LOG_DIR", "./logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    # Nom de fichier unique par nœud — évite les collisions lors des pulls
    # entre N1, N2 et la machine de dev locale travaillant sur le même clone.
    node_sfx = _node_suffix()
    file_path = log_dir / f"{datetime.now(UTC).strftime('%Y%m%d')}_artcb_startup_{node_sfx}.json"
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not any(
        getattr(handler, "_artcb_startup_file", False)
        and getattr(handler, "baseFilename", None) == str(file_path.resolve())
        for handler in root_logger.handlers
    ):
        root_file_handler = logging.FileHandler(file_path, encoding="utf-8")
        root_file_handler.setFormatter(JsonLineFormatter())
        root_file_handler._artcb_startup_file = True
        root_logger.addHandler(root_file_handler)

    if not any(getattr(handler, "_artcb_startup_stream", False) for handler in root_logger.handlers):
        root_stream_handler = logging.StreamHandler()
        root_stream_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root_stream_handler._artcb_startup_stream = True
        root_logger.addHandler(root_stream_handler)

    logger = logging.getLogger(module)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = True

    # Uvicorn installs its own handlers during startup. Route its records
    # through the ARTCB root handler so access/error logs share the JSONL run.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.setLevel(level)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    return logger
