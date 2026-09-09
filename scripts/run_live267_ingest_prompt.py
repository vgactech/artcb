#!/usr/bin/env python3
"""Live ingest of this turn's user_query onto ARTCB (OVH1 Bearer /ai/memo).

Agent-mediated. Cursor does not intercept the prompt. Thinking/system/tokens
are not posted. Writes logs/267_ingest_*.json. Never prints the API key.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import ingest_prompt_file, resolve_api_key, resolve_api_url  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = {
    "ovh-node-1": "http://152.228.144.34:8000",
    "ovh-node-2": "http://151.80.107.29:8000",
    "aws-node-3": "http://13.38.209.25:8000",
    "ovh-node-4": "http://91.134.45.8:8000",
}


def _http_plain(url: str, timeout: float = 20) -> dict:
    import ssl
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    t0 = time.perf_counter_ns()
    req = Request(url, method="GET")
    ctx = ssl._create_unverified_context() if url.startswith("https") else None
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            if isinstance(body, dict):
                body["http"] = resp.status
                body["dur_ns"] = time.perf_counter_ns() - t0
                body["trace_ns"] = resp.headers.get("X-ARTCB-Trace-Ns")
            return body
    except HTTPError as exc:
        return {"http": exc.code, "error": exc.read().decode("utf-8", errors="replace")[:400]}
    except (URLError, TimeoutError, OSError) as exc:
        return {"http": 0, "error": type(exc).__name__}


def certs_for(seq: int) -> dict:
    out = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        row = _http_plain(f"{HTTP[nid]}/api/v1/consensus/pbft/certificate?seq={int(seq)}")
        cert = row.get("certificate") if isinstance(row.get("certificate"), dict) else None
        out[nid] = {
            "http": row.get("http"),
            "ok": bool(row.get("ok") and cert),
            "digest": (cert or {}).get("digest") or (cert or {}).get("block_hash"),
            "view": (cert or {}).get("view"),
            "seq": (cert or {}).get("seq"),
            "q": (cert or {}).get("q"),
            "commits": len((cert or {}).get("commits") or []),
            "dur_ns": row.get("dur_ns"),
        }
    return out


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = Path(os.environ.get("ARTCB_INGEST_PROMPT_FILE") or "/tmp/artcb_turn_prompt.txt")
    url = resolve_api_url()
    key = resolve_api_key()
    payload: dict = {
        "stamp": stamp,
        "platform_hook": False,
        "prompt_path": str(path),
        "prompt_exists": path.is_file(),
        "live_url": url,
        "key_present": bool(key and key.startswith("artcb_")),
    }
    if not path.is_file():
        payload["error"] = "prompt_file_missing"
        print(json.dumps(payload, indent=2))
        return 2
    if not key:
        payload["error"] = "api_key_missing"
        print(json.dumps(payload, indent=2))
        return 3
    before = {nid: _http_plain(f"{HTTP[nid]}/api/v1/chain/status") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    view = _http_plain(f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view")
    payload["before_height"] = {n: (before[n].get("height"), before[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS}
    payload["view"] = view.get("view")
    payload["primary"] = view.get("primary")
    t0 = time.perf_counter_ns()
    ingest = ingest_prompt_file(
        path,
        url=url,
        api_key=key,
        tags=["267", "ingest_at_receipt", "user_query", "cursor_chat"],
        session_id="267-cursor-chat-truth",
        timeout=180,
    )
    payload["ingest"] = ingest
    payload["ingest_wall_ns"] = time.perf_counter_ns() - t0
    seq = ingest.get("ingest_block_index")
    if seq is not None:
        time.sleep(2)
        payload["certs"] = certs_for(int(seq))
        from artcb.live import http_json

        memo_http, memo = http_json("GET", f"{url}/api/v1/ai/memo/{int(seq)}", api_key=key, timeout=60)
        text = (memo.get("content_text") or "") if isinstance(memo, dict) else ""
        original = path.read_text(encoding="utf-8")
        payload["readback"] = {
            "http": memo_http,
            "content_available": bool(text),
            "content_chars": len(text),
            "original_chars": len(original),
            "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
            "user_query_in_content": original in text if original else False,
            "starts_with_veriter": "JE VEUX LA VERITER" in text,
        }
    after = {nid: _http_plain(f"{HTTP[nid]}/health") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    payload["after_sha"] = {n: after[n].get("git_sha") for n in OFFICIAL_COMPUTE_NODE_IDS}
    chain_after = {nid: _http_plain(f"{HTTP[nid]}/api/v1/chain/status") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    payload["after_height"] = {
        n: (chain_after[n].get("height"), chain_after[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS
    }
    certs = payload.get("certs") or {}
    digests = {c.get("digest") for c in certs.values() if c.get("digest")}
    payload["cert_x4"] = bool(certs) and all(c.get("ok") for c in certs.values()) and len(digests) == 1
    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / f"267_ingest_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "267_ingest_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    brief = {
        "wrote": str(dest),
        "ingest_http": ingest.get("ingest_http"),
        "block_index": ingest.get("ingest_block_index"),
        "block_hash": ingest.get("ingest_block_hash"),
        "chars": ingest.get("chars"),
        "sha256": ingest.get("sha256"),
        "cert_x4": payload.get("cert_x4"),
        "platform_hook": False,
    }
    print(json.dumps(brief, indent=2))
    return 0 if ingest.get("ingest_http") == 200 else 4


if __name__ == "__main__":
    raise SystemExit(main())
