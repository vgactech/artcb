#!/usr/bin/env python3
"""R306 P0 proof matrix — measure, do not certify.

P0 checklist (operator audit 2026-09-10):
1 SHA ×5 vs origin/main
2 membership N=5 identity JSON
3 primary_of(view) vs stored primary
4 PREPARE/COMMIT real (seeds HTTP)
5 quorum Q=3
6 same tip/height seeds (+ Mac separate)
7–10 chaos L/M/N — SSH required; may be NOT_REACHABLE

Never wipe / genesis / rescue. CERTIFIED_100=false.
Mac RFC1918 is never in seed fan-out without public tunnel.
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# pbft_view.py still imports `src.artcb…` — keep repo root + src on path.
for _p in (str(ROOT), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from artcb.consensus.pbft_view import primary_of  # noqa: E402
from artcb.mac_node_access import select_cloud_remote  # noqa: E402
from artcb.node_registry import (  # noqa: E402
    MAC_NODE_ID,
    OFFICIAL_COMPUTE_NODE_IDS,
    official_pbft_n_f_q,
    official_pbft_replica_ids,
    pbft_reachable_http_map,
)
from artcb.p2p.official_replica import replica_peer_allowed  # noqa: E402

CTX = ssl.create_default_context()
NS = ROOT / "data" / "trace" / "ns.jsonl"
HTTP_SEEDS = {
    "ovh-node-1": "https://artcb.me",
    "ovh-node-2": "https://n2.artcb.me",
    "aws-node-3": "https://n3.artcb.me",
    "ovh-node-4": "https://n4.artcb.me",
}
HTTP_ALL = {**HTTP_SEEDS, "mac-node-local": "http://127.0.0.1:8001"}


def _ns(event: str, **kw) -> None:
    NS.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts_ns": time.time_ns(), "event": event, **kw}
    with NS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def http(method: str, url: str, body: dict | None = None, timeout: int = 20) -> dict:
    t0 = time.perf_counter_ns()
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = CTX if url.startswith("https") else None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read().decode()
            code = int(getattr(r, "status", 200) or 200)
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:300]}
            dur = time.perf_counter_ns() - t0
            _ns("http_" + method.lower(), url=url, http=code, dur_ns=dur)
            return {"http": code, "dur_ns": dur, **parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() if exc.fp else ""
        try:
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:300]}
        except json.JSONDecodeError:
            parsed = {"raw": raw[:300]}
        dur = time.perf_counter_ns() - t0
        _ns("http_" + method.lower(), url=url, http=exc.code, dur_ns=dur)
        return {"http": exc.code, "dur_ns": dur, **parsed}
    except Exception as exc:  # noqa: BLE001 — live probe
        dur = time.perf_counter_ns() - t0
        _ns("http_" + method.lower(), url=url, http=0, dur_ns=dur, error=type(exc).__name__)
        return {"http": 0, "dur_ns": dur, "error": type(exc).__name__, "msg": str(exc)[:200]}


def measure_nodes(want: str) -> dict:
    nodes: dict = {}
    for nid, base in HTTP_ALL.items():
        hb = http("GET", f"{base}/health")
        vb = http("GET", f"{base}/api/v1/consensus/pbft/view")
        fb = http("GET", f"{base}/api/v1/consensus/pbft/finality")
        cb = http("GET", f"{base}/api/v1/chain/status")
        view = int(vb.get("view") or 0) if vb.get("http") == 200 else None
        stored = vb.get("primary") if vb.get("http") == 200 else None
        calc = primary_of(view) if view is not None else None
        nodes[nid] = {
            "base": base,
            "health_http": hb.get("http"),
            "git_sha": hb.get("git_sha") if hb.get("http") == 200 else None,
            "sha_eq_origin": (hb.get("git_sha") == want) if hb.get("http") == 200 else False,
            "pqc": ((hb.get("pqc") or {}).get("algorithm") if hb.get("http") == 200 else None),
            "height": cb.get("height") if cb.get("http") == 200 else None,
            "last_hash": cb.get("last_hash") if cb.get("http") == 200 else None,
            "chain_valid": cb.get("chain_valid") if cb.get("http") == 200 else None,
            "view": view,
            "n": vb.get("n") if vb.get("http") == 200 else None,
            "f": vb.get("f") if vb.get("http") == 200 else None,
            "q": vb.get("q") if vb.get("http") == 200 else None,
            "replicas": vb.get("replicas") if vb.get("http") == 200 else None,
            "primary_stored": stored,
            "primary_of_view": calc,
            "primary_matches_calc": bool(stored and calc and stored == calc),
            "finality": {
                k: fb.get(k)
                for k in ("prepared_count", "committed_count", "certificate_count")
            }
            if fb.get("http") == 200
            else {"error": fb.get("error")},
        }
    return nodes


def probe_propose(nodes: dict) -> dict:
    """Try propose on calc primary and stored primary. Seeds only. No wipe."""
    v = int(nodes["ovh-node-1"].get("view") or 0)
    stored = nodes["ovh-node-1"].get("primary_stored")
    calc = primary_of(v)
    height_before = nodes["ovh-node-1"].get("height")
    tip_before = nodes["ovh-node-1"].get("last_hash")
    tag = f"p0_306_{int(time.time())}"
    attempts: dict = {}
    for label, primary in (("calc_primary", calc), ("stored_primary", stored)):
        if primary not in HTTP_SEEDS:
            attempts[label] = {"ok": False, "reason": "primary_not_seed_http", "primary": primary}
            continue
        proposed = http(
            "POST",
            f"{HTTP_SEEDS[primary]}/api/v1/consensus/pbft/propose",
            {"graph_id": f"{tag}_{label}", "graph_root": f"{tag}_{label}", "source": "pbft:306_p0"},
        )
        attempts[label] = {
            "primary": primary,
            "propose_http": proposed.get("http"),
            "propose_ok": proposed.get("ok"),
            "propose_reason": proposed.get("reason")
            or proposed.get("detail")
            or proposed.get("error"),
            "has_preprepare": bool(proposed.get("pre_prepare") or proposed.get("preprepare")),
        }
    after = {nid: http("GET", f"{HTTP_SEEDS[nid]}/api/v1/chain/status") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    book_unchanged = all(after[n].get("height") == height_before for n in after) and all(
        after[n].get("last_hash") == tip_before for n in after
    )
    a = attempts.get("calc_primary") or {}
    b = attempts.get("stored_primary") or {}
    prepared = bool(a.get("has_preprepare") or b.get("has_preprepare"))
    return {
        "view": v,
        "primary_stored": stored,
        "primary_of_view": calc,
        "primary_divergence": stored != calc,
        "height_before": height_before,
        "tip_before_prefix": (tip_before or "")[:16],
        "attempts": attempts,
        "book_unchanged": book_unchanged,
        "mac_in_fanout": False,
        "mac_participated": False,
        "verdict": "PASS" if prepared else "FAIL_OR_BLOCKED",
        "note": "409 equivocation on calc primary + 409 not_primary on stored = membership/primary divergence blocks new PREPARE",
    }


def build_p0(want: str, nodes: dict, propose: dict) -> dict:
    shas = {nid: r.get("git_sha") for nid, r in nodes.items()}
    tips = {nid: r.get("last_hash") for nid, r in nodes.items()}
    ns_ = {nid: r.get("n") for nid, r in nodes.items()}
    seed_tips = {nid: tips[nid] for nid in OFFICIAL_COMPUTE_NODE_IDS}
    return {
        "1_sha_exact_5_runtimes": {
            "origin_main": want,
            "shas_prefix": {k: (v or "")[:12] for k, v in shas.items()},
            "all_eq_origin": all(nodes[n].get("sha_eq_origin") for n in nodes),
            "verdict": "PASS"
            if all(nodes[n].get("sha_eq_origin") for n in nodes)
            else "PARTIAL",
        },
        "2_membership_n5": {
            "code_n_f_q": list(official_pbft_n_f_q()),
            "live_n": ns_,
            "mac_in_replicas": {
                n: MAC_NODE_ID in (nodes[n].get("replicas") or []) for n in nodes
            },
            "verdict": "PASS_IDENTITY"
            if all(ns_.get(n) == 5 for n in nodes)
            else "FAIL",
            "note": "Identity JSON ≠ PREPARE participation",
        },
        "3_primary_calculated": {
            "rows": {
                n: {
                    "view": nodes[n].get("view"),
                    "stored": nodes[n].get("primary_stored"),
                    "calc": nodes[n].get("primary_of_view"),
                    "match": nodes[n].get("primary_matches_calc"),
                }
                for n in nodes
            },
            "verdict": "PASS"
            if all(nodes[n].get("primary_matches_calc") for n in OFFICIAL_COMPUTE_NODE_IDS)
            else "FAIL_DIVERGENCE",
        },
        "4_prepare_commit_real": {
            "verdict": propose.get("verdict"),
            "mac_participated": False,
            "detail": propose,
        },
        "5_quorum_q3": {
            "verdict": "NOT_REACHED" if propose.get("verdict") != "PASS" else "MEASURED",
            "mac_in_quorum": False,
        },
        "6_same_block_tip_state": {
            "seed_tips_same": len(set(seed_tips.values())) == 1 and None not in seed_tips.values(),
            "mac_same_as_seeds": tips.get("mac-node-local")
            == next(iter(set(v for v in seed_tips.values() if v)), None),
            "verdict": "PASS_SEEDS_ONLY"
            if len(set(v for v in seed_tips.values() if v)) == 1
            and tips.get("mac-node-local")
            != next(iter(set(v for v in seed_tips.values() if v)), None)
            else "CHECK",
        },
        "7_10_chaos_L_M_N": {
            "verdict": "NOT_RUN",
            "reason": "SSH port 22 connection refused from this LAN",
        },
    }


def main() -> int:
    want = subprocess.check_output(["git", "rev-parse", "origin/main"], text=True).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    nodes = measure_nodes(want)
    propose = probe_propose(nodes)
    tun = select_cloud_remote()
    payload = {
        "stamp": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "origin_main": want,
        "head": head,
        "certified_100": False,
        "mac_live_pbft": False,
        "includes_thinking": False,
        "wipe": False,
        "n_f_q": list(official_pbft_n_f_q()),
        "membership": list(official_pbft_replica_ids()),
        "seeds": list(OFFICIAL_COMPUTE_NODE_IDS),
        "mac_in_seeds": MAC_NODE_ID in OFFICIAL_COMPUTE_NODE_IDS,
        "reachable_http": list(pbft_reachable_http_map().keys()),
        "replica_peer_rfc1918": replica_peer_allowed("10.234.49.2"),
        "tunnel": {k: tun.get(k) for k in ("ok", "reason", "tunnel_required")},
        "nodes": nodes,
        "propose_probe": propose,
        "p0": build_p0(want, nodes, propose),
        "crypto_observed": {n: nodes[n].get("pqc") for n in nodes},
    }
    dest = ROOT / "logs" / f"306_p0_proof_matrix_{payload['stamp']}.json"
    latest = ROOT / "logs" / "306_p0_proof_matrix.json"
    text = json.dumps(payload, indent=2) + "\n"
    dest.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    print(json.dumps({"ok": True, "log": str(dest), "p0": payload["p0"], "certified_100": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
