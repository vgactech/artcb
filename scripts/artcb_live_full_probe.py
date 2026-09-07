#!/usr/bin/env python3
"""Hit every developed live surface on the four official nodes.

Safe GETs from OpenAPI. Curated POSTs that do not wipe the book.
The book itself is exercised by verify/status/search/block + one
operator-authorized /ai/memo (agent memory) when --memo is passed.

Never prints the token.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODES = {
    "ovh-node-1": "http://152.228.144.34:8000",
    "ovh-node-2": "http://151.80.107.29:8000",
    "aws-node-3": "http://51.44.222.232:8000",
    "ovh-node-4": "http://91.134.45.8:8000",
}
SKIP_GET_PREFIXES = (
    "/setup/init-node",
)
# These never return (SSE / long-poll) or require params.
SKIP_GET_EXACT = {
    "/api/v1/ai/events",
    "/api/v1/ai/ingest/file",
    "/api/v1/chain/search",
}
CTX = ssl._create_unverified_context()


def _key() -> str:
    return (os.environ.get("ARTCB_API_KEY") or "").strip()


def hit(url: str, *, method: str = "GET", body: dict | None = None, auth: bool = False, timeout: int = 8) -> dict:
    headers = {"Accept": "application/json"}
    if auth:
        key = _key()
        if len(key) < 16:
            return {"url": url, "ok": False, "error": "no_key", "dur_ns": 0}
        headers["Authorization"] = f"Bearer {key}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    ctx = CTX if url.startswith("https") else None
    t0 = time.perf_counter_ns()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            code = resp.status
            server_ns = resp.headers.get("X-ARTCB-Trace-Ns")
        dur = time.perf_counter_ns() - t0
        parsed = {}
        if raw[:1] in (b"{", b"["):
            try:
                parsed = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                parsed = {}
        keep = {}
        if isinstance(parsed, dict):
            for k in (
                "height",
                "last_hash",
                "chain_valid",
                "git_sha",
                "count",
                "status",
                "knowledge_count",
                "detail",
                "certified_distributed_mainnet",
            ):
                if k in parsed:
                    keep[k] = parsed[k]
        return {
            "url": url,
            "method": method,
            "http": code,
            "ok": 200 <= code < 400,
            "dur_ns": dur,
            "server_ns": int(server_ns) if server_ns and str(server_ns).isdigit() else None,
            "bytes": len(raw),
            **keep,
        }
    except urllib.error.HTTPError as exc:
        dur = time.perf_counter_ns() - t0
        return {
            "url": url,
            "method": method,
            "http": exc.code,
            "ok": False,
            "dur_ns": dur,
            "error": exc.read().decode("utf-8", errors="replace")[:180],
        }
    except Exception as exc:
        return {
            "url": url,
            "method": method,
            "http": 0,
            "ok": False,
            "dur_ns": time.perf_counter_ns() - t0,
            "error": type(exc).__name__,
        }


def openapi_gets(base: str) -> list[str]:
    spec = hit(f"{base}/openapi.json", timeout=30)
    if not spec.get("ok"):
        return []
    req = urllib.request.Request(f"{base}/openapi.json", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        doc = json.loads(resp.read().decode())
    paths = []
    for path, methods in (doc.get("paths") or {}).items():
        if "get" not in methods:
            continue
        if "{" in path:
            continue
        if any(path.startswith(p) for p in SKIP_GET_PREFIXES):
            continue
        if path in SKIP_GET_EXACT:
            continue
        paths.append(path)
    return sorted(set(paths))


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("ok")]
    err = [r for r in rows if not r.get("ok")]
    durs = [int(r["dur_ns"]) for r in rows if isinstance(r.get("dur_ns"), int)]
    by_http: dict[str, int] = {}
    for r in rows:
        by_http[str(r.get("http"))] = by_http.get(str(r.get("http")), 0) + 1
    return {
        "n": len(rows),
        "ok": len(ok),
        "fail": len(err),
        "by_http": by_http,
        "dur_ns_min": min(durs) if durs else None,
        "dur_ns_max": max(durs) if durs else None,
        "dur_ns_avg": int(sum(durs) / len(durs)) if durs else None,
    }


def main() -> int:
    do_memo = "--memo" in sys.argv
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload: dict = {"stamp": stamp, "nodes": {}, "memo": None, "concepts": None, "token_printed": False}
    for nid, base in NODES.items():
        print(f"PROBE {nid}", flush=True)
        gets = openapi_gets(base)
        targets = [f"{base}{p}" for p in gets]
        targets += [
            f"{base}/api/v1/chain/block/0",
            f"{base}/api/v1/chain/block/4",
            f"{base}/api/v1/chain/block/1073",
            f"{base}/api/v1/chain/search?q=continuite",
            f"{base}/api/v1/ai/ingest/file?path=src/artcb/chain/manager.py",
            f"{base}/api/v1/p2p/replica/blocks",
        ]
        rows: list[dict] = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(hit, url) for url in targets]
            for fut in as_completed(futs):
                rows.append(fut.result())
        extra = [
            hit(f"{base}/api/v1/encode", method="POST", body={"text": "Le livre public doit se propager."}),
            hit(
                f"{base}/api/v1/search",
                method="POST",
                body={"query": "propagation publique", "top_k": 3},
            ),
        ]
        all_rows = rows + extra
        payload["nodes"][nid] = {
            "base": base,
            "get_paths": len(gets),
            "summary": summarize(all_rows),
            "chain": hit(f"{base}/api/v1/chain/status"),
            "health": hit(f"{base}/health"),
            "fails": [r for r in all_rows if not r.get("ok")][:40],
            "slowest": sorted(all_rows, key=lambda r: int(r.get("dur_ns") or 0), reverse=True)[:8],
        }
        print(f"DONE {nid} {payload['nodes'][nid]['summary']}", flush=True)
    if ROOT.joinpath("src").is_dir():
        sys.path.insert(0, str(ROOT / "src"))
        try:
            from artcb.ir.encoder import IREncoder
            from artcb.ir.concept import concept_id_from_node

            enc = IREncoder()
            texts = {
                "fr": "Le serveur doit vérifier la signature.",
                "en": "The server must verify the signature.",
                "es": "El servidor debe verificar la firma.",
            }
            ids = {}
            for lang, text in texts.items():
                g = enc.encode(text, session_id=f"probe_{lang}")
                ids[lang] = [concept_id_from_node(n) for n in g.nodes]
            payload["concepts"] = {
                "ids": ids,
                "fr_en_overlap": len(set(ids["fr"]) & set(ids["en"])),
                "all_three_overlap": len(set(ids["fr"]) & set(ids["en"]) & set(ids["es"])),
                "note": "overlap 0 is a demonstrated gap (rapport 252) — not invented PASS",
            }
        except Exception as exc:  # noqa: BLE001
            payload["concepts"] = {"error": type(exc).__name__}
    if do_memo:
        memo = hit(
            "https://152.228.144.34:8443/api/v1/ai/memo",
            method="POST",
            auth=True,
            timeout=60,
            body={
                "content": (
                    "254 ns-trace + full live probe. Reports 252/253: replication 1074 is real; "
                    "language IA not yet ConceptID-convergent; JSON still primary storage; "
                    "BFT/adversarial not demonstrated. Probe hits every OpenAPI GET on 4 nodes "
                    "plus encode/search/book read. Nanosecond traces on HTTP and chain_append."
                ),
                "memo_type": "lesson",
                "tags": ["254", "trace_ns", "live_probe", "memory"],
                "session_id": "ai_memo_254",
                "visibility": "public",
                "inject_context": True,
            },
        )
        payload["memo"] = memo
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    dest = out / f"254_live_probe_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "254_live_probe_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    brief = {
        "wrote": str(dest),
        "nodes": {
            nid: {
                "height": row["chain"].get("height"),
                "git_sha": str(row["health"].get("git_sha") or "")[:12],
                "gets_ok": row["summary"]["ok"],
                "gets_fail": row["summary"]["fail"],
                "dur_ns_avg": row["summary"]["dur_ns_avg"],
            }
            for nid, row in payload["nodes"].items()
        },
        "concepts": payload.get("concepts"),
        "memo_http": (payload.get("memo") or {}).get("http"),
    }
    print(json.dumps(brief, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
