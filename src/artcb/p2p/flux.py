"""P2P / official-replica flux log — real network timings, not invented.

Append-only JSONL at ``data/p2p/flux.jsonl``. One row per chunk.
The 1065 ingest POSTs to OVH1 produced no inter-node rows — that send
never left the node. Rows appear only when a real push/pull/replica runs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FLUX_REL = Path("p2p") / "flux.jsonl"
MAX_ROWS_DEFAULT = 200


def flux_path(data_dir: Path) -> Path:
    return Path(data_dir) / FLUX_REL


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_flux(data_dir: Path, row: dict[str, Any]) -> dict[str, Any]:
    record = {"ts": now_iso(), **row}
    path = flux_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return record


def list_flux(data_dir: Path, *, limit: int = MAX_ROWS_DEFAULT) -> list[dict[str, Any]]:
    path = flux_path(data_dir)
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
            if isinstance(parsed, dict):
                rows.append(parsed)
    cap = max(1, min(int(limit or MAX_ROWS_DEFAULT), 2000))
    return rows[-cap:]


def summarize_flux(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r.get("ok") is True]
    err = [r for r in rows if r.get("ok") is False]
    rtts = [float(r["rtt_ms"]) for r in ok if isinstance(r.get("rtt_ms"), (int, float))]
    bytes_wire = [int(r["bytes_wire"]) for r in ok if isinstance(r.get("bytes_wire"), (int, float))]
    pushed = sum(int(r.get("pushed") or 0) for r in ok)
    imported = sum(int(r.get("imported") or 0) for r in ok)
    return {
        "rows": len(rows),
        "ok": len(ok),
        "errors": len(err),
        "pushed_blocks": pushed,
        "imported_blocks": imported,
        "bytes_wire_ok": sum(bytes_wire),
        "rtt_ms_min": min(rtts) if rtts else None,
        "rtt_ms_max": max(rtts) if rtts else None,
        "rtt_ms_avg": round(sum(rtts) / len(rtts), 2) if rtts else None,
        "ingest_1065_had_no_inter_node_flux": True,
    }
