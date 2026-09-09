#!/usr/bin/env python3
"""265 live — PBFT block finality on the four official nodes.

R264 is baseline. This run exercises PRE-PREPARE/PREPARE/COMMIT + cert on
the real append/import path, with nanosecond traces. Processes stay UP
except TEST I (restart then must come back). Never wipe.
"""

from __future__ import annotations

import json
import os
import shlex
import ssl
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.consensus.pbft_finality import verify_certificate, verify_preprepare  # noqa: E402
from artcb.consensus.pbft_view import primary_of  # noqa: E402
from artcb.node_registry import NODES, OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402
from artcb.trace.ns import is_nanosecond_ts  # noqa: E402

CTX = ssl._create_unverified_context()
SSH_KEYS = {
    "ovh-node-1": Path.home() / ".ssh" / "artcb_ovh_deploy",
    "ovh-node-2": Path.home() / ".ssh" / "artcb_ovh_node_2",
    "aws-node-3": Path.home() / ".ssh" / "artcb_aws_node_3",
    "ovh-node-4": Path.home() / ".ssh" / "artcb_ovh_node_4",
}
KNOWN = {
    "ovh-node-1": ROOT / "deploy" / "ovh_artcb_node_1.known_hosts",
    "ovh-node-2": ROOT / "deploy" / "ovh_artcb_node_2.known_hosts",
    "aws-node-3": ROOT / "deploy" / "aws_artcb_node_3.known_hosts",
    "ovh-node-4": ROOT / "deploy" / "ovh_artcb_node_4.known_hosts",
}
HTTP = {
    "ovh-node-1": "http://152.228.144.34:8000",
    "ovh-node-2": "http://151.80.107.29:8000",
    "aws-node-3": "http://13.38.209.25:8000",
    "ovh-node-4": "http://91.134.45.8:8000",
}
HTTPS = {"ovh-node-1": "https://152.228.144.34:8443"}
PEERS = {
    "ovh-node-1": ["151.80.107.29", "13.38.209.25", "91.134.45.8"],
    "ovh-node-2": ["152.228.144.34", "13.38.209.25", "91.134.45.8"],
    "aws-node-3": ["152.228.144.34", "151.80.107.29", "91.134.45.8"],
    "ovh-node-4": ["152.228.144.34", "151.80.107.29", "13.38.209.25"],
}


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


def _http(method: str, url: str, body: dict | None = None, timeout: int = 25, *, auth: bool = False) -> dict:
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
    ctx = CTX if url.startswith("https") else None
    t0 = time.perf_counter_ns()
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:400]}
            return {"ok": True, "http": resp.status, "dur_ns": time.perf_counter_ns() - t0, **parsed}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:500]
        try:
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"detail": raw}
        except json.JSONDecodeError:
            parsed = {"detail": raw}
        return {"ok": False, "http": exc.code, "dur_ns": time.perf_counter_ns() - t0, **(parsed if isinstance(parsed, dict) else {"detail": raw})}
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "http": 0, "error": type(exc).__name__, "dur_ns": time.perf_counter_ns() - t0}


def _ssh_base(node_id: str) -> list[str] | None:
    spec = NODES[node_id]
    key = SSH_KEYS[node_id]
    if not key.is_file():
        return None
    known = KNOWN[node_id]
    known_opts = (
        ["-o", f"UserKnownHostsFile={known}", "-o", "StrictHostKeyChecking=yes"]
        if known.is_file()
        else ["-o", "StrictHostKeyChecking=accept-new"]
    )
    return ["-i", str(key), *known_opts, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", f"{spec.ssh_user}@{spec.ssh_host}"]


def _ssh(node_id: str, remote: str, timeout: int = 90, stdin: str | None = None) -> dict:
    base = _ssh_base(node_id)
    if base is None:
        return {"node_id": node_id, "returncode": 2, "stdout": "", "stderr": "missing_ssh_key"}
    proc = subprocess.run(["ssh", *base, remote], input=stdin, capture_output=True, text=True, timeout=timeout, check=False)
    return {"node_id": node_id, "returncode": proc.returncode, "stdout": (proc.stdout or "")[-3000:], "stderr": (proc.stderr or "")[-300:]}


def _scp(node_id: str, local: Path, remote: str) -> dict:
    base = _ssh_base(node_id)
    if base is None:
        return {"returncode": 2}
    host = base[-1]
    flags = base[:-1]
    proc = subprocess.run(["scp", *flags, str(local), f"{host}:{remote}"], capture_output=True, text=True, timeout=60, check=False)
    return {"node_id": node_id, "returncode": proc.returncode}


def isolate(nid: str, action: str) -> dict:
    peers = " ".join(PEERS[nid])
    script = "/home/ubuntu/artcb/scripts/artcb265_partition_node.sh"
    return _ssh(nid, f"chmod +x {script}; sudo bash {script} {action} {peers}")


def independent_snapshot() -> dict:
    out = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        h = _http("GET", f"{HTTP[nid]}/health")
        c = _http("GET", f"{HTTP[nid]}/api/v1/chain/status")
        v = _http("GET", f"{HTTP[nid]}/api/v1/consensus/pbft/view")
        f = _http("GET", f"{HTTP[nid]}/api/v1/consensus/pbft/finality")
        tr = _http("GET", f"{HTTP[nid]}/api/v1/trace?limit=20")
        rows = tr.get("rows") or []
        ns_ok = bool(rows) and all(is_nanosecond_ts(r.get("ts_ns")) for r in rows if r.get("ts_ns") is not None)
        out[nid] = {
            "git_sha": h.get("git_sha"),
            "health_http": h.get("http"),
            "height": c.get("height"),
            "last_hash": c.get("last_hash"),
            "chain_valid": c.get("chain_valid"),
            "view": v.get("view"),
            "primary": v.get("primary"),
            "replica_id": v.get("replica_id") or f.get("replica_id"),
            "finality_http": f.get("http"),
            "trace_unit": tr.get("unit"),
            "trace_ns_ok": ns_ok and tr.get("unit") == "nanosecond",
            "mock": False,
            "probed_url": HTTP[nid],
        }
    return out


def _same_sha(snap: dict, want: str) -> bool:
    return all((snap.get(n) or {}).get("git_sha") == want for n in OFFICIAL_COMPUTE_NODE_IDS)


def run_round(tag: str, nodes: list[str] | None = None) -> dict:
    """TEST A path: propose on current primary, fan-out, certify, write."""
    nodes = nodes or list(OFFICIAL_COMPUTE_NODE_IDS)
    views = {n: _http("GET", f"{HTTP[n]}/api/v1/consensus/pbft/view") for n in nodes}
    view = int((views.get(nodes[0]) or {}).get("view") or 0)
    primary = primary_of(view)
    if primary not in nodes:
        return {"ok": False, "reason": "primary_not_in_set", "view": view, "primary": primary}
    t0 = time.perf_counter_ns()
    gid = f"265-{tag}-{uuid.uuid4().hex[:8]}"
    proposed = _http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/propose", {"graph_id": gid, "graph_root": tag, "source": "pbft:265"})
    pp = proposed.get("pre_prepare")
    block = proposed.get("block")
    if proposed.get("http") != 200 or not isinstance(pp, dict) or not isinstance(block, dict):
        return {"ok": False, "phase": "propose", "proposed": {k: proposed.get(k) for k in ("http", "detail", "error")}, "dur_ns": time.perf_counter_ns() - t0}
    digest = str(pp.get("digest") or block.get("hash") or "")
    seq = int(block.get("index") or -1)
    recv = {}
    for nid in nodes:
        if nid == primary:
            continue
        recv[nid] = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
    if not verify_preprepare(pp):
        return {"ok": False, "reason": "preprepare_not_verifiable", "dur_ns": time.perf_counter_ns() - t0}
    prepares = {}
    for nid in nodes:
        prepares[nid] = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": digest})
    for nid in nodes:
        for src, row in prepares.items():
            prep = row.get("prepare")
            if src == nid or not isinstance(prep, dict):
                continue
            _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": prep})
    commits = {}
    cert = None
    for nid in nodes:
        commits[nid] = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/commit", {"view": view, "seq": seq, "digest": digest})
        if isinstance(commits[nid].get("certificate"), dict):
            cert = commits[nid]["certificate"]
    for nid in nodes:
        cmsg = (commits[nid].get("commit") if isinstance(commits[nid], dict) else None)
        if not isinstance(cmsg, dict):
            continue
        for dst in nodes:
            if dst == nid:
                continue
            got = _http("POST", f"{HTTP[dst]}/api/v1/consensus/pbft/commit", {"commit": cmsg})
            if isinstance(got.get("certificate"), dict):
                cert = got["certificate"]
    writes = {}
    if isinstance(cert, dict) and verify_certificate(cert):
        for nid in nodes:
            writes[nid] = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/certificate", {"certificate": cert, "block": block})
    heights = {n: _http("GET", f"{HTTP[n]}/api/v1/chain/status") for n in nodes}
    ok = bool(cert) and verify_certificate(cert) and all((writes.get(n) or {}).get("wrote") for n in nodes)
    hashes = {(heights.get(n) or {}).get("last_hash") for n in nodes}
    return {
        "ok": bool(ok and len(hashes) == 1),
        "tag": tag,
        "view": view,
        "primary": primary,
        "seq": seq,
        "digest": digest,
        "gid": gid,
        "preprepare_verified": True,
        "recv_ok": {n: (recv[n].get("ok")) for n in recv},
        "prepare_http": {n: (prepares[n].get("http")) for n in prepares},
        "commit_http": {n: (commits[n].get("http")) for n in commits},
        "cert_ok": bool(cert) and verify_certificate(cert or {}),
        "cert_q": (cert or {}).get("q"),
        "cert_replicas": (cert or {}).get("replica_ids"),
        "writes": {n: (writes.get(n) or {}).get("wrote") for n in nodes},
        "heights": {n: (heights[n].get("height"), heights[n].get("last_hash")) for n in nodes},
        "dur_ns": time.perf_counter_ns() - t0,
        "network_used": [HTTP[n] for n in nodes],
    }


def replica_from_ovh1() -> dict:
    code = (
        "import json,sys,urllib.request,urllib.error\n"
        "key=sys.stdin.read().strip()\n"
        "req=urllib.request.Request('http://127.0.0.1:8000/api/v1/p2p/replica/run?include_files=true',"
        "method='POST',headers={'Authorization':'Bearer '+key,'Accept':'application/json'})\n"
        "try:\n"
        "  with urllib.request.urlopen(req,timeout=200) as r:\n"
        "    print(r.read().decode())\n"
        "except urllib.error.HTTPError as e:\n"
        "  print(json.dumps({'ok':False,'http':e.code,'detail':e.read().decode()[:300]}))\n"
        "except Exception as e:\n"
        "  print(json.dumps({'ok':False,'error':type(e).__name__}))\n"
    )
    key = _operator_key()
    if len(key) < 16:
        return {"ok": False, "error": "missing_key"}
    row = _ssh("ovh-node-1", "python3 -c " + shlex.quote(code), timeout=240, stdin=key)
    try:
        parsed = json.loads(row.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {"raw": (row.get("stdout") or "")[:300]}
    peers = parsed.get("peers") or []
    ok_peers = [p for p in peers if p.get("ok") or p.get("skipped")]
    return {"ssh_rc": row.get("returncode"), "peer_ok": len(ok_peers), "ok": len(ok_peers) >= 3}


def verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload: dict = {
        "stamp": stamp,
        "protocol": "265-pbft-block-finality",
        "r264_is_baseline": True,
        "wipe": False,
        "unit": "nanosecond",
        "tests": {},
        "PBFT_LIVE_E2E_PASS": False,
    }
    isolated: list[str] = []
    try:
        want_sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        payload["git_sha_agent"] = want_sha
        payload["before"] = independent_snapshot()
        payload["same_sha_before"] = _same_sha(payload["before"], want_sha)
        if not payload["same_sha_before"]:
            payload["tests"]["deploy"] = {"result": "NOT_VALIDATED", "reason": "nodes_not_on_agent_sha"}
            payload["PBFT_LIVE_E2E_PASS"] = False

        a = run_round("A")
        traces_a = {n: _http("GET", f"{HTTP[n]}/api/v1/trace?limit=80") for n in OFFICIAL_COMPUTE_NODE_IDS}
        ns_a = True
        for n, tr in traces_a.items():
            rows = [r for r in (tr.get("rows") or []) if str(r.get("kind") or "").startswith("pbft_")]
            if not rows or tr.get("unit") != "nanosecond":
                ns_a = False
            if not all(is_nanosecond_ts(r.get("ts_ns")) for r in rows):
                ns_a = False
        payload["tests"]["A"] = {"result": verdict(bool(a.get("ok")) and ns_a), "round": a, "ns_traces": ns_a}

        # C — equivocation / conflicting digest
        primary = primary_of(int((payload["before"]["ovh-node-1"] or {}).get("view") or 0))
        views_now = _http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view")
        primary = primary_of(int(views_now.get("view") or 0))
        follower = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != primary][0]
        bad = _http("POST", f"{HTTP[follower]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": {"kind": "pre-prepare", "view": views_now.get("view"), "seq": 0, "digest": "ab" * 32, "replica_id": primary, "message": "PP|x", "signature": "nope", "block": {"index": 0, "hash": "ab" * 32}}})
        payload["tests"]["C"] = {"result": verdict(bad.get("http") == 409), "http": bad.get("http"), "detail": bad.get("detail")}

        # E — NEW-VIEW with 2 VC only
        nv_bad = _http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/new-view", {"view": int(views_now.get("view") or 0) + 5, "view_changes": [{}, {}]})
        payload["tests"]["E"] = {"result": verdict(nv_bad.get("http") in (409, 422)), "http": nv_bad.get("http"), "detail": nv_bad.get("detail")}

        # F — fake signature prepare
        fake_p = _http("POST", f"{HTTP[follower]}/api/v1/consensus/pbft/prepare", {"prepare": {"kind": "prepare", "view": views_now.get("view"), "seq": 1, "digest": "cd" * 32, "replica_id": follower, "message": "P|x", "signature": "00", "protocol": "265-pbft-block-finality"}})
        payload["tests"]["F"] = {"result": verdict(fake_p.get("ok") is False or fake_p.get("http") == 409 or fake_p.get("reason") == "invalid_prepare"), "body": {k: fake_p.get(k) for k in ("http", "ok", "reason", "detail")}}

        # J — after A, try import conflict via certificate with other digest is rejected on install
        conflict = _http("POST", f"{HTTP[follower]}/api/v1/consensus/pbft/certificate", {"certificate": {"view": 1, "seq": 0, "digest": "ee" * 32, "commits": [], "q": 3}})
        payload["tests"]["J"] = {"result": verdict(conflict.get("http") == 409), "http": conflict.get("http")}

        # D + B — isolate current primary, VIEW-CHANGE 264+265, NEW-VIEW, resume
        snap_mid = independent_snapshot()
        view_b = int((snap_mid.get("ovh-node-1") or {}).get("view") or 0)
        old_p = primary_of(view_b)
        new_v = view_b + 1
        new_p = primary_of(new_v)
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            _scp(nid, ROOT / "scripts" / "artcb265_partition_node.sh", "/home/ubuntu/artcb/scripts/artcb265_partition_node.sh")
        payload["isolate_B"] = isolate(old_p, "isolate")
        isolated.append(old_p)
        majority = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != old_p]
        vcs264 = []
        vcs265 = []
        t_vc = time.perf_counter_ns()
        for nid in majority:
            r264 = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change", {"view": new_v, "reason": "primary_unreachable"})
            if r264.get("http") == 200:
                vcs264.append({k: r264.get(k) for k in ("kind", "protocol", "view", "from_view", "height", "last_hash", "replica_id", "reason", "message", "signature", "producer_ed25519_b64", "producer_pqc_b64", "ts_ns") if r264.get(k) is not None})
            r265 = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change-265", {"view": new_v})
            if isinstance(r265.get("view_change"), dict):
                vcs265.append(r265["view_change"])
        for nid in majority:
            for vc in vcs264:
                if vc.get("replica_id") == nid:
                    continue
                _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change/receive", {"view_change": vc})
        nv = _http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264})
        nv_obj = nv.get("new_view")
        for nid in majority:
            if nid == new_p:
                continue
            if nv_obj:
                _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264, "new_view": nv_obj})
        payload["restore_B"] = isolate(old_p, "restore")
        isolated = [x for x in isolated if x != old_p]
        if nv_obj:
            _http("POST", f"{HTTP[old_p]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264, "new_view": nv_obj})
        views_b = {n: _http("GET", f"{HTTP[n]}/api/v1/consensus/pbft/view") for n in OFFICIAL_COMPUTE_NODE_IDS}
        b_round = run_round("B")
        d_ok = len(vcs265) >= 3 and all(int(v.get("view") or -1) == new_v for v in views_b.values())
        payload["tests"]["B"] = {"result": verdict(bool(b_round.get("ok")) and d_ok), "new_view": new_v, "old_primary": old_p, "new_primary": new_p, "vc264": len(vcs264), "round": b_round, "views": {n: views_b[n].get("view") for n in views_b}, "dur_ns_vc": time.perf_counter_ns() - t_vc, "isolated_stayed_up": _http("GET", f"{HTTP[old_p]}/health").get("http") == 200}
        payload["tests"]["D"] = {"result": verdict(len(vcs265) >= 3), "vc265_count": len(vcs265), "psets": [vc.get("prepared") for vc in vcs265]}
        payload["tests"]["K"] = {"result": verdict(new_v >= 2 and all(int(v.get("view") or -1) == new_v for v in views_b.values())), "view": new_v, "primary": new_p}

        # G + H — isolate two, no Q, restore
        g1, g2 = "aws-node-3", "ovh-node-4"
        payload["isolate_G"] = {g1: isolate(g1, "isolate"), g2: isolate(g2, "isolate")}
        isolated.extend([g1, g2])
        g_round = run_round("G", nodes=["ovh-node-1", "ovh-node-2"])
        payload["tests"]["G"] = {"result": verdict(g_round.get("ok") is False), "round_ok": g_round.get("ok"), "reason": "q_unreachable_two_nodes"}
        payload["restore_G"] = {g1: isolate(g1, "restore"), g2: isolate(g2, "restore")}
        isolated = []
        payload["replica_H"] = replica_from_ovh1()
        after_h = independent_snapshot()
        heights = {(after_h[n].get("height"), after_h[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS}
        payload["tests"]["H"] = {"result": verdict(len(heights) == 1 and all(after_h[n].get("health_http") == 200 for n in OFFICIAL_COMPUTE_NODE_IDS)), "heights": {n: (after_h[n].get("height"), after_h[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS}}

        # I — restart one replica, recover view + chain
        target = "ovh-node-4"
        view_before = _http("GET", f"{HTTP[target]}/api/v1/consensus/pbft/view").get("view")
        height_before = _http("GET", f"{HTTP[target]}/api/v1/chain/status").get("height")
        payload["restart_I"] = _ssh(target, "sudo systemctl restart artcb; sleep 2; systemctl is-active artcb")
        time.sleep(4)
        up = False
        for _ in range(12):
            h = _http("GET", f"{HTTP[target]}/health")
            if h.get("http") == 200:
                up = True
                break
            time.sleep(2)
        view_after = _http("GET", f"{HTTP[target]}/api/v1/consensus/pbft/view").get("view")
        height_after = _http("GET", f"{HTTP[target]}/api/v1/chain/status").get("height")
        payload["tests"]["I"] = {"result": verdict(up and view_after == view_before and height_after == height_before), "view_before": view_before, "view_after": view_after, "height_before": height_before, "height_after": height_after, "active": up}

        # L — two more cycles
        l1 = run_round("L1")
        l2 = run_round("L2")
        payload["tests"]["L"] = {"result": verdict(bool(l1.get("ok")) and bool(l2.get("ok"))), "cycles": [l1.get("ok"), l2.get("ok")], "dur_ns": [l1.get("dur_ns"), l2.get("dur_ns")]}

        payload["replica_final"] = replica_from_ovh1()
        payload["after"] = independent_snapshot()
        payload["active_after"] = {
            nid: _ssh(nid, "systemctl is-active artcb; echo BOOK=$(wc -l < /home/ubuntu/artcb/data/chain/blocks.jsonl | tr -d ' '); echo R265=$(sudo iptables-save | grep -c artcb265 || true)").get("stdout")
            for nid in OFFICIAL_COMPUTE_NODE_IDS
        }
        results = {k: (v or {}).get("result") for k, v in payload["tests"].items()}
        all_pass = all(r == "PASS" for r in results.values()) if results else False
        ns_after = all(bool((payload["after"].get(n) or {}).get("trace_ns_ok")) for n in OFFICIAL_COMPUTE_NODE_IDS)
        payload["same_sha_after"] = _same_sha(payload["after"], want_sha)
        payload["results"] = results
        payload["PBFT_LIVE_E2E_PASS"] = bool(all_pass and ns_after and payload["same_sha_after"])
        if not payload["PBFT_LIVE_E2E_PASS"]:
            payload["PBFT_LIVE_E2E_NOT_VALIDATED"] = True
            payload["fail_reason"] = {k: r for k, r in results.items() if r != "PASS"}
    finally:
        for nid in list(isolated):
            isolate(nid, "restore")
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            _ssh(nid, "sudo iptables-save | grep -F artcb265 | sed 's/^-A //' | while read -r spec; do sudo iptables -D $spec 2>/dev/null || true; done; systemctl is-active artcb || sudo systemctl start artcb")

    dest_dir = ROOT / "logs"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"265_pbft_e2e_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (dest_dir / "265_pbft_e2e_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"wrote": str(dest), "PBFT_LIVE_E2E_PASS": payload.get("PBFT_LIVE_E2E_PASS"), "results": payload.get("results")}, indent=2))
    return 0 if payload.get("PBFT_LIVE_E2E_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
