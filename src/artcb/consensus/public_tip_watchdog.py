"""R328 — public tip stall watchdog + controlled auto VIEW-CHANGE.

Hypothesis split (operator):
  (a) timer broken despite pending PRE-PREPARE
  (b) no pending request ever reached primary (entry-path 409)

This module records both signals. Auto VIEW-CHANGE only runs when
``ARTCB_PUBLIC_TIP_WATCHDOG=1`` (default on official compute) and the
public tip age exceeds ``ARTCB_PUBLIC_TIP_STALL_SEC`` (default 900).

2026-09-12T19:10:00Z
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.consensus.public_tip_watchdog")

_STATE_NAME = "consensus/public_tip_watchdog.json"
_thread: threading.Thread | None = None
_stop = threading.Event()


def _data_dir(chain: Any) -> Path:
    return Path(chain.blocks_path).parent.parent


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 8.0) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            payload = {"detail": str(exc.reason)}
        return int(exc.code), payload if isinstance(payload, dict) else {"detail": str(payload)}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:160]}


def _parse_ts(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


def diagnose(chain: Any, *, pbft_log: Any | None = None) -> dict[str, Any]:
    """Classify stall cause without mutating consensus state."""
    split = chain.tip_public_private()
    pub_ts = _parse_ts(split.get("public_last_timestamp"))
    now = time.time()
    age_sec = (now - pub_ts) if pub_ts is not None else None
    pending_prepares = 0
    pending_detail: list[dict[str, Any]] = []
    if pbft_log is not None:
        try:
            prepared = list(pbft_log.prepared_set() or [])
            for row in prepared:
                if not isinstance(row, dict):
                    continue
                seq = int(row.get("seq") or -1)
                already = False
                try:
                    if chain._split_active():
                        already = chain.public_book().get_by_consensus_index(seq) is not None
                    else:
                        tip = chain.tip_public_private()
                        already = int(tip.get("public_last_index") or -1) >= seq
                except Exception:  # noqa: BLE001
                    already = False
                if not already:
                    pending_prepares += 1
                    pending_detail.append({"seq": seq, "digest": str(row.get("digest") or "")[:16]})
        except Exception as exc:  # noqa: BLE001
            pending_detail.append({"error": str(exc)[:120]})
    hypothesis = "unknown"
    if age_sec is not None and age_sec > 60:
        if pending_prepares > 0:
            hypothesis = "a_timer_or_progress_stuck_with_pending"
        else:
            hypothesis = "b_no_pending_pre_prepare_entry_path"
    return {
        "public_last_index": split.get("public_last_index"),
        "public_last_hash": str(split.get("public_last_hash") or "")[:16],
        "public_last_timestamp": split.get("public_last_timestamp"),
        "age_sec": age_sec,
        "private_suffix_lines": split.get("private_suffix_lines"),
        "ledger_mode": split.get("ledger_mode"),
        "pending_prepares": pending_prepares,
        "pending_detail": pending_detail[:8],
        "hypothesis": hypothesis,
        "ts_ns": time.time_ns(),
    }


def _persist(data_dir: Path, row: dict[str, Any]) -> None:
    path = data_dir / _STATE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    try:
        from src.artcb.trace.ns import emit

        emit(data_dir, {"kind": "public_tip_watchdog", **row})
    except Exception:  # noqa: BLE001
        pass


def maybe_trigger_view_change(
    *,
    local_base: str,
    chain: Any,
    reason: str,
) -> dict[str, Any]:
    """Emit local VIEW-CHANGE for view+1. Does not wipe. Best-effort fan-out."""
    code, view_body = _http_json("GET", f"{local_base}/api/v1/consensus/pbft/view")
    if code != 200:
        return {"ok": False, "reason": f"view_http_{code}", "body": view_body}
    cur = int((view_body or {}).get("view") or 0)
    target = cur + 1
    split = chain.tip_public_private()
    height = int(split.get("public_last_index") or -1) + 1
    last_hash = str(split.get("public_last_hash") or "")
    vc_code, vc_body = _http_json(
        "POST",
        f"{local_base}/api/v1/consensus/pbft/view-change",
        {
            "view": target,
            "reason": reason[:200],
        },
    )
    return {
        "ok": vc_code in (200, 201),
        "http": vc_code,
        "from_view": cur,
        "to_view": target,
        "height_public_next": height,
        "last_hash_public": last_hash[:16],
        "body": vc_body,
    }


def tick(chain: Any, *, local_base: str, pbft_log: Any | None = None) -> dict[str, Any]:
    stall_sec = float(os.environ.get("ARTCB_PUBLIC_TIP_STALL_SEC") or "900")
    diag = diagnose(chain, pbft_log=pbft_log)
    action: dict[str, Any] = {"triggered": False}
    age = diag.get("age_sec")
    if age is not None and age >= stall_sec:
        logger.warning(
            "R328 public tip stall age_sec=%.0f hypothesis=%s pending=%s",
            age,
            diag.get("hypothesis"),
            diag.get("pending_prepares"),
        )
        if str(os.environ.get("ARTCB_PUBLIC_TIP_AUTO_VC", "1")).strip() not in (
            "0",
            "false",
            "False",
            "no",
        ):
            action = maybe_trigger_view_change(
                local_base=local_base,
                chain=chain,
                reason=f"public_tip_watchdog:{diag.get('hypothesis')}:age={int(age)}",
            )
            action["triggered"] = bool(action.get("ok"))
    row = {**diag, "action": action, "stall_threshold_sec": stall_sec}
    _persist(_data_dir(chain), row)
    return row


def start_background(chain: Any, *, local_base: str | None = None, pbft_log: Any | None = None) -> bool:
    """Daemon thread. Idempotent. Honours ARTCB_PUBLIC_TIP_WATCHDOG (default 1)."""
    global _thread
    if str(os.environ.get("ARTCB_PUBLIC_TIP_WATCHDOG", "1")).strip() in ("0", "false", "False", "no"):
        return False
    if _thread is not None and _thread.is_alive():
        return True
    base = (local_base or os.environ.get("ARTCB_LOCAL_BASE") or "http://127.0.0.1:8000").rstrip("/")
    interval = float(os.environ.get("ARTCB_PUBLIC_TIP_WATCHDOG_INTERVAL_SEC") or "60")

    def _loop() -> None:
        while not _stop.wait(interval):
            try:
                tick(chain, local_base=base, pbft_log=pbft_log)
            except Exception:  # noqa: BLE001
                logger.exception("public_tip_watchdog tick failed")

    _stop.clear()
    _thread = threading.Thread(target=_loop, name="artcb-public-tip-watchdog", daemon=True)
    _thread.start()
    logger.info("R328 public tip watchdog started interval=%ss base=%s", interval, base)
    return True
