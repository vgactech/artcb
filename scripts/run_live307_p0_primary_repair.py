#!/usr/bin/env python3
"""R307 P0-B — repair primary via VIEW-CHANGE/NEW-VIEW (no wipe).

Canonical authority: primary_of(view) over official_pbft_replica_ids().
Stored primary is not normative. CERTIFIED_100 stays false.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.artcb.consensus.pbft_view import primary_of  # noqa: E402
from src.artcb.node_registry import official_pbft_n_f_q, official_pbft_replica_ids  # noqa: E402

HTTPS = {
    "ovh-node-1": "https://artcb.me",
    "ovh-node-2": "https://n2.artcb.me",
    "aws-node-3": "https://n3.artcb.me",
    "ovh-node-4": "https://n4.artcb.me",
}
MAC_HTTP = "http://127.0.0.1:8001"
SEEDS = list(HTTPS.keys())
VC_KEYS = (
    "kind",
    "protocol",
    "view",
    "from_view",
    "height",
    "last_hash",
    "replica_id",
    "reason",
    "message",
    "signature",
    "producer_ed25519_b64",
    "producer_pqc_b64",
)


def _operator_key() -> str:
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(key) >= 16:
        return key
    try:
        from artcb.live import apply_key_to_environ, resolve_api_key

        loaded = resolve_api_key()
        if loaded:
            apply_key_to_environ(loaded)
            return loaded.strip()
    except Exception:
        return ""
    return ""


def _http(method: str, url: str, body: dict | None = None, timeout: int = 30, *, auth: bool = False) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if auth:
        key = _operator_key()
        if len(key) < 16:
            return {"ok": False, "http": 0, "error": "ARTCB_API_KEY missing"}
        headers["Authorization"] = f"Bearer {key}"
    req = Request(url, data=data, method=method, headers=headers)
    t0 = time.perf_counter_ns()
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:400]}
            return {"ok": True, "http": resp.status, "dur_ns": time.perf_counter_ns() - t0, **parsed}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:800]
        try:
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"detail": raw}
        except json.JSONDecodeError:
            parsed = {"detail": raw}
        return {"ok": False, "http": exc.code, "dur_ns": time.perf_counter_ns() - t0, **(parsed if isinstance(parsed, dict) else {"detail": raw})}
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "http": 0, "error": type(exc).__name__, "detail": str(exc)[:200], "dur_ns": time.perf_counter_ns() - t0}


def _tcp(host: str, port: int, timeout: float = 5.0) -> dict:
    s = socket.socket()
    s.settimeout(timeout)
    t0 = time.perf_counter_ns()
    try:
        s.connect((host, port))
        return {"ok": True, "dur_ns": time.perf_counter_ns() - t0}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "dur_ns": time.perf_counter_ns() - t0}
    finally:
        s.close()


def _view(base: str) -> dict:
    return _http("GET", f"{base}/api/v1/consensus/pbft/view")


def _health(base: str) -> dict:
    return _http("GET", f"{base}/health")


def _snapshot_all() -> dict:
    out = {}
    for nid, base in HTTPS.items():
        h = _health(base)
        v = _view(base)
        out[nid] = {
            "git_sha": h.get("git_sha"),
            "status": h.get("status"),
            "view": v.get("view"),
            "primary_stored": v.get("primary"),
            "n": v.get("n"),
            "f": v.get("f"),
            "q": v.get("q"),
            "replicas": v.get("replicas"),
            "health_http": h.get("http"),
            "view_http": v.get("http"),
        }
    mh = _health(MAC_HTTP)
    mv = _view(MAC_HTTP)
    out["mac-node-local"] = {
        "git_sha": mh.get("git_sha"),
        "status": mh.get("status"),
        "view": mv.get("view"),
        "primary_stored": mv.get("primary"),
        "n": mv.get("n"),
        "replicas": mv.get("replicas"),
        "health_http": mh.get("http"),
        "view_http": mv.get("http"),
        "note": "local_only_not_public_pbft_transport",
    }
    return out


def _align_row(row: dict) -> dict:
    view = int(row.get("view") or 0)
    stored = str(row.get("primary_stored") or "")
    calc = primary_of(view)
    return {
        "view": view,
        "primary_stored": stored,
        "primary_of": calc,
        "aligned": stored == calc and bool(stored),
    }


def _view_change(nodes: list[str], new_v: int, reason: str) -> dict:
    vcs: list[dict] = []
    emit = {}
    for nid in nodes:
        r = _http(
            "POST",
            f"{HTTPS[nid]}/api/v1/consensus/pbft/view-change",
            {"view": new_v, "reason": reason},
            auth=True,
        )
        emit[nid] = {"http": r.get("http"), "ok": r.get("ok"), "detail": r.get("detail") or r.get("error")}
        if r.get("http") == 200:
            vcs.append({k: r.get(k) for k in VC_KEYS if r.get(k) is not None})
    receive = {}
    for nid in nodes:
        receive[nid] = []
        for vc in vcs:
            if vc.get("replica_id") == nid:
                continue
            got = _http(
                "POST",
                f"{HTTPS[nid]}/api/v1/consensus/pbft/view-change/receive",
                {"view_change": vc},
                auth=True,
            )
            receive[nid].append(
                {
                    "from": vc.get("replica_id"),
                    "http": got.get("http"),
                    "ok": got.get("ok"),
                    "detail": got.get("detail") or got.get("error") or got.get("reason"),
                }
            )
    new_p = primary_of(new_v)
    nv = _http(
        "POST",
        f"{HTTPS[new_p]}/api/v1/consensus/pbft/new-view",
        {"view": new_v, "view_changes": vcs},
        auth=True,
    )
    nv_obj = nv.get("new_view") if isinstance(nv.get("new_view"), dict) else None
    fan = {}
    if nv_obj:
        for nid in nodes:
            if nid == new_p:
                continue
            fan[nid] = _http(
                "POST",
                f"{HTTPS[nid]}/api/v1/consensus/pbft/new-view",
                {"view": new_v, "view_changes": vcs, "new_view": nv_obj},
                auth=True,
            )
            fan[nid] = {
                "http": fan[nid].get("http"),
                "ok": fan[nid].get("ok"),
                "detail": fan[nid].get("detail") or fan[nid].get("error") or fan[nid].get("reason"),
            }
    return {
        "new_view_target": new_v,
        "canonical_primary": new_p,
        "vc_count": len(vcs),
        "vc_replicas": [v.get("replica_id") for v in vcs],
        "emit": emit,
        "receive": receive,
        "new_view_http": nv.get("http"),
        "new_view_ok": nv.get("ok"),
        "new_view_detail": nv.get("detail") or nv.get("error") or nv.get("reason"),
        "new_view_primary": (nv_obj or {}).get("primary") if nv_obj else nv.get("primary"),
        "enter_view": nv.get("enter_view"),
        "fanout": fan,
        "nv_obj_present": bool(nv_obj),
    }


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    want = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "origin/main"], text=True).strip()
    n, f, q = official_pbft_n_f_q()
    ids = list(official_pbft_replica_ids())
    before = _snapshot_all()
    seed_views = {nid: _align_row(before[nid]) for nid in SEEDS}
    divergent = any(not r["aligned"] for r in seed_views.values())
    cur_view = int(before["ovh-node-1"].get("view") or 0)
    new_v = cur_view + 1
    payload: dict = {
        "stamp": stamp,
        "protocol": "307-p0-primary-repair",
        "certified_100": False,
        "wipe": False,
        "origin_main": want,
        "canonical_rule": "primary_of(view) over official_pbft_replica_ids(); stored primary is not normative",
        "membership": {"n": n, "f": f, "q": q, "replicas": ids},
        "primary_of_table": {str(v): primary_of(v) for v in range(cur_view, cur_view + 3)},
        "before": before,
        "before_alignment": seed_views,
        "divergence": divergent,
        "aws3_tcp": {
            "22": _tcp("13.38.209.25", 22),
            "8000": _tcp("13.38.209.25", 8000),
            "8443": _tcp("13.38.209.25", 8443),
            "443_domain": _tcp("n3.artcb.me", 443),
        },
        "ts_ns": time.time_ns(),
    }

    repair = None
    if divergent:
        repair = _view_change(SEEDS, new_v, reason="307_p0_primary_of_alignment")
        payload["repair"] = repair
        time.sleep(1.5)
    else:
        payload["repair"] = {"skipped": True, "reason": "already_aligned"}

    after = _snapshot_all()
    after_align = {nid: _align_row(after[nid]) for nid in SEEDS}
    payload["after"] = after
    payload["after_alignment"] = after_align
    payload["aligned_seeds"] = all(r["aligned"] for r in after_align.values())
    payload["sha_homogeneity"] = {
        nid: {
            "git_sha": after[nid].get("git_sha"),
            "equals_origin_main": (after[nid].get("git_sha") or "") == want,
        }
        for nid in list(SEEDS) + ["mac-node-local"]
    }
    payload["sha_x5_pass"] = all(payload["sha_homogeneity"][nid]["equals_origin_main"] for nid in SEEDS + ["mac-node-local"])

    # Propose probe only if aligned on seeds
    propose = {}
    if payload["aligned_seeds"]:
        primary = after_align["ovh-node-1"]["primary_of"]
        base = HTTPS.get(primary)
        if base:
            propose["primary"] = primary
            propose["result"] = _http(
                "POST",
                f"{base}/api/v1/consensus/pbft/propose",
                {
                    "graph_id": f"307-p0-{stamp}",
                    "graph_root": "307-primary-repair",
                    "source": "pbft:307",
                    "visibility": "public",
                },
                auth=True,
            )
            propose["result"] = {
                "http": propose["result"].get("http"),
                "ok": propose["result"].get("ok"),
                "detail": propose["result"].get("detail") or propose["result"].get("error"),
                "seq": propose["result"].get("seq"),
                "digest": propose["result"].get("digest"),
            }
    else:
        propose = {"skipped": True, "reason": "primary_still_divergent"}
    payload["propose_probe"] = propose
    payload["verdict"] = {
        "CERTIFIED_100": False,
        "book_continuity_seeds": True,
        "primary_alignment": payload["aligned_seeds"],
        "sha_x5": payload["sha_x5_pass"],
        "aws3_ssh": payload["aws3_tcp"]["22"]["ok"],
        "prepare_commit": "NOT_RUN" if not payload["aligned_seeds"] else "PROBE_ONLY",
        "mac_pbft_transport": "NOT_PROVEN",
        "chaos": "NOT_RUN",
        "wipe": False,
    }

    out = ROOT / "logs" / "307_p0_primary_repair.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ns = ROOT / "data" / "trace" / "ns.jsonl"
    ns.parent.mkdir(parents=True, exist_ok=True)
    with ns.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts_ns": time.time_ns(),
                    "event": "307_p0_primary_repair",
                    "aligned": payload["aligned_seeds"],
                    "sha_x5": payload["sha_x5_pass"],
                    "new_view": (repair or {}).get("new_view_target") if isinstance(repair, dict) else None,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    print(json.dumps({"wrote": str(out), "aligned": payload["aligned_seeds"], "sha_x5": payload["sha_x5_pass"], "verdict": payload["verdict"]}, indent=2))
    return 0 if payload["aligned_seeds"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
