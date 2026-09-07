"""Nanosecond end-to-end trace — every HTTP hit and every book write.

Operator GO 2026-09-07: log at nanosecond granularity even if it costs
latency. The point is to see real gaps, not to be fast.

Never writes tokens, PEM, or block bodies. Path + timing + status only.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

TRACE_REL = Path("trace") / "ns.jsonl"
MAX_LIST = 2000


def now_wall_ns() -> int:
    return time.time_ns()


def now_mono_ns() -> int:
    return time.perf_counter_ns()


def trace_path(data_dir: Path) -> Path:
    return Path(data_dir) / TRACE_REL


def emit(data_dir: Path | None, row: dict[str, Any]) -> dict[str, Any]:
    record = {
        "ts_ns": now_wall_ns(),
        "mono_ns": now_mono_ns(),
        "pid": os.getpid(),
        **row,
    }
    if data_dir is None:
        return record
    path = trace_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return record


def list_traces(data_dir: Path, *, limit: int = 200, kind: str | None = None) -> list[dict[str, Any]]:
    path = trace_path(data_dir)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            if kind and parsed.get("kind") != kind:
                continue
            rows.append(parsed)
    cap = max(1, min(int(limit or 200), MAX_LIST))
    return rows[-cap:]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    durs = [int(r["dur_ns"]) for r in rows if isinstance(r.get("dur_ns"), (int, float))]
    by_kind: dict[str, int] = {}
    errors = 0
    for row in rows:
        k = str(row.get("kind") or "?")
        by_kind[k] = by_kind.get(k, 0) + 1
        if row.get("ok") is False:
            errors += 1
    return {
        "rows": len(rows),
        "errors": errors,
        "by_kind": by_kind,
        "dur_ns_min": min(durs) if durs else None,
        "dur_ns_max": max(durs) if durs else None,
        "dur_ns_avg": int(sum(durs) / len(durs)) if durs else None,
        "dur_ms_avg": round((sum(durs) / len(durs)) / 1_000_000, 3) if durs else None,
    }
