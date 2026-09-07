#!/usr/bin/env python3
"""Push the local official book to the other three compute nodes.

Must run on an official node (typically OVH1) after follow-main, or call
POST /api/v1/p2p/replica/run on that node with the operator bearer.

Never prints the token. Never wipes blocks.jsonl.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _url() -> str:
    return (os.environ.get("ARTCB_REPLICA_URL") or "http://127.0.0.1:8000").rstrip("/")


def _key() -> str:
    return (os.environ.get("ARTCB_API_KEY") or "").strip()


def _http(method: str, path: str, *, auth: bool = False, timeout: int = 900) -> dict:
    url = f"{_url()}{path}"
    headers = {"Accept": "application/json"}
    if auth:
        key = _key()
        if len(key) < 16:
            return {"ok": False, "error": "ARTCB_API_KEY missing on this process"}
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, method=method, headers=headers)
    ctx = ssl._create_unverified_context() if url.startswith("https") else None
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            code = resp.status
        parsed = json.loads(body) if body.strip().startswith("{") else {"raw": body[:400]}
        return {"ok": code == 200, "http": code, "rtt_ms": round((time.perf_counter() - t0) * 1000, 1), **parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:400]
        return {"ok": False, "http": exc.code, "error": raw, "rtt_ms": round((time.perf_counter() - t0) * 1000, 1)}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "http": 0, "error": type(exc).__name__, "rtt_ms": round((time.perf_counter() - t0) * 1000, 1)}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    before = _http("GET", "/api/v1/chain/status")
    run = _http("POST", "/api/v1/p2p/replica/run?include_files=true", auth=True, timeout=1200)
    flux = _http("GET", "/api/v1/p2p/flux?limit=500")
    after = _http("GET", "/api/v1/chain/status")
    payload = {
        "stamp": stamp,
        "local_url": _url(),
        "before": {"height": before.get("height"), "last_hash": before.get("last_hash"), "http": before.get("http")},
        "run": run,
        "flux_summary": flux.get("summary"),
        "after": {"height": after.get("height"), "last_hash": after.get("last_hash"), "http": after.get("http")},
        "token_printed": False,
    }
    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / f"251_replica_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "251_replica_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(dest),
                "local_height": after.get("height"),
                "run_ok": run.get("ok"),
                "peers": [
                    {
                        "node_id": p.get("node_id"),
                        "host": p.get("host"),
                        "ok": p.get("ok"),
                        "height_before": p.get("height_before"),
                        "height_after": p.get("height_after"),
                    }
                    for p in (run.get("peers") or [])
                ],
                "flux_summary": flux.get("summary"),
            },
            indent=2,
        )
    )
    return 0 if run.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
