#!/usr/bin/env python3
"""R270 live — PBFT certification campaign on the four official nodes.

Never claims CERTIFIED_100 unless every required matrix row is live PASS.
Unexecuted critical rows stay NOT_PROVEN. No wipe. No HPC. AWS stays t3.small.
Processes and iptables always restored.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live265_pbft_e2e as l265  # noqa: E402
import run_live266_pbft_cert as l266  # noqa: E402
from artcb.consensus.live_bft import n_f_q  # noqa: E402
from artcb.consensus.pbft_certification_matrix import (  # noqa: E402
    apply_result,
    finalize,
    independent_safety,
    new_matrix,
)
from artcb.consensus.pbft_finality import verify_certificate  # noqa: E402
from artcb.consensus.pbft_view import primary_of  # noqa: E402
from artcb.node_registry import (  # noqa: E402
    OFFICIAL_COMPUTE_NODE_IDS,
    official_pbft_n_f_q,
    official_pbft_replica_ids,
)

HTTP = l265.HTTP
VC_KEYS = (
    "kind", "protocol", "view", "from_view", "height", "last_hash", "replica_id",
    "reason", "message", "signature", "producer_ed25519_b64", "producer_pqc_b64", "ts_ns",
)


def _pass(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _mark(matrix: dict, row_id: str, ok: bool, *, level: str, proof: str, **extra) -> None:
    verdict = _pass(ok)
    apply_result(
        matrix,
        row_id,
        result=verdict,
        verdict=verdict,
        live_wan=verdict,
        level=level,
        proof=proof,
        **extra,
    )


def _not_exec(matrix: dict, row_id: str, why: str) -> None:
    apply_result(
        matrix,
        row_id,
        result="NOT_EXECUTED",
        verdict="NOT_PROVEN",
        live_wan="NOT_EXECUTED",
        level="L0",
        proof=why,
    )


def _complete(pp: dict, block: dict, view: int, nodes: list[str] | None = None) -> dict:
    nodes = nodes or list(OFFICIAL_COMPUTE_NODE_IDS)
    digest = str(pp.get("digest") or block.get("hash") or "")
    seq = int(block.get("index") or -1)
    primary = primary_of(view)
    for nid in nodes:
        if nid != primary:
            l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
    prepares = {}
    for nid in nodes:
        prepares[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": digest})
    for nid in nodes:
        for src, row in prepares.items():
            prep = row.get("prepare")
            if src == nid or not isinstance(prep, dict):
                continue
            l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": prep})
    cert = None
    commits = {}
    for nid in nodes:
        commits[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/commit", {"view": view, "seq": seq, "digest": digest})
        if isinstance(commits[nid].get("certificate"), dict):
            cert = commits[nid]["certificate"]
    for nid in nodes:
        cmsg = commits[nid].get("commit") if isinstance(commits[nid], dict) else None
        if not isinstance(cmsg, dict):
            continue
        for dst in nodes:
            if dst == nid:
                continue
            got = l265._http("POST", f"{HTTP[dst]}/api/v1/consensus/pbft/commit", {"commit": cmsg})
            if isinstance(got.get("certificate"), dict):
                cert = got["certificate"]
    writes = {}
    if isinstance(cert, dict) and verify_certificate(cert):
        for nid in nodes:
            writes[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/certificate", {"certificate": cert, "block": block})
    ok = bool(cert) and verify_certificate(cert) and all((writes.get(n) or {}).get("wrote") for n in nodes)
    return {"ok": ok, "seq": seq, "digest": digest, "writes": {n: (writes.get(n) or {}).get("wrote") for n in nodes}}


def _view_change(nodes: list[str], new_v: int, reason: str) -> tuple[list[dict], dict | None]:
    vcs = []
    for nid in nodes:
        r = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change", {"view": new_v, "reason": reason})
        if r.get("http") == 200:
            vcs.append({k: r.get(k) for k in VC_KEYS if r.get(k) is not None})
    for nid in nodes:
        for vc in vcs:
            if vc.get("replica_id") == nid:
                continue
            l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change/receive", {"view_change": vc})
    new_p = primary_of(new_v)
    nv = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs})
    nv_obj = nv.get("new_view") if isinstance(nv.get("new_view"), dict) else None
    if nv_obj:
        for nid in nodes:
            if nid == new_p:
                continue
            l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs, "new_view": nv_obj})
    return vcs, nv_obj


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    want = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    origin_main = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "origin/main"], text=True).strip()
    matrix = new_matrix()
    payload: dict = {
        "stamp": stamp,
        "protocol": "270-pbft-certification",
        "git_sha_agent": want,
        "origin_main": origin_main,
        "engine_sha_note": "live nodes must equal origin/main; engine PBFT last changed in f59dd88 if docs-only follow",
        "hpc": False,
        "wipe": False,
        "aws": "t3.small",
        # ~~n_f_q(4)~~ 2026-09-10T11:20:00Z — formule historique N=4, pas la membership live.
        "n_f_q_historical_four": list(n_f_q(4)),
        "n_f_q": list(official_pbft_n_f_q()),
        "official_pbft_replica_ids": list(official_pbft_replica_ids()),
        "official_compute_seeds": list(OFFICIAL_COMPUTE_NODE_IDS),
        "http_fanout": list(OFFICIAL_COMPUTE_NODE_IDS),
        "tests": {},
    }
    stopped: str | None = None
    isolated: list[str] = []
    netem: str | None = None
    try:
        freeze = l265.independent_snapshot()
        health0 = l265._http("GET", f"{HTTP['ovh-node-1']}/health")
        payload["freeze"] = {
            "n": {n: {k: (freeze[n] or {}).get(k) for k in ("git_sha", "height", "last_hash", "view", "primary", "chain_valid")} for n in OFFICIAL_COMPUTE_NODE_IDS},
            "genesis_hash": health0.get("genesis_hash"),
            "protocol_version": health0.get("protocol_version"),
            "pqc": health0.get("pqc"),
            "network_id": health0.get("network_id"),
        }
        sha_ok = l265._same_sha(freeze, origin_main)
        safety0 = independent_safety(freeze)
        payload["tests"]["FREEZE"] = {"ok": sha_ok and safety0["converged"], "sha_ok": sha_ok, "safety": safety0}
        _mark(matrix, "PBFT-P00", sha_ok and safety0["converged"], level="L4", proof="independent_snapshot ×4")
        _mark(matrix, "PBFT-P01", sha_ok, level="L4", proof=f"git_sha={origin_main}")
        if not sha_ok:
            payload["ok"] = False
            payload["reason"] = "sha_mismatch"
            payload["matrix"] = finalize(matrix)
            _write(payload, stamp)
            return 3

        round1 = l265.run_round("270-L01a")
        round2 = l265.run_round("270-L01b")
        after_l = l265.independent_snapshot()
        safety_l = independent_safety(after_l)
        liveness = bool(round1.get("ok") and round2.get("ok") and safety_l["converged"])
        payload["tests"]["L01"] = {
            "ok": liveness,
            "r1": {k: round1.get(k) for k in ("ok", "seq", "digest", "view", "primary")},
            "r2": {k: round2.get(k) for k in ("ok", "seq", "digest", "view", "primary")},
            "safety": safety_l,
        }
        _mark(matrix, "PBFT-L01", liveness, level="L4", proof="two certified public rounds ×4")
        _mark(matrix, "PBFT-X02", liveness, level="L4", proof="exclusive PBFT public append run_round")
        tip_after_l = str((after_l.get("ovh-node-1") or {}).get("last_hash") or "")
        time.sleep(3)
        after_wait = l265.independent_snapshot()
        unchanged = independent_safety(after_wait)["converged"] and str((after_wait.get("ovh-node-1") or {}).get("last_hash") or "") == tip_after_l
        payload["tests"]["S02"] = {"ok": unchanged, "tip": tip_after_l[:16]}
        _mark(matrix, "PBFT-S02", unchanged, level="L4", proof="tip unchanged after idle wait (not a full comms-cut)")
        _mark(matrix, "PBFT-S01", safety_l["converged"] and unchanged, level="L4", proof="no dual tip across L01; not exhaustive L6")

        view = int((after_wait.get("ovh-node-1") or {}).get("view") or 0)
        primary = primary_of(view)
        replica = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != primary][0]
        first = l265._http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/propose", {"graph_id": f"270-eq-{stamp}", "graph_root": "x", "source": "pbft:270"})
        second = l265._http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/propose", {"graph_id": f"270-eq-y-{stamp}", "graph_root": "y", "source": "pbft:270-y"})
        eq_ok = first.get("http") == 200 and second.get("http") == 409
        payload["tests"]["B01"] = {"ok": eq_ok, "first": first.get("http"), "second": second.get("http"), "detail": str(second.get("detail") or "")[:160]}
        _mark(matrix, "PBFT-B01", eq_ok, level="L6", proof="HTTP dual propose on live primary")
        pp = first.get("pre_prepare") if isinstance(first.get("pre_prepare"), dict) else None
        block = first.get("block") if isinstance(first.get("block"), dict) else None
        if pp and block:
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                if nid != primary:
                    l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
            digest = str(pp.get("digest") or block.get("hash") or "")
            seq = int(block.get("index") or -1)
            l265._http("POST", f"{HTTP[replica]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": digest})
            yprep = l265._http("POST", f"{HTTP[replica]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": "ab" * 32})
            p11 = yprep.get("http") == 409 or "not_accepted" in str(yprep.get("detail") or yprep.get("reason") or "")
            payload["tests"]["B02"] = {"ok": p11, "http": yprep.get("http"), "detail": str(yprep.get("detail") or yprep.get("reason") or "")[:160]}
            _mark(matrix, "PBFT-B02", p11, level="L6", proof="PREPARE Y after accepted X")
            fake = copy.deepcopy(pp)
            fake["view"] = int(view) + 9
            replay = l265._http("POST", f"{HTTP[replica]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": fake})
            replay_ok = replay.get("http") in (200, 409) and (
                replay.get("ok") is False or "invalid" in str(replay.get("reason") or replay.get("detail") or "").lower()
            )
            payload["tests"]["V02"] = {"ok": replay_ok, "http": replay.get("http"), "detail": str(replay.get("reason") or replay.get("detail") or "")[:160]}
            _mark(matrix, "PBFT-V02", replay_ok, level="L4", proof="wrong-view PRE-PREPARE rejected (HTTP 200 may wrap invalid_*)")
            fin = _complete(pp, block, view)
            payload["tests"]["B01_finish"] = fin
        else:
            _mark(matrix, "PBFT-B02", False, level="L6", proof="no pre_prepare")
            _not_exec(matrix, "PBFT-V02", "no pre_prepare")

        forged = l265._http(
            "POST",
            f"{HTTP[replica]}/api/v1/consensus/pbft/prepare",
            {"prepare": {"kind": "prepare", "view": view, "seq": 1, "digest": "cd" * 32, "replica_id": replica, "message": "P|x", "signature": "00", "protocol": "265-pbft-block-finality"}},
        )
        forged_ok = forged.get("http") in (409, 422) or forged.get("ok") is False
        payload["tests"]["B03"] = {"ok": forged_ok, "http": forged.get("http"), "detail": str(forged.get("detail") or forged.get("reason") or "")[:160]}
        _mark(matrix, "PBFT-B03", forged_ok, level="L6", proof="forged PREPARE HTTP")

        last_seq = int((l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/chain/status").get("height") or 1)) - 1
        cert_got = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/certificate?seq={last_seq}")
        cert = cert_got.get("certificate") if isinstance(cert_got.get("certificate"), dict) else None
        bind_ok = False
        dup_ok = False
        if cert and verify_certificate(cert):
            mismatch = dict(cert)
            mismatch["digest"] = "11" * 32
            p17 = l265._http("POST", f"{HTTP[replica]}/api/v1/consensus/pbft/certificate", {"certificate": mismatch, "block": {"index": last_seq, "hash": "22" * 32, "visibility": "public"}})
            bind_ok = p17.get("http") == 409
            codes = [l265._http("POST", f"{HTTP[replica]}/api/v1/consensus/pbft/certificate", {"certificate": cert}).get("http") for _ in range(20)]
            after_dup = l265.independent_snapshot()
            dup_ok = all(c in (200, 409) for c in codes) and independent_safety(after_dup)["converged"]
            payload["tests"]["S04"] = {"ok": bind_ok, "http": p17.get("http")}
            payload["tests"]["N07_small"] = {"ok": dup_ok, "codes": sorted(set(codes)), "n": len(codes)}
        _mark(matrix, "PBFT-S03", bind_ok, level="L4", proof="digest/hash binding via invalid cert")
        _mark(matrix, "PBFT-S04", bind_ok, level="L4", proof="cert≠block 409")
        _mark(matrix, "PBFT-N07", False, level="L4", proof="only 20 duplicates, not 1000x — NOT full")
        apply_result(matrix, "PBFT-N07", result="NOT_PROVEN", verdict="NOT_PROVEN", live_wan="PARTIAL", proof="20× duplicate cert only", level="L4")
        _mark(matrix, "PBFT-S05", True, level="L1", proof="covered by unit test_certificate_duplicate_replica_not_q — not re-live as L6")
        apply_result(matrix, "PBFT-S05", verdict="NOT_PROVEN", result="NOT_PROVEN", live_wan="NOT_EXECUTED", proof="L1 unit only on this SHA", level="L1")

        two = l265.run_round("270-Q01", nodes=["ovh-node-1", "ovh-node-2"])
        q01 = two.get("ok") is not True
        payload["tests"]["Q01"] = {"ok": q01, "two_node_round_ok": two.get("ok"), "reason": two.get("reason") or two.get("phase")}
        _mark(matrix, "PBFT-Q01", q01, level="L4", proof="run_round on 2 nodes must not finalize")

        # F04 crash replica (not primary), public tip conserved, then restore
        crash_target = replica
        l265._ssh(crash_target, "sudo systemctl stop artcb")
        stopped = crash_target
        down = l266.wait_health(crash_target, up=False)
        tip_down = independent_safety({n: l265.independent_snapshot().get(n) or {} for n in OFFICIAL_COMPUTE_NODE_IDS if n != crash_target})
        l265._ssh(crash_target, "sudo systemctl start artcb")
        up = l266.wait_health(crash_target, up=True)
        stopped = None
        after_crash = l265.independent_snapshot()
        f04 = down and up and after_crash[crash_target].get("health_http") == 200
        payload["tests"]["F04"] = {"ok": f04, "down": down, "up": up, "target": crash_target}
        _mark(matrix, "PBFT-F04", f04, level="L5", proof=f"stop/start {crash_target}")
        _mark(matrix, "PBFT-R01", f04, level="L5", proof="process restart")
        _mark(matrix, "PBFT-F01", f04, level="L5", proof="node down then up; not specifically primary-idle")

        # Combined crash + equivocation (C01): stop replica, dual propose, finalize on 3, restart, replica protocol
        lag = "ovh-node-2"
        if lag == primary_of(int((l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view").get("view") or 0))):
            lag = "aws-node-3"
        l265._ssh(lag, "sudo systemctl stop artcb")
        stopped = lag
        majority = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != lag]
        vnow = int(l265._http("GET", f"{HTTP[majority[0]]}/api/v1/consensus/pbft/view").get("view") or 0)
        prim = primary_of(vnow)
        if prim == lag:
            new_v = vnow + 1
            vcs, nv_obj = _view_change(majority, new_v, "270_lag_primary")
            payload["tests"]["C01_vc"] = {"vc": len(vcs), "nv": bool(nv_obj), "new_v": new_v}
            prim = primary_of(new_v)
            vnow = new_v
        px = l265._http("POST", f"{HTTP[prim]}/api/v1/consensus/pbft/propose", {"graph_id": f"270-c01-{stamp}", "graph_root": "c01", "source": "pbft:270-c01"})
        py = l265._http("POST", f"{HTTP[prim]}/api/v1/consensus/pbft/propose", {"graph_id": f"270-c01y-{stamp}", "graph_root": "c01y", "source": "pbft:270-c01y"})
        pp_c = px.get("pre_prepare") if isinstance(px.get("pre_prepare"), dict) else None
        block_c = px.get("block") if isinstance(px.get("block"), dict) else None
        round_m = _complete(pp_c, block_c, vnow, majority) if pp_c and block_c else {"ok": False, "reason": "no_pp"}
        l265._ssh(lag, "sudo systemctl start artcb")
        l266.wait_health(lag, up=True)
        stopped = None
        replica_ok = l265.replica_from_ovh1()
        after_c01 = l265.independent_snapshot()
        safety_c = independent_safety(after_c01)
        c01 = (
            px.get("http") == 200
            and py.get("http") == 409
            and bool(round_m.get("ok"))
            and safety_c["converged"]
        )
        payload["tests"]["C01"] = {
            "ok": c01,
            "eq": {"x": px.get("http"), "y": py.get("http")},
            "majority_round": {k: round_m.get(k) for k in ("ok", "seq", "digest")},
            "replica": replica_ok,
            "safety": safety_c,
            "lag": lag,
        }
        _mark(matrix, "PBFT-C01", c01, level="L6", proof="replica down + equivocation + majority certify + protocol replica")
        _mark(matrix, "PBFT-R02", bool(replica_ok.get("ok")) and safety_c["converged"], level="L5", proof="p2p/replica/run not jsonl-append")
        _mark(matrix, "PBFT-F02", bool(round_m.get("ok")), level="L5", proof="majority certified while one process down")
        _mark(matrix, "PBFT-F03", safety_c["converged"] and after_c01[lag].get("health_http") == 200, level="L5", proof="lagging node rejoined via replica")

        # 2-2 partition
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            l265._scp(nid, ROOT / "scripts" / "artcb266_partition_node.sh", "/home/ubuntu/artcb/scripts/artcb266_partition_node.sh")
        payload["isolate_N01"] = {
            "ovh-node-1": l266.isolate266("ovh-node-1", "isolate", l266.RIGHT_IPS),
            "ovh-node-2": l266.isolate266("ovh-node-2", "isolate", l266.RIGHT_IPS),
            "aws-node-3": l266.isolate266("aws-node-3", "isolate", l266.LEFT_IPS),
            "ovh-node-4": l266.isolate266("ovh-node-4", "isolate", l266.LEFT_IPS),
        }
        isolated = list(OFFICIAL_COMPUTE_NODE_IDS)
        left_round = l265.run_round("270-N01L", nodes=l266.LEFT)
        right_round = l265.run_round("270-N01R", nodes=l266.RIGHT)
        dual = bool(left_round.get("ok") and right_round.get("ok") and left_round.get("digest") != right_round.get("digest"))
        payload["restore_N01"] = {nid: l266.isolate266(nid, "restore", l266.RIGHT_IPS if nid in l266.LEFT else l266.LEFT_IPS) for nid in OFFICIAL_COMPUTE_NODE_IDS}
        isolated = []
        l265.replica_from_ovh1()
        after_p = l265.independent_snapshot()
        n01 = (not dual) and (left_round.get("ok") is not True) and (right_round.get("ok") is not True) and independent_safety(after_p)["converged"]
        payload["tests"]["N01"] = {
            "ok": n01,
            "left_ok": left_round.get("ok"),
            "right_ok": right_round.get("ok"),
            "dual_finality": dual,
            "after": independent_safety(after_p),
        }
        _mark(matrix, "PBFT-N01", n01, level="L5", proof="iptables 2-2, neither side Q=3")
        _mark(matrix, "PBFT-N02", independent_safety(after_p)["converged"], level="L5", proof="heal + replica_from_ovh1")

        # Primary death + new block + rejoin (F02/F03/V01) if not already done via C01
        snap = l265.independent_snapshot()
        vcur = int((snap.get("ovh-node-1") or {}).get("view") or 0)
        old_p = primary_of(vcur)
        l265._ssh(old_p, "sudo systemctl stop artcb")
        stopped = old_p
        majority = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != old_p]
        new_v = vcur + 1
        vcs, nv_obj = _view_change(majority, new_v, "270_primary_down")
        round_v = l265.run_round("270-F02", nodes=majority)
        l265._ssh(old_p, "sudo systemctl start artcb")
        l266.wait_health(old_p, up=True)
        stopped = None
        if nv_obj:
            l265._http("POST", f"{HTTP[old_p]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs, "new_view": nv_obj})
        l265.replica_from_ovh1()
        after_f = l265.independent_snapshot()
        v01 = len(vcs) >= 3 and bool(nv_obj) and bool(round_v.get("ok")) and independent_safety(after_f)["converged"]
        payload["tests"]["V01_F02"] = {
            "ok": v01,
            "old_primary": old_p,
            "new_view": new_v,
            "vc": len(vcs),
            "round": {k: round_v.get(k) for k in ("ok", "seq", "digest", "primary")},
            "safety": independent_safety(after_f),
        }
        _mark(matrix, "PBFT-V01", v01, level="L5", proof="VIEW-CHANGE majority + NEW-VIEW + certify")
        _mark(matrix, "PBFT-L02", v01, level="L5", proof="progress after primary down")

        # mild netem
        iface_row = l265._ssh("ovh-node-2", "ip -o route get 1.1.1.1 | awk '{print $5; exit}'")
        iface = (iface_row.get("stdout") or "").strip().splitlines()[-1] if iface_row.get("returncode") == 0 else ""
        netem_ok = False
        safe_iface = bool(iface) and all(c.isalnum() or c in ".-" for c in iface)
        if safe_iface:
            add = l265._ssh("ovh-node-2", f"sudo tc qdisc add dev {iface} root netem delay 100ms 2>/dev/null || sudo tc qdisc replace dev {iface} root netem delay 100ms")
            if add.get("returncode") == 0:
                netem = iface
                delayed = l265.run_round("270-N05")
                l265._ssh("ovh-node-2", f"sudo tc qdisc del dev {iface} root || true")
                netem = None
                netem_ok = bool(delayed.get("ok")) and independent_safety(l265.independent_snapshot())["converged"]
                payload["tests"]["N05"] = {"ok": netem_ok, "iface": iface, "round": {k: delayed.get(k) for k in ("ok", "seq", "digest")}}
                _mark(matrix, "PBFT-N05", netem_ok, level="L5", proof="100ms netem on ovh-node-2 then restore")
            else:
                _not_exec(matrix, "PBFT-N05", f"tc add failed rc={add.get('returncode')} {(add.get('stderr') or '')[:80]}")
        else:
            _not_exec(matrix, "PBFT-N05", f"no iface ({iface!r})")

        # Historical / code-inspected rows that this SHA did not fully re-run
        _not_exec(matrix, "PBFT-N03", "asymmetric iptables not executed")
        _not_exec(matrix, "PBFT-N04", "packet-loss sweep 1–50% not executed (production risk)")
        _not_exec(matrix, "PBFT-N06", "no middlebox reordering")
        _not_exec(matrix, "PBFT-N08", "combined loss+delay+reorder not executed")
        _not_exec(matrix, "PBFT-C02", "crash+partition+delay combined not executed")
        _not_exec(matrix, "PBFT-C03", "clock skew not executed")
        _not_exec(matrix, "PBFT-C04", "thousands of blocks long-run not executed")
        _not_exec(matrix, "PBFT-C05", "validator membership change not in live protocol")
        _not_exec(matrix, "PBFT-B04", "selective contradictory PREPARE to different nodes not executed")
        apply_result(matrix, "PBFT-B05", verdict="NOT_PROVEN", result="NOT_PROVEN", live_wan="NOT_EXECUTED", proof="P8 live was on 960f069; not re-run on this SHA", level="L0")
        apply_result(matrix, "PBFT-R03", verdict="NOT_PROVEN", result="NOT_PROVEN", live_wan="NOT_EXECUTED", proof="P14 truncate was on f59dd88 campaign; not re-run here", level="L0")
        apply_result(matrix, "PBFT-A01", verdict="NOT_PROVEN", result="NOT_PROVEN", live_wan="NOT_EXECUTED", proof="P15 live on f59dd88; not re-run this SHA campaign", level="L0")
        apply_result(matrix, "PBFT-A02", verdict="NOT_PROVEN", result="NOT_PROVEN", live_wan="NOT_EXECUTED", proof="P16 private fork then jsonl catch-up — public PBFT replicate not re-proven here", level="L0")
        apply_result(matrix, "PBFT-X01", verdict="NOT_PROVEN", result="NOT_PROVEN", live_wan="NOT_EXECUTED", proof="188 settlement BFT not re-run this SHA", level="L0")
        apply_result(matrix, "PBFT-X03", verdict="NOT_PROVEN", result="NOT_PROVEN", live_wan="NOT_EXECUTED", proof="wallets/PoL/HBP/ORG not exercised through this campaign", level="L0")
        apply_result(matrix, "PBFT-Q02", verdict="NOT_PROVEN", result="NOT_PROVEN", live_wan="NOT_EXECUTED", proof="F=2 is expected failure vs spec; not executed (would not certify)", level="L0")

        after = l265.independent_snapshot()
        payload["after"] = independent_safety(after)
        payload["matrix"] = finalize(matrix)
        payload["bft_settlement"] = matrix["rows"]  # filled below
        payload["bft_block_consensus"] = "PARTIALLY_VERIFIED" if payload["matrix"]["global_verdict"] == "PARTIALLY_VERIFIED" else payload["matrix"]["global_verdict"]
        payload["bft_settlement"] = "NOT_PROVEN"
        payload["certified_100"] = payload["matrix"]["certified_100"]
        payload["global_verdict"] = payload["matrix"]["global_verdict"]
        payload["ok"] = payload["global_verdict"] in ("PARTIALLY_VERIFIED", "CERTIFIED_100") and not payload["certified_100"]
        _write(payload, stamp)
        print(json.dumps({
            "certified_100": payload["certified_100"],
            "global_verdict": payload["global_verdict"],
            "totals": payload["matrix"]["totals"],
            "after": payload["after"],
            "sha": origin_main[:12],
        }, indent=2))
        return 0
    finally:
        if netem:
            l265._ssh("ovh-node-2", f"sudo tc qdisc del dev {netem} root || true")
        if stopped:
            l265._ssh(stopped, "sudo systemctl start artcb || true")
        if isolated:
            l266.restore_all()
        l266.restore_all()
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            l265._ssh(nid, "systemctl is-active artcb || sudo systemctl start artcb")


def _write(payload: dict, stamp: str) -> None:
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    dest = out / f"270_pbft_cert_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "270_pbft_cert_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    matrix = payload.get("matrix") or {}
    (out / "PBFT_CERTIFICATION_FINAL_latest.json").write_text(json.dumps(matrix, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
