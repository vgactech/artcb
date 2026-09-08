#!/usr/bin/env python3
"""Live V-XX probe: active Byzantine *offers*, OVH4 stays up.

Never stops a node. Never wipes blocks.jsonl. Never sends a well-formed
tip-extension (that would append). Not a PBFT demonstration.

Uses POST /p2p/blocks/offer when the 260 SHA is deployed; otherwise records
the 404 and still probes receive/replica rejection on the current SHA.
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
CTX = ssl._create_unverified_context()
NODES = {
    "ovh-node-1": "https://152.228.144.34:8443",
    "ovh-node-2": "https://151.80.107.29:8443",
    "aws-node-3": "https://51.44.222.232:8443",
    "ovh-node-4": "https://91.134.45.8:8443",
}


def _http(method: str, url: str, body: dict | None = None, timeout: int = 20) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:300]}
            return {"ok": True, "http": resp.status, "rtt_ms": round((time.perf_counter() - t0) * 1000, 1), **parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"detail": raw}
        except json.JSONDecodeError:
            parsed = {"detail": raw}
        return {
            "ok": False,
            "http": exc.code,
            "rtt_ms": round((time.perf_counter() - t0) * 1000, 1),
            **(parsed if isinstance(parsed, dict) else {"detail": raw}),
        }
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "http": 0, "error": type(exc).__name__, "rtt_ms": round((time.perf_counter() - t0) * 1000, 1)}


def _status(base: str) -> dict:
    return _http("GET", f"{base}/api/v1/chain/status")


def _health(ip: str) -> dict:
    return _http("GET", f"http://{ip}:8000/health")


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = os.environ.get("ARTCB_API_URL") or NODES["ovh-node-1"]
    baseline = {}
    for nid, url in NODES.items():
        baseline[nid] = {"health": _health(url.split("//")[1].split(":")[0]), "status": _status(url)}

    tip = str((baseline["ovh-node-1"].get("status") or {}).get("last_hash") or "")
    height = int((baseline["ovh-node-1"].get("status") or {}).get("height") or 0)
    next_index = height  # height == next index on this chain

    attacks = [
        {
            "name": "hash_mismatch",
            "block": {
                "visibility": "public",
                "index": next_index,
                "timestamp": "2026-09-08T00:00:00Z",
                "prev_hash": tip,
                "graph_root": "byz-hash",
                "merkle_root": "byz-hash",
                "pol_score": 0.1,
                "hash": "ff" * 32,
                "signature": "ed25519:00",
            },
        },
        {
            "name": "invalid_signature",
            "block": {
                "visibility": "public",
                "index": next_index,
                "timestamp": "2026-09-08T00:00:00Z",
                "prev_hash": tip,
                "graph_root": "byz-sig",
                "merkle_root": "byz-sig",
                "pol_score": 0.1,
                "hash": "aa" * 32,
                "signature": "not-a-signature",
            },
        },
        {
            "name": "wrong_prev_hash",
            "block": {
                "visibility": "public",
                "index": next_index,
                "timestamp": "2026-09-08T00:00:00Z",
                "prev_hash": "00" * 32,
                "graph_root": "byz-prev",
                "merkle_root": "byz-prev",
                "pol_score": 0.1,
                "hash": "bb" * 32,
                "signature": "ed25519:00",
            },
        },
    ]
    offers = []
    appended = False
    for attack in attacks:
        resp = _http(
            "POST",
            f"{target}/api/v1/p2p/blocks/offer",
            {"blocks": [attack["block"]], "from_node_id": "ovh-node-4"},
        )
        offers.append({"name": attack["name"], "resp": {k: resp.get(k) for k in resp if k != "blocks"}})
        for dec in resp.get("decisions") or []:
            if dec.get("action") == "append":
                appended = True

    receive = _http("POST", f"{target}/api/v1/p2p/blocks/receive", {"envelope": {"ciphertext": "00", "from_node_id": "ovh-node-4"}})
    replica = _http("POST", f"{target}/api/v1/p2p/replica/push", {"envelope": {"ciphertext": "00", "from_node_id": "ovh-node-4"}})
    evidence = _http("GET", f"{target}/api/v1/consensus/byzantine/evidence?limit=50")
    after = {nid: _status(url) for nid, url in NODES.items()}

    payload = {
        "stamp": stamp,
        "target": target,
        "baseline": {
            nid: {
                "git_sha": (row.get("health") or {}).get("git_sha"),
                "height": (row.get("status") or {}).get("height"),
                "last_hash": (row.get("status") or {}).get("last_hash"),
                "chain_valid": (row.get("status") or {}).get("chain_valid"),
            }
            for nid, row in baseline.items()
        },
        "offers": offers,
        "appended_from_byzantine_offer": appended,
        "receive_garbage": {"http": receive.get("http"), "ok": receive.get("ok")},
        "replica_from_non_official": {"http": replica.get("http"), "ok": replica.get("ok"), "detail": str(replica.get("detail") or "")[:160]},
        "evidence_http": evidence.get("http"),
        "evidence_summary": evidence.get("summary"),
        "after": {
            nid: {"height": row.get("height"), "last_hash": row.get("last_hash"), "chain_valid": row.get("chain_valid")}
            for nid, row in after.items()
        },
        "ovh4_not_stopped": True,
        "not_block_append_bft": True,
        "token_printed": False,
    }
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    dest = out / f"260_byzantine_probe_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "260_byzantine_probe_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(dest),
                "appended_from_byzantine_offer": appended,
                "offer_https": [o["resp"].get("http") for o in offers],
                "receive_http": receive.get("http"),
                "replica_http": replica.get("http"),
                "evidence_http": evidence.get("http"),
                "height_ovh1": (after.get("ovh-node-1") or {}).get("height"),
            },
            indent=2,
        )
    )
    return 2 if appended else 0


if __name__ == "__main__":
    raise SystemExit(main())
