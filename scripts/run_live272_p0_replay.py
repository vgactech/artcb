#!/usr/bin/env python3
"""R272 — P0 live replay after orphan-lock + prepared-set fixes.

Does not overlay R270/R271 as CERTIFIED_100. Healthy rounds first, then
B05, then network faults on a clean view. Never wipe. Restore tc/iptables.
"""

from __future__ import annotations

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

import run_live265_pbft_e2e as l265  # noqa: E402
import run_live266_pbft_cert as l266  # noqa: E402
import run_live271_close_not_proven as l271  # noqa: E402
from artcb.consensus.pbft_certification_matrix import independent_safety  # noqa: E402
from artcb.consensus.pbft_view import primary_of  # noqa: E402
from artcb.live import http_json, resolve_api_key, resolve_api_url  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = l265.HTTP
HEALTHY = max(3, int(os.environ.get("ARTCB272_HEALTHY", "10")))
LOSS_PCT = (1, 5, 10, 20, 30, 50)


def _finish_pp(pp: dict, block: dict, view: int, primary: str) -> dict:
    """Complete PREPARE→COMMIT→certificate for an already-accepted PRE-PREPARE."""
    from artcb.consensus.pbft_finality import verify_certificate

    digest = str(pp.get("digest") or block.get("hash") or "")
    seq = int(block.get("index") or -1)
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        if nid != primary:
            l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
    prepares = {
        n: l265._http("POST", f"{HTTP[n]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": digest})
        for n in OFFICIAL_COMPUTE_NODE_IDS
    }
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for src, row in prepares.items():
            prep = row.get("prepare")
            if src != nid and isinstance(prep, dict):
                l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": prep})
    cert = None
    commits = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        commits[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/commit", {"view": view, "seq": seq, "digest": digest})
        if isinstance(commits[nid].get("certificate"), dict):
            cert = commits[nid]["certificate"]
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        cmsg = commits[nid].get("commit") if isinstance(commits[nid], dict) else None
        if not isinstance(cmsg, dict):
            continue
        for dst in OFFICIAL_COMPUTE_NODE_IDS:
            if dst == nid:
                continue
            got = l265._http("POST", f"{HTTP[dst]}/api/v1/consensus/pbft/commit", {"commit": cmsg})
            if isinstance(got.get("certificate"), dict):
                cert = got["certificate"]
    writes = {}
    if isinstance(cert, dict) and verify_certificate(cert):
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            writes[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/certificate", {"certificate": cert, "block": block})
    ok = bool(cert) and verify_certificate(cert) and all((writes.get(n) or {}).get("wrote") for n in OFFICIAL_COMPUTE_NODE_IDS)
    return {"ok": ok, "seq": seq, "digest": digest, "writes": {n: (writes.get(n) or {}).get("wrote") for n in OFFICIAL_COMPUTE_NODE_IDS}}


def _write(payload: dict, stamp: str) -> None:
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    dest = out / f"272_p0_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "272_p0_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    origin_main = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "origin/main"], text=True).strip()
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    payload: dict = {
        "stamp": stamp,
        "protocol": "272-p0-orphan-prepared",
        "origin_main": origin_main,
        "git_sha_agent": head,
        "hpc": False,
        "wipe": False,
        "overlay_forbidden": True,
        "certified_100_claim": False,
        "tests": {},
    }
    try:
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            l265._scp(nid, ROOT / "scripts" / "artcb271_netem.sh", "/home/ubuntu/artcb/scripts/artcb271_netem.sh")
            l265._scp(nid, ROOT / "scripts" / "artcb271_asym.sh", "/home/ubuntu/artcb/scripts/artcb271_asym.sh")
            l265._ssh(nid, "chmod +x /home/ubuntu/artcb/scripts/artcb271_netem.sh /home/ubuntu/artcb/scripts/artcb271_asym.sh")
        freeze = l265.independent_snapshot()
        payload["before"] = independent_safety(freeze)
        payload["freeze_nodes"] = {
            n: {k: (freeze[n] or {}).get(k) for k in ("git_sha", "height", "last_hash", "view", "primary", "chain_valid")}
            for n in OFFICIAL_COMPUTE_NODE_IDS
        }
        payload["sha_equal"] = l265._same_sha(freeze, origin_main)
        if not payload["sha_equal"]:
            payload["sha_note"] = "live SHA != origin/main — results are SHA-specific"

        print("HEALTHY ROUNDS", HEALTHY, flush=True)
        from artcb.consensus.campaign_artifacts import final_status_from_attempts, record_attempt

        ok_n = 0
        last = None
        healthy_attempts: list[dict] = []
        for i in range(HEALTHY):
            rnd = l265.run_round(f"272-H{i}")
            if rnd.get("ok"):
                ok_n += 1
                last = rnd
                record_attempt(healthy_attempts, result="PASS", reason=f"H{i}")
            else:
                reason = str((rnd.get("proposed") or {}).get("detail") or rnd.get("reason") or "")
                record_attempt(healthy_attempts, result="FAIL", reason=reason)
                if reason.find("equivocation") >= 0:
                    l271._unlock_view("272_healthy_unlock")
                    rnd = l265.run_round(f"272-H{i}r")
                    if rnd.get("ok"):
                        ok_n += 1
                        last = rnd
                        record_attempt(healthy_attempts, result="PASS", recovery="VIEW_CHANGE", reason=f"H{i}r")
                    else:
                        record_attempt(
                            healthy_attempts,
                            result="FAIL",
                            recovery="VIEW_CHANGE",
                            reason=str((rnd.get("proposed") or {}).get("detail") or rnd.get("reason") or ""),
                        )
        payload["tests"]["healthy"] = {
            "ok": ok_n == HEALTHY,
            "ok_n": ok_n,
            "requested": HEALTHY,
            "attempts": healthy_attempts,
            "final_status": final_status_from_attempts(healthy_attempts),
            "last": {k: (last or {}).get(k) for k in ("ok", "seq", "digest")},
        }

        print("ORPHAN PP + VC", flush=True)
        v = int(l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view").get("view") or 0)
        prim = primary_of(v)
        orphan = l265._http(
            "POST",
            f"{HTTP[prim]}/api/v1/consensus/pbft/propose",
            {"graph_id": f"272-orphan-{stamp}", "graph_root": "orphan", "source": "pbft:272-orphan"},
        )
        second = l265._http(
            "POST",
            f"{HTTP[prim]}/api/v1/consensus/pbft/propose",
            {"graph_id": f"272-orphan-y-{stamp}", "graph_root": "y", "source": "pbft:272-y"},
        )
        same_view_eq = second.get("http") == 409 and "equivocation" in str(second.get("detail") or "")
        unlock = l271._unlock_view("272_orphan_vc")
        after = l265.run_round("272-orphan-heal")
        payload["tests"]["orphan"] = {
            "ok": same_view_eq and bool(after.get("ok")),
            "first_http": orphan.get("http"),
            "second_http": second.get("http"),
            "second_detail": str(second.get("detail") or "")[:160],
            "same_view_equivocation": same_view_eq,
            "unlock": {k: unlock.get(k) for k in ("from_view", "to_view", "vc_n", "primary")},
            "heal": {k: after.get(k) for k in ("ok", "seq", "digest", "phase")},
        }

        print("B05 prepared X / refuse Y", flush=True)
        v = int(l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view").get("view") or 0)
        prim = primary_of(v)
        proposed = l265._http(
            "POST",
            f"{HTTP[prim]}/api/v1/consensus/pbft/propose",
            {"graph_id": f"272-p8-{stamp}", "graph_root": "p8", "source": "pbft:272-p8"},
        )
        pp = proposed.get("pre_prepare") if isinstance(proposed.get("pre_prepare"), dict) else None
        block = proposed.get("block") if isinstance(proposed.get("block"), dict) else None
        b05 = {"ok": False, "propose_http": proposed.get("http"), "detail": str(proposed.get("detail") or "")[:160]}
        if pp and block:
            digest = str(pp.get("digest") or "")
            seq = int(block.get("index") or -1)
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                if nid != prim:
                    l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
            prepares = {
                n: l265._http("POST", f"{HTTP[n]}/api/v1/consensus/pbft/prepare", {"view": v, "seq": seq, "digest": digest})
                for n in OFFICIAL_COMPUTE_NODE_IDS
            }
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                for src, row in prepares.items():
                    prep = row.get("prepare")
                    if src != nid and isinstance(prep, dict):
                        l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": prep})
            vcs265 = []
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                r = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change-265", {"view": v + 1})
                if isinstance(r.get("view_change"), dict):
                    vcs265.append(r["view_change"])
            unlock = l271._unlock_view("272_p8")
            new_p = primary_of(int(unlock.get("to_view") or v + 1))
            selected = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/select-prepared", {"view_changes": vcs265})
            y = l265._http(
                "POST",
                f"{HTTP[new_p]}/api/v1/consensus/pbft/propose",
                {"graph_id": f"272-p8-y-{stamp}", "graph_root": "Y", "source": "pbft:272-y"},
            )
            x = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/client-request", {"block": block})
            fin = None
            if isinstance(x.get("pre_prepare"), dict):
                fin = _finish_pp(x["pre_prepare"], x.get("block") or block, int(unlock.get("to_view") or v + 1), new_p)
            y_refused = y.get("http") == 409 and "must_repropose_prepared" in str(y.get("detail") or "")
            b05 = {
                "ok": bool(selected.get("proof")) and y_refused,
                "select_proof": selected.get("proof"),
                "bound": selected.get("bound"),
                "y_http": y.get("http"),
                "y_detail": str(y.get("detail") or "")[:160],
                "x_http": x.get("http"),
                "fin": {k: (fin or {}).get(k) for k in ("ok", "seq", "digest")} if fin else None,
                "vc265": len(vcs265),
            }
        payload["tests"]["B05"] = b05

        print("N03 N04 N06 N08 C03", flush=True)
        l265._ssh("ovh-node-1", "sudo bash /home/ubuntu/artcb/scripts/artcb271_asym.sh drop 91.134.45.8")
        round_a = l265.run_round("272-N03")
        during = independent_safety(l265.independent_snapshot())
        l265._ssh("ovh-node-1", "sudo bash /home/ubuntu/artcb/scripts/artcb271_asym.sh restore 91.134.45.8")
        l265.replica_from_ovh1()
        heal = l265.run_round("272-N03-heal")
        payload["tests"]["N03"] = {
            "ok": during["converged"] and bool(heal.get("ok")) and not (round_a.get("ok") is True and during["hash_unique"] > 1),
            "during_round": {k: round_a.get(k) for k in ("ok", "seq", "phase")},
            "heal": {k: heal.get(k) for k in ("ok", "seq", "digest")},
            "during_safety": during["converged"],
        }

        n04_rows = []
        live_1 = False
        safety_all = True
        for pct in LOSS_PCT:
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                l271._netem(nid, f"loss {pct}%")
            rnd = l265.run_round(f"272-loss{pct}")
            snap = independent_safety(l265.independent_snapshot())
            safety_all = safety_all and snap["converged"]
            if pct == 1 and rnd.get("ok"):
                live_1 = True
            n04_rows.append({"loss_pct": pct, "round_ok": bool(rnd.get("ok")), "seq": rnd.get("seq"), "reason": rnd.get("reason") or rnd.get("phase"), "safety": snap["converged"]})
            l271._clear_netem_all()
            time.sleep(1)
        payload["tests"]["N04"] = {"ok": safety_all and live_1, "liveness_1pct": live_1, "safety_all": safety_all, "rows": n04_rows}

        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            l271._netem(nid, "delay 40ms reorder 50% 25%")
        rnd6 = l265.run_round("272-N06")
        snap6 = independent_safety(l265.independent_snapshot())
        l271._clear_netem_all()
        payload["tests"]["N06"] = {"ok": snap6["converged"] and bool(rnd6.get("ok")), "round_ok": bool(rnd6.get("ok")), "seq": rnd6.get("seq"), "safety": snap6["converged"]}

        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            l271._netem(nid, "delay 80ms 20ms loss 10% reorder 25% 10%")
        rnd8 = l265.run_round("272-N08")
        snap8 = independent_safety(l265.independent_snapshot())
        l271._clear_netem_all()
        payload["tests"]["N08"] = {"ok": snap8["converged"] and bool(rnd8.get("ok")), "round_ok": bool(rnd8.get("ok")), "seq": rnd8.get("seq"), "safety": snap8["converged"]}

        skew = l265._ssh("ovh-node-2", "sudo timedatectl set-ntp false; sudo date -s '+70 seconds'; date -u +%s")
        rnd_sk = l265.run_round("272-C03")
        l265._ssh("ovh-node-2", "sudo timedatectl set-ntp true; sudo systemctl restart systemd-timesyncd 2>/dev/null || true")
        snap_sk = independent_safety(l265.independent_snapshot())
        payload["tests"]["C03"] = {"ok": snap_sk["converged"] and bool(rnd_sk.get("ok")), "skew_rc": skew.get("returncode"), "round_ok": bool(rnd_sk.get("ok")), "seq": rnd_sk.get("seq")}

        print("A02 X03", flush=True)
        url = resolve_api_url()
        key = resolve_api_key()
        eid = f"evt_272_{uuid.uuid4().hex[:12]}"
        body_a = {"event_id": eid, "kind": "observation", "content": f"272-A {stamp}", "visibility": "public", "tags": ["272"], "session_id": "272"}
        e1_h, e1 = http_json("POST", f"{url}/api/v1/agent/events", api_key=key, body=body_a, timeout=90)
        e2_h, e2 = http_json("POST", f"{url}/api/v1/agent/events", api_key=key, body={**body_a, "content": f"272-B {stamp}"}, timeout=60)
        after_a2 = independent_safety(l265.independent_snapshot())
        payload["tests"]["A02"] = {
            "ok": e1_h == 200 and e2_h == 409 and after_a2["converged"],
            "first": e1_h,
            "second": e2_h,
            "detail": str((e2 or {}).get("detail") if isinstance(e2, dict) else e2)[:160],
        }
        econ_h, _econ = http_json("GET", f"{url}/api/v1/economics/params", api_key=key, timeout=20)
        wal_h, _wal = http_json(
            "POST",
            f"{url}/api/v1/wallet/create",
            api_key=key,
            body={"name": f"w272_{stamp[8:14]}", "password": "artcb272-live"},
            timeout=30,
        )
        memo = l265.run_round("272-X03")
        payload["tests"]["X03"] = {
            "ok": econ_h == 200 and wal_h in (200, 409) and bool(memo.get("ok")),
            "economics_http": econ_h,
            "wallet_http": wal_h,
            "memo_round": {k: memo.get(k) for k in ("ok", "seq", "digest")},
        }

        after = l265.independent_snapshot()
        payload["after"] = independent_safety(after)
        payload["after_nodes"] = {
            n: {k: (after[n] or {}).get(k) for k in ("git_sha", "height", "last_hash", "view", "primary", "chain_valid")}
            for n in OFFICIAL_COMPUTE_NODE_IDS
        }
        executed = payload["tests"]
        payload["summary"] = {k: bool((v or {}).get("ok")) for k, v in executed.items()}
        payload["all_ok"] = all(payload["summary"].values()) if payload["summary"] else False
        _write(payload, stamp)
        print(json.dumps({"summary": payload["summary"], "all_ok": payload["all_ok"], "after": payload["after"]}, indent=2))
        return 0
    finally:
        l271._clear_netem_all()
        l271._restore_iptables()
        l265._ssh("ovh-node-2", "sudo timedatectl set-ntp true 2>/dev/null || true")
        l271._ensure_up()


if __name__ == "__main__":
    raise SystemExit(main())
