#!/usr/bin/env python3
"""R271 — execute the 18 R270 NOT_PROVEN rows on the live 4-node testnet.

Test mainnet: real iptables, real tc netem (loss/reorder/delay), real crashes.
Never wipe blocks.jsonl. Always restore tc, iptables, clocks, processes.
Does not claim CERTIFIED_100 unless every required row is live PASS.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live264_pbft_viewchange as l264  # noqa: E402
import run_live265_pbft_e2e as l265  # noqa: E402
import run_live266_pbft_cert as l266  # noqa: E402
from artcb.consensus.live_bft import LIVE_BFT_PROTOCOL, n_f_q  # noqa: E402
from artcb.consensus.pbft_certification_matrix import (  # noqa: E402
    apply_result,
    finalize,
    independent_safety,
    new_matrix,
)
from artcb.consensus.pbft_finality import verify_certificate, verify_preprepare  # noqa: E402
from artcb.consensus.pbft_view import primary_of  # noqa: E402
from artcb.economics.economic_snapshot import settlement_id  # noqa: E402
from artcb.live import http_json, resolve_api_key, resolve_api_url  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = l265.HTTP
HTTPS = l266.HTTPS
LONG_ROUNDS = max(8, int(os.environ.get("ARTCB271_LONG_ROUNDS", "40")))
LOSS_PCT = (1, 5, 10, 20, 30, 50)


def _mark(matrix, row_id, ok, *, level, proof, **extra) -> None:
    verdict = "PASS" if ok else "FAIL"
    apply_result(matrix, row_id, result=verdict, verdict=verdict, live_wan=verdict, level=level, proof=proof, **extra)


def _iface(nid: str) -> str:
    row = l265._ssh(nid, "ip -o route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i==\"dev\"){print $(i+1); exit}}'")
    return (row.get("stdout") or "").strip().splitlines()[-1] if row.get("returncode") == 0 else ""


def _netem(nid: str, spec: str | None) -> dict:
    iface = _iface(nid)
    if not iface or not all(c.isalnum() or c in ".-" for c in iface):
        return {"ok": False, "error": f"bad_iface:{iface!r}"}
    if spec is None:
        return l265._ssh(nid, f"sudo tc qdisc del dev {iface} root 2>/dev/null || true; echo CLEARED {iface}")
    quoted = spec.replace("'", "")
    return l265._ssh(nid, f"sudo tc qdisc del dev {iface} root 2>/dev/null || true; sudo tc qdisc add dev {iface} root netem {quoted}; tc qdisc show dev {iface} | head -1")


def _clear_netem_all() -> None:
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        _netem(nid, None)


def _restore_iptables() -> None:
    l266.restore_all()
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        l265._ssh(
            nid,
            "sudo iptables-save | grep -E 'artcb271' | sed 's/^-A //' | while read -r spec; do sudo iptables -D $spec 2>/dev/null || true; done; true",
        )


def _ensure_up() -> None:
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        l265._ssh(nid, "systemctl is-active artcb || sudo systemctl start artcb")


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    origin_main = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "origin/main"], text=True).strip()
    matrix = new_matrix()
    payload: dict = {
        "stamp": stamp,
        "protocol": "271-close-not-proven",
        "origin_main": origin_main,
        "hpc": False,
        "wipe": False,
        "aws": "t3.small",
        "n_f_q": list(n_f_q(4)),
        "long_rounds": LONG_ROUNDS,
        "tests": {},
    }
    stopped: list[str] = []
    try:
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            l265._scp(nid, ROOT / "scripts" / "artcb271_netem.sh", "/home/ubuntu/artcb/scripts/artcb271_netem.sh")
            l265._scp(nid, ROOT / "scripts" / "artcb271_asym.sh", "/home/ubuntu/artcb/scripts/artcb271_asym.sh")
            l265._ssh(nid, "chmod +x /home/ubuntu/artcb/scripts/artcb271_netem.sh /home/ubuntu/artcb/scripts/artcb271_asym.sh")

        freeze = l265.independent_snapshot()
        payload["before"] = independent_safety(freeze)
        payload["freeze_nodes"] = {n: {k: (freeze[n] or {}).get(k) for k in ("git_sha", "height", "last_hash", "view", "primary", "chain_valid")} for n in OFFICIAL_COMPUTE_NODE_IDS}
        sha_ok = l265._same_sha(freeze, origin_main)
        payload["sha_equal"] = sha_ok
        if not sha_ok:
            payload["reason"] = "sha_mismatch_live_vs_origin_main"
            # still execute: testnet, user demanded live on current nodes
            payload["sha_note"] = "continuing on deployed SHA anyway (test mainnet)"

        # --- X01 BFT_SETTLEMENT 188 ---
        view = int((freeze.get("ovh-node-1") or {}).get("view") or 0)
        wid = f"artcb271-{uuid.uuid4().hex[:12]}"
        s188 = l264.run_188(wid, view=view, nodes=list(OFFICIAL_COMPUTE_NODE_IDS))
        payload["tests"]["X01"] = s188
        _mark(matrix, "PBFT-X01", bool(s188.get("ok")), level="L4", proof="POST /consensus/prepare+commit Q=3 on 4 live nodes")

        # --- S05 duplicate replica_id in certificate ---
        last_seq = int((l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/chain/status").get("height") or 1)) - 1
        cert_got = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/certificate?seq={last_seq}")
        cert = cert_got.get("certificate") if isinstance(cert_got.get("certificate"), dict) else None
        s05 = False
        if cert:
            dup = copy.deepcopy(cert)
            if dup.get("commits"):
                c0 = dict(dup["commits"][0])
                dup["commits"] = [c0, dict(c0), dict(c0)]
            r = l265._http("POST", f"{HTTP['ovh-node-2']}/api/v1/consensus/pbft/certificate", {"certificate": dup})
            s05 = r.get("http") == 409
            payload["tests"]["S05"] = {"ok": s05, "http": r.get("http"), "detail": str(r.get("detail") or "")[:160]}
        _mark(matrix, "PBFT-S05", s05, level="L4", proof="duplicate replica commits rejected live")

        # --- N07 1000x duplicate cert ---
        n07_ok = False
        if cert:
            codes = []
            t0 = time.perf_counter()
            for _ in range(1000):
                codes.append(l265._http("POST", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/certificate", {"certificate": cert}).get("http"))
            after = independent_safety(l265.independent_snapshot())
            n07_ok = after["converged"] and all(c in (200, 409) for c in codes)
            payload["tests"]["N07"] = {"ok": n07_ok, "n": 1000, "codes": sorted(set(codes)), "dur_s": round(time.perf_counter() - t0, 2), "safety": after}
        _mark(matrix, "PBFT-N07", n07_ok, level="L5", proof="1000 identical certificate POSTs, tip unchanged/converged")

        # --- B04 selective PREPARE X vs Y ---
        views = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view")
        view = int(views.get("view") or 0)
        primary = primary_of(view)
        proposed = l265._http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/propose", {"graph_id": f"271-b04-{stamp}", "graph_root": "x", "source": "pbft:271-b04"})
        pp = proposed.get("pre_prepare") if isinstance(proposed.get("pre_prepare"), dict) else None
        block = proposed.get("block") if isinstance(proposed.get("block"), dict) else None
        b04 = False
        if pp and block:
            digest = str(pp.get("digest") or "")
            seq = int(block.get("index") or -1)
            others = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != primary]
            for nid in others:
                l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
            left, right = others[0], others[1]
            px = l265._http("POST", f"{HTTP[left]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": digest})
            py = l265._http("POST", f"{HTTP[right]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": "ee" * 32})
            b04 = px.get("http") == 200 and (py.get("http") == 409 or "not_accepted" in str(py.get("detail") or py.get("reason") or ""))
            fin = l265.run_round("271-b04-fin")
            payload["tests"]["B04"] = {"ok": b04, "px": px.get("http"), "py": py.get("http"), "py_detail": str(py.get("detail") or py.get("reason") or "")[:160], "finalize_after": bool(fin.get("ok"))}
        _mark(matrix, "PBFT-B04", b04, level="L6", proof="PREPARE X to one replica, PREPARE Y to another")

        # --- B05 prepared certificate in VIEW-CHANGE (P8 on this SHA) ---
        b05 = False
        payload["tests"]["B05_note"] = "inline P8-like on current SHA"
        vnow = int(l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view").get("view") or 0)
        prim = primary_of(vnow)
        proposed = l265._http("POST", f"{HTTP[prim]}/api/v1/consensus/pbft/propose", {"graph_id": f"271-p8-{stamp}", "graph_root": "p8", "source": "pbft:271-p8"})
        pp = proposed.get("pre_prepare") if isinstance(proposed.get("pre_prepare"), dict) else None
        block = proposed.get("block") if isinstance(proposed.get("block"), dict) else None
        if pp and block:
            digest = str(pp.get("digest") or "")
            seq = int(block.get("index") or -1)
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                if nid != prim:
                    l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
            prepares = {n: l265._http("POST", f"{HTTP[n]}/api/v1/consensus/pbft/prepare", {"view": vnow, "seq": seq, "digest": digest}) for n in OFFICIAL_COMPUTE_NODE_IDS}
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                for src, row in prepares.items():
                    prep = row.get("prepare")
                    if src != nid and isinstance(prep, dict):
                        l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": prep})
            new_v = vnow + 1
            new_p = primary_of(new_v)
            vcs265, vcs264 = [], []
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                r = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change-265", {"view": new_v})
                if isinstance(r.get("view_change"), dict):
                    vcs265.append(r["view_change"])
                r264 = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change", {"view": new_v, "reason": "271_p8"})
                if r264.get("http") == 200:
                    vcs264.append({k: r264.get(k) for k in ("kind", "protocol", "view", "from_view", "height", "last_hash", "replica_id", "reason", "message", "signature", "producer_ed25519_b64", "producer_pqc_b64", "ts_ns") if r264.get(k) is not None})
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                for vc in vcs264:
                    if vc.get("replica_id") != nid:
                        l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change/receive", {"view_change": vc})
            nv = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264})
            nv_obj = nv.get("new_view")
            if nv_obj:
                for nid in OFFICIAL_COMPUTE_NODE_IDS:
                    if nid != new_p:
                        l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264, "new_view": nv_obj})
            selected = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/select-prepared", {"view_changes": vcs265})
            y = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/propose", {"graph_id": f"271-p8-y-{stamp}", "graph_root": "Y", "source": "pbft:271-y"})
            b05 = bool(selected.get("proof")) and y.get("http") == 409
            repro = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/client-request", {"block": block})
            if isinstance(repro.get("pre_prepare"), dict):
                l265.run_round("271-p8-fin")
            payload["tests"]["B05"] = {"ok": b05, "select_proof": selected.get("proof"), "y_http": y.get("http"), "y_detail": str(y.get("detail") or "")[:160], "vc265": len(vcs265)}
        _mark(matrix, "PBFT-B05", b05, level="L5", proof="prepared proofs + Y refused after VC on this SHA")

        # --- R03 truncated finality json ---
        target = "ovh-node-2"
        state = "/home/ubuntu/artcb/data/consensus/pbft_finality.json"
        l265._ssh(target, f"cp -a {state} /tmp/pbft_finality.bak271 && printf '{{truncated' > {state}")
        l265._ssh(target, "sudo systemctl restart artcb")
        l266.wait_health(target, up=True)
        bogus = l265._http("GET", f"{HTTP[target]}/api/v1/consensus/pbft/certificate?seq={last_seq}")
        invented = bogus.get("http") == 200 and isinstance(bogus.get("certificate"), dict) and verify_certificate(bogus.get("certificate") or {})
        l265._ssh(target, f"cp -a /tmp/pbft_finality.bak271 {state} && sudo systemctl restart artcb")
        restored = l266.wait_health(target, up=True)
        r03 = restored and not invented
        payload["tests"]["R03"] = {"ok": r03, "invented": invented, "bogus_http": bogus.get("http"), "restored": restored}
        _mark(matrix, "PBFT-R03", r03, level="L5", proof="truncated pbft_finality.json does not invent a valid cert")

        # --- N03 asymmetric partition ---
        l265._ssh("ovh-node-1", "sudo bash /home/ubuntu/artcb/scripts/artcb271_asym.sh drop 91.134.45.8")
        left_ok = l265._http("GET", f"{HTTP['ovh-node-1']}/health").get("http") == 200
        right_ok = l265._http("GET", f"{HTTP['ovh-node-4']}/health").get("http") == 200
        round_a = l265.run_round("271-N03")
        after_a = independent_safety(l265.independent_snapshot())
        l265._ssh("ovh-node-1", "sudo bash /home/ubuntu/artcb/scripts/artcb271_asym.sh restore 91.134.45.8")
        l265.replica_from_ovh1()
        after_n03 = independent_safety(l265.independent_snapshot())
        n03 = left_ok and right_ok and after_n03["converged"] and not (round_a.get("ok") is True and after_a["hash_unique"] > 1)
        payload["tests"]["N03"] = {"ok": n03, "round": {k: round_a.get(k) for k in ("ok", "seq", "digest", "reason", "phase")}, "during": after_a, "after": after_n03}
        _mark(matrix, "PBFT-N03", n03, level="L5", proof="OUTPUT drop 1→4 only; INPUT still open; no dual tip")

        # --- N04 packet loss sweep ---
        n04_rows = []
        n04_safety = True
        n04_any_live = False
        for pct in LOSS_PCT:
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                _netem(nid, f"loss {pct}%")
            rnd = l265.run_round(f"271-loss{pct}")
            snap = independent_safety(l265.independent_snapshot())
            n04_safety = n04_safety and snap["converged"]
            n04_any_live = n04_any_live or bool(rnd.get("ok"))
            n04_rows.append({"loss_pct": pct, "round_ok": bool(rnd.get("ok")), "seq": rnd.get("seq"), "digest": rnd.get("digest"), "reason": rnd.get("reason") or rnd.get("phase"), "safety": snap["converged"]})
            _clear_netem_all()
            time.sleep(1)
        n04 = n04_safety and len(n04_rows) == len(LOSS_PCT)
        payload["tests"]["N04"] = {"ok": n04, "safety_all": n04_safety, "any_liveness": n04_any_live, "rows": n04_rows}
        _mark(matrix, "PBFT-N04", n04, level="L5", proof="tc netem loss 1,5,10,20,30,50% ×4 ifaces; safety=no dual tip")

        # --- N06 reorder ---
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            _netem(nid, "delay 40ms reorder 50% 25%")
        rnd6 = l265.run_round("271-N06")
        snap6 = independent_safety(l265.independent_snapshot())
        _clear_netem_all()
        n06 = snap6["converged"]
        payload["tests"]["N06"] = {"ok": n06, "round_ok": bool(rnd6.get("ok")), "seq": rnd6.get("seq"), "digest": rnd6.get("digest"), "safety": snap6}
        _mark(matrix, "PBFT-N06", n06, level="L5", proof="tc netem delay 40ms reorder 50% 25% ×4")

        # --- N08 loss+delay+reorder ---
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            _netem(nid, "delay 80ms 20ms loss 10% reorder 25% 10%")
        rnd8 = l265.run_round("271-N08")
        snap8 = independent_safety(l265.independent_snapshot())
        _clear_netem_all()
        n08 = snap8["converged"]
        payload["tests"]["N08"] = {"ok": n08, "round_ok": bool(rnd8.get("ok")), "seq": rnd8.get("seq"), "safety": snap8}
        _mark(matrix, "PBFT-N08", n08, level="L5", proof="combined delay+loss+reorder; safety required")

        # --- C02 crash + partition + delay ---
        crash = "aws-node-3"
        l265._ssh(crash, "sudo systemctl stop artcb")
        stopped.append(crash)
        l265._ssh("ovh-node-1", "sudo bash /home/ubuntu/artcb/scripts/artcb271_asym.sh drop 151.80.107.29")
        _netem("ovh-node-4", "delay 120ms")
        rnd_c = l265.run_round("271-C02")
        snap_c = independent_safety({n: (l265.independent_snapshot().get(n) or {}) for n in OFFICIAL_COMPUTE_NODE_IDS if n != crash})
        l265._ssh("ovh-node-1", "sudo bash /home/ubuntu/artcb/scripts/artcb271_asym.sh restore 151.80.107.29")
        _netem("ovh-node-4", None)
        l265._ssh(crash, "sudo systemctl start artcb")
        l266.wait_health(crash, up=True)
        stopped = [s for s in stopped if s != crash]
        l265.replica_from_ovh1()
        after_c02 = independent_safety(l265.independent_snapshot())
        c02 = after_c02["converged"]
        payload["tests"]["C02"] = {"ok": c02, "round_ok": bool(rnd_c.get("ok")), "during_majority_unique": snap_c.get("hash_unique"), "after": after_c02}
        _mark(matrix, "PBFT-C02", c02, level="L6", proof="aws-3 down + asym 1→2 + delay ovh4; restore; converge")

        # --- C03 clock skew ---
        skew = l265._ssh("ovh-node-2", "sudo timedatectl set-ntp false; sudo date -s '+70 seconds'; date -u +%s")
        rnd_sk = l265.run_round("271-C03")
        uns = l265._ssh("ovh-node-2", "sudo timedatectl set-ntp true; sudo systemctl restart systemd-timesyncd 2>/dev/null || true; date -u +%s")
        snap_sk = independent_safety(l265.independent_snapshot())
        c03 = snap_sk["converged"]
        payload["tests"]["C03"] = {"ok": c03, "skew_rc": skew.get("returncode"), "round_ok": bool(rnd_sk.get("ok")), "seq": rnd_sk.get("seq"), "ntp_rc": uns.get("returncode"), "safety": snap_sk}
        _mark(matrix, "PBFT-C03", c03, level="L5", proof="+70s clock on ovh-2 then NTP restore")

        # --- Q02 F=2 expected: two nodes down, remaining 2 cannot finalize ---
        a, b = "ovh-node-2", "aws-node-3"
        l265._ssh(a, "sudo systemctl stop artcb")
        l265._ssh(b, "sudo systemctl stop artcb")
        stopped.extend([a, b])
        majority2 = ["ovh-node-1", "ovh-node-4"]
        rnd_f2 = l265.run_round("271-Q02", nodes=majority2)
        q02 = rnd_f2.get("ok") is not True
        l265._ssh(a, "sudo systemctl start artcb")
        l265._ssh(b, "sudo systemctl start artcb")
        l266.wait_health(a, up=True)
        l266.wait_health(b, up=True)
        stopped = []
        l265.replica_from_ovh1()
        payload["tests"]["Q02"] = {"ok": q02, "two_node_round_ok": rnd_f2.get("ok"), "reason": rnd_f2.get("reason") or rnd_f2.get("phase"), "expected_failure": True}
        _mark(matrix, "PBFT-Q02", q02, level="L4", proof="F=2 (2 processes down): remaining 2 must not finalize — expected")

        # --- C05 membership: unknown replica_id rejected ---
        v = int(l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view").get("view") or 0)
        evil = l265._http("POST", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/prepare", {"prepare": {"kind": "prepare", "view": v, "seq": 1, "digest": "ab" * 32, "replica_id": "evil-node-5", "message": "P|x", "signature": "00", "protocol": "265-pbft-block-finality"}})
        c05 = evil.get("http") in (409, 422) or evil.get("ok") is False
        payload["tests"]["C05"] = {"ok": c05, "http": evil.get("http"), "detail": str(evil.get("detail") or evil.get("reason") or "")[:180]}
        _mark(matrix, "PBFT-C05", c05, level="L5", proof="replica_id outside official set rejected (no silent 5th validator)")

        # --- A01 / A02 agent ---
        url = resolve_api_url()
        key = resolve_api_key()
        aid = f"agent_271_{uuid.uuid4().hex[:8]}"
        r1_h, _r1 = http_json("POST", f"{url}/api/v1/agent/register", api_key=key, body={"provider": "cursor", "label": "p271", "agent_id": aid, "capabilities": ["memory:read"]}, timeout=30)
        r2_h, r2 = http_json("POST", f"{url}/api/v1/agent/register", api_key=key, body={"provider": "claude", "label": "p271b", "agent_id": aid, "capabilities": ["memory:read"]}, timeout=30)
        a01 = r1_h == 200 and r2_h == 409
        payload["tests"]["A01"] = {"ok": a01, "first": r1_h, "second": r2_h, "detail": str((r2 or {}).get("detail") if isinstance(r2, dict) else r2)[:160]}
        _mark(matrix, "PBFT-A01", a01, level="L4", proof="same agent_id different provider → 409")
        eid = f"evt_271_{uuid.uuid4().hex[:12]}"
        body_a = {"event_id": eid, "kind": "observation", "content": f"271-A {stamp}", "visibility": "public", "tags": ["271"], "session_id": "271"}
        e1_h, e1 = http_json("POST", f"{url}/api/v1/agent/events", api_key=key, body=body_a, timeout=90)
        e2_h, e2 = http_json("POST", f"{url}/api/v1/agent/events", api_key=key, body={**body_a, "content": f"271-B {stamp}"}, timeout=60)
        after_a2 = independent_safety(l265.independent_snapshot())
        a02 = e1_h == 200 and e2_h == 409 and after_a2["converged"]
        payload["tests"]["A02"] = {"ok": a02, "first": e1_h, "second": e2_h, "detail": str((e2 or {}).get("detail") if isinstance(e2, dict) else e2)[:160], "e1_status": (e1 or {}).get("status") if isinstance(e1, dict) else None, "safety": after_a2}
        _mark(matrix, "PBFT-A02", a02, level="L4", proof="public event then different payload 409; 4 tips")

        # --- X03 sample ARTCB features via live APIs / consensus ---
        econ_h, econ = http_json("GET", f"{url}/api/v1/economics/params", api_key=key, timeout=20)
        wal_h, wal = http_json("POST", f"{url}/api/v1/wallet/create", api_key=key, body={"label": f"271-{stamp[:8]}"}, timeout=30)
        memo_round = l265.run_round("271-X03")
        x03 = econ_h == 200 and bool(memo_round.get("ok")) and after_a2["converged"]
        payload["tests"]["X03"] = {"ok": x03, "economics_http": econ_h, "wallet_http": wal_h, "wallet_ok": bool((wal or {}).get("ok")) if isinstance(wal, dict) else wal_h, "memo_round": {k: memo_round.get(k) for k in ("ok", "seq", "digest")}, "h_adult_params": (econ or {}).get("h_adult") if isinstance(econ, dict) else None}
        _mark(matrix, "PBFT-X03", x03, level="L4", proof="economics params + wallet create + public PBFT round — not every product feature")

        # --- C04 long-run many certified blocks ---
        c04_ok_n = 0
        c04_fail = 0
        last_ok = None
        for i in range(LONG_ROUNDS):
            rnd = l265.run_round(f"271-L{i}")
            if rnd.get("ok"):
                c04_ok_n += 1
                last_ok = rnd
            else:
                c04_fail += 1
        snap_l = independent_safety(l265.independent_snapshot())
        c04 = c04_ok_n >= max(8, LONG_ROUNDS // 2) and snap_l["converged"] and c04_fail == 0
        payload["tests"]["C04"] = {"ok": c04, "requested": LONG_ROUNDS, "ok_n": c04_ok_n, "fail_n": c04_fail, "last": {k: (last_ok or {}).get(k) for k in ("ok", "seq", "digest")}, "safety": snap_l, "thousands": LONG_ROUNDS >= 1000}
        _mark(matrix, "PBFT-C04", c04, level="L5", proof=f"{c04_ok_n}/{LONG_ROUNDS} certified rounds live; thousands={LONG_ROUNDS>=1000}")

        after = l265.independent_snapshot()
        payload["after"] = independent_safety(after)
        payload["matrix"] = finalize(matrix)
        payload["certified_100"] = payload["matrix"]["certified_100"]
        payload["global_verdict"] = payload["matrix"]["global_verdict"]
        _write(payload, stamp)
        print(json.dumps({"certified_100": payload["certified_100"], "global_verdict": payload["global_verdict"], "totals": payload["matrix"]["totals"], "after": payload["after"]}, indent=2))
        return 0
    finally:
        _clear_netem_all()
        _restore_iptables()
        l265._ssh("ovh-node-2", "sudo timedatectl set-ntp true 2>/dev/null || true")
        for nid in stopped:
            l265._ssh(nid, "sudo systemctl start artcb || true")
        _ensure_up()


def _write(payload: dict, stamp: str) -> None:
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    dest = out / f"271_close_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "271_close_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
