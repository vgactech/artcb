#!/usr/bin/env python3
"""266 live — exclusive PBFT + Byzantine signed PP + crash/partition/restart.

Does not re-claim TEST A as unknown. Measures V-01…V-07 on the four official
nodes after they run the SHA under test. Processes restored; iptables artcb266
wiped. Never wipe the book.
"""

from __future__ import annotations

import json
import os
import shlex
import ssl
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.consensus.pbft_finality import verify_certificate, verify_preprepare  # noqa: E402
from artcb.consensus.pbft_view import primary_of  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402
from artcb.trace.ns import is_nanosecond_ts  # noqa: E402

HTTP = l265.HTTP
HTTPS = {
    "ovh-node-1": "https://152.228.144.34:8443",
    "ovh-node-2": "https://151.80.107.29:8443",
    "aws-node-3": "https://51.44.222.232:8443",
    "ovh-node-4": "https://91.134.45.8:8443",
}
CTX = ssl._create_unverified_context()
LEFT = ["ovh-node-1", "ovh-node-2"]
RIGHT = ["aws-node-3", "ovh-node-4"]
LEFT_IPS = ["152.228.144.34", "151.80.107.29"]
RIGHT_IPS = ["51.44.222.232", "91.134.45.8"]


def _http(method: str, url: str, body: dict | None = None, timeout: int = 40, *, auth: bool = False) -> dict:
    return l265._http(method, url, body, timeout=timeout, auth=auth)


def isolate266(nid: str, action: str, peers: list[str]) -> dict:
    peer_s = " ".join(peers)
    script = "/home/ubuntu/artcb/scripts/artcb266_partition_node.sh"
    return l265._ssh(nid, f"chmod +x {script}; sudo bash {script} {action} {peer_s}")


def ns_pbft_ok() -> tuple[bool, dict]:
    out = {}
    ok = True
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        tr = _http("GET", f"{HTTP[nid]}/api/v1/trace?limit=400")
        rows = [r for r in (tr.get("rows") or []) if str(r.get("kind") or "").startswith("pbft_")]
        unit = tr.get("unit") == "nanosecond"
        ts = bool(rows) and all(is_nanosecond_ts(r.get("ts_ns")) for r in rows)
        dur = bool(rows) and all("dur_ns" in r for r in rows)
        node_ok = bool(rows) and unit and ts and dur
        out[nid] = {"http": tr.get("http"), "pbft_rows": len(rows), "unit": tr.get("unit"), "ok": node_ok}
        ok = ok and node_ok
    return ok, out


def wait_health(nid: str, *, up: bool, tries: int = 20) -> bool:
    for _ in range(tries):
        h = _http("GET", f"{HTTP[nid]}/health", timeout=8)
        alive = h.get("http") == 200
        if alive == up:
            return True
        time.sleep(2)
    return False


def certs_for(seq: int) -> dict:
    out = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        row = _http("GET", f"{HTTP[nid]}/api/v1/consensus/pbft/certificate?seq={int(seq)}")
        cert = row.get("certificate") if isinstance(row.get("certificate"), dict) else None
        out[nid] = {
            "http": row.get("http"),
            "ok": bool(cert) and verify_certificate(cert),
            "digest": (cert or {}).get("digest"),
            "q": (cert or {}).get("q"),
        }
    return out


def dual_signed_pp(primary: str) -> dict:
    code = r"""
import json, sys
sys.path.insert(0, "/home/ubuntu/artcb")
sys.path.insert(0, "/home/ubuntu/artcb/src")
from pathlib import Path
from artcb.chain.manager import ChainManager
from artcb.consensus.pbft_finality import sign_preprepare, verify_preprepare
from artcb.consensus.pbft_view import PbftViewStore
from artcb.node_registry import official_replica_id
data = Path("/home/ubuntu/artcb/data")
chain = ChainManager(data / "chain" / "blocks.jsonl", key_path=data / "chain.key", enable_security=False)
rid = official_replica_id()
view = int(PbftViewStore(data, replica_id=rid).view)
x = json.loads(chain.append_block(graph_id="v02-x", graph_root="x", pol_score=0.1, visibility="public", source="pbft:v02", dry_run=True).to_json_line())
y = json.loads(chain.append_block(graph_id="v02-y", graph_root="y", pol_score=0.1, visibility="public", source="pbft:v02", dry_run=True).to_json_line())
pp_x = sign_preprepare(chain, view=view, replica_id=rid, block=x)
pp_y = sign_preprepare(chain, view=view, replica_id=rid, block=y)
print(json.dumps({"view": view, "replica": rid, "x": x, "y": y, "pp_x": pp_x, "pp_y": pp_y, "vx": verify_preprepare(pp_x), "vy": verify_preprepare(pp_y)}))
"""
    row = l265._ssh(primary, "cd /home/ubuntu/artcb && PYTHONPATH=src .venv/bin/python -c " + shlex.quote(code), timeout=60)
    try:
        parsed = json.loads((row.get("stdout") or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        parsed = {"raw": (row.get("stdout") or "")[:500], "stderr": (row.get("stderr") or "")[:300]}
        parsed["ssh_rc"] = row.get("returncode")
        parsed["ssh_stderr"] = (row.get("stderr") or "")[-400:]
        if "raw" not in parsed and not parsed.get("pp_x"):
            parsed["ssh_stdout"] = (row.get("stdout") or "")[-500:]
        return parsed


def dv02_flood() -> dict:
    t0 = time.perf_counter_ns()
    codes = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        got = []
        for _ in range(16):
            got.append(_http("GET", f"{HTTP[nid]}/health", timeout=8).get("http"))
        codes[nid] = got
    unauth = _http("DELETE", f"{HTTP['ovh-node-1']}/api/v1/p2p/peers/http%3A%2F%2F1.2.3.4%3A9", timeout=8)
    all_200 = all(c == 200 for row in codes.values() for c in row)
    return {
        "ok": all_200 and unauth.get("http") in (401, 404, 405, 422),
        "health_codes": {n: sorted(set(v)) for n, v in codes.items()},
        "unauth_http": unauth.get("http"),
        "dur_ns": time.perf_counter_ns() - t0,
        "not_syn": True,
    }


def restore_all() -> dict:
    out = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        out[nid] = l265._ssh(
            nid,
            "sudo iptables-save | grep -E 'artcb266|artcb265' | sed 's/^-A //' | while read -r spec; do sudo iptables -D $spec 2>/dev/null || true; done; "
            "systemctl is-active artcb || sudo systemctl start artcb; systemctl is-active artcb",
        ).get("stdout")
    return out


def want_test(name: str) -> bool:
    only = {x.strip() for x in (os.environ.get("ARTCB266_ONLY") or "").split(",") if x.strip()}
    return (not only) or name in only


def verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload: dict = {
        "stamp": stamp,
        "protocol": "266-pbft-exclusive-cert",
        "unit": "nanosecond",
        "wipe": False,
        "tests": {},
        "PBFT_LIVE_E2E_PASS": False,
    }
    stopped: str | None = None
    isolated: list[str] = []
    try:
        want_sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        payload["git_sha_agent"] = want_sha
        payload["before"] = l265.independent_snapshot()
        payload["same_sha_before"] = l265._same_sha(payload["before"], want_sha)
        payload["tests"]["V07"] = {
            "result": verdict(bool(payload["same_sha_before"])),
            "want": want_sha,
            "live": {n: (payload["before"].get(n) or {}).get("git_sha") for n in OFFICIAL_COMPUTE_NODE_IDS},
        }
        if not want_test("V07"):
            payload["tests"].pop("V07", None)

        t01 = time.perf_counter_ns()
        before_h = {n: (payload["before"].get(n) or {}).get("height") for n in OFFICIAL_COMPUTE_NODE_IDS}
        view0 = _http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view")
        memo_primary = primary_of(int(view0.get("view") or 0))
        memo_url = f"{HTTPS[memo_primary]}/api/v1/ai/memo"
        memo = _http(
            "POST",
            memo_url,
            {
                "content": f"266 V-01 exclusive PBFT public memo sha={want_sha[:12]}",
                "memo_type": "proof",
                "tags": ["266", "pbft", "exclusive", "V-01"],
                "visibility": "public",
                "session_id": "266-v01",
                "inject_context": False,
            },
            timeout=90,
            auth=True,
        )
        time.sleep(2)
        l265.replica_from_ovh1()
        after_memo = l265.independent_snapshot()
        seq = memo.get("block_index")
        certs = certs_for(int(seq)) if seq is not None else {}
        heights = {(after_memo[n].get("height"), after_memo[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS}
        grew = all(int(after_memo[n].get("height") or 0) > int(before_h.get(n) or 0) for n in OFFICIAL_COMPUTE_NODE_IDS)
        v01_ok = (
            memo.get("http") == 200
            and grew
            and len(heights) == 1
            and bool(certs)
            and all(c.get("ok") for c in certs.values())
            and len({c.get("digest") for c in certs.values()}) == 1
        )
        payload["tests"]["V01"] = {
            "result": verdict(v01_ok),
            "memo_http": memo.get("http"),
            "memo_primary": memo_primary,
            "memo_url_host": memo_primary,
            "block_index": seq,
            "block_hash": memo.get("block_hash"),
            "detail": memo.get("detail") or memo.get("error"),
            "certs": certs,
            "heights": {n: (after_memo[n].get("height"), after_memo[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS},
            "dur_ns": time.perf_counter_ns() - t01,
        }

        # V-02 — two valid signed PRE-PREPARE, 2-2 split, no dual finality.
        t02 = time.perf_counter_ns()
        view_now = _http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view")
        primary = primary_of(int(view_now.get("view") or 0))
        forged = dual_signed_pp(primary)
        pp_x, pp_y = forged.get("pp_x"), forged.get("pp_y")
        recv = {"x": {}, "y": {}}
        if isinstance(pp_x, dict) and isinstance(pp_y, dict):
            for nid in LEFT:
                recv["x"][nid] = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp_x})
            for nid in RIGHT:
                recv["y"][nid] = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp_y})
            seq2 = int((forged.get("x") or {}).get("index") or -1)
            digest_x = str((forged.get("x") or {}).get("hash") or "")
            digest_y = str((forged.get("y") or {}).get("hash") or "")
            view = int(forged.get("view") or view_now.get("view") or 0)
            for nid in LEFT:
                _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq2, "digest": digest_x})
            for nid in RIGHT:
                _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq2, "digest": digest_y})
            for nid in LEFT:
                _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/commit", {"view": view, "seq": seq2, "digest": digest_x})
            for nid in RIGHT:
                _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/commit", {"view": view, "seq": seq2, "digest": digest_y})
            cert_x = {n: _http("GET", f"{HTTP[n]}/api/v1/consensus/pbft/certificate?seq={seq2}") for n in LEFT}
            cert_y = {n: _http("GET", f"{HTTP[n]}/api/v1/consensus/pbft/certificate?seq={seq2}") for n in RIGHT}
            x_ok = any(verify_certificate(r.get("certificate")) for r in cert_x.values() if isinstance(r.get("certificate"), dict))
            y_ok = any(verify_certificate(r.get("certificate")) for r in cert_y.values() if isinstance(r.get("certificate"), dict))
            both = x_ok and y_ok and digest_x != digest_y
            v02_ok = (
                forged.get("vx") is True
                and forged.get("vy") is True
                and digest_x != digest_y
                and not both
                and verify_preprepare(pp_x)
                and verify_preprepare(pp_y)
            )
        else:
            v02_ok = False
            seq2 = -1
            digest_x = digest_y = ""
            x_ok = y_ok = False
            cert_x = cert_y = {}
        payload["tests"]["V02"] = {
            "result": verdict(v02_ok),
            "primary": primary,
            "ssh_rc": forged.get("ssh_rc"),
            "vx": forged.get("vx"),
            "vy": forged.get("vy"),
            "seq": seq2,
            "digest_x": digest_x,
            "digest_y": digest_y,
            "recv": {k: {n: r.get("http") for n, r in v.items()} for k, v in recv.items()},
            "cert_x_any": x_ok,
            "cert_y_any": y_ok,
            "dual_finality": bool(x_ok and y_ok and digest_x != digest_y),
            "dur_ns": time.perf_counter_ns() - t02,
        }

        # V-03 — conflicting certificate for an already-certified seq (V-01).
        t03 = time.perf_counter_ns()
        seq_c = int(seq) if seq is not None else 0
        conflict = _http(
            "POST",
            f"{HTTP['ovh-node-4']}/api/v1/consensus/pbft/certificate",
            {"certificate": {"protocol": "265-pbft-block-finality", "view": 2, "seq": seq_c, "digest": "ee" * 32, "commits": [], "q": 3}},
        )
        payload["tests"]["V03"] = {
            "result": verdict(conflict.get("http") == 409),
            "http": conflict.get("http"),
            "detail": conflict.get("detail"),
            "seq": seq_c,
            "dur_ns": time.perf_counter_ns() - t03,
        }

        # V-04 — stop current primary process, view-change, new block, start.
        t04 = time.perf_counter_ns()
        snap = l265.independent_snapshot()
        view_b = int((snap.get("ovh-node-1") or {}).get("view") or 0)
        old_p = primary_of(view_b)
        new_v = view_b + 1
        new_p = primary_of(new_v)
        payload["stop_V04"] = l265._ssh(old_p, "sudo systemctl stop artcb; systemctl is-active artcb || true")
        stopped = old_p
        wait_health(old_p, up=False, tries=10)
        majority = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != old_p]
        vcs264 = []
        for nid in majority:
            r264 = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change", {"view": new_v, "reason": "primary_process_down"})
            if r264.get("http") == 200:
                vcs264.append({k: r264.get(k) for k in ("kind", "protocol", "view", "from_view", "height", "last_hash", "replica_id", "reason", "message", "signature", "producer_ed25519_b64", "producer_pqc_b64", "ts_ns") if r264.get(k) is not None})
        for nid in majority:
            for vc in vcs264:
                if vc.get("replica_id") == nid:
                    continue
                _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change/receive", {"view_change": vc})
        nv = _http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264})
        nv_obj = nv.get("new_view")
        for nid in majority:
            if nid == new_p or not nv_obj:
                continue
            _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264, "new_view": nv_obj})
        round_v04 = l265.run_round("V04", nodes=majority)
        l265._ssh(old_p, "sudo systemctl start artcb")
        wait_health(old_p, up=True, tries=20)
        stopped = None
        if nv_obj:
            _http("POST", f"{HTTP[old_p]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264, "new_view": nv_obj})
        l265.replica_from_ovh1()
        after_v04 = l265.independent_snapshot()
        views_v04 = {n: int((after_v04[n] or {}).get("view") or -1) for n in OFFICIAL_COMPUTE_NODE_IDS}
        heights_v04 = {(after_v04[n].get("height"), after_v04[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS}
        v04_ok = (
            bool(round_v04.get("ok"))
            and len(vcs264) >= 3
            and all(v == new_v for v in views_v04.values())
            and len(heights_v04) == 1
            and after_v04[old_p].get("health_http") == 200
        )
        payload["tests"]["V04"] = {
            "result": verdict(v04_ok),
            "old_primary": old_p,
            "new_view": new_v,
            "new_primary": new_p,
            "vc264": len(vcs264),
            "round": {k: round_v04.get(k) for k in ("ok", "seq", "digest", "view", "primary", "dur_ns")},
            "views": views_v04,
            "heights": {n: (after_v04[n].get("height"), after_v04[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS},
            "dur_ns": time.perf_counter_ns() - t04,
        }

        # V-05 — 2-2 partition, no dual finality, restore.
        t05 = time.perf_counter_ns()
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            l265._scp(nid, ROOT / "scripts" / "artcb266_partition_node.sh", "/home/ubuntu/artcb/scripts/artcb266_partition_node.sh")
        height_before = _http("GET", f"{HTTP['ovh-node-1']}/api/v1/chain/status").get("height")
        payload["isolate_V05"] = {
            "ovh-node-1": isolate266("ovh-node-1", "isolate", RIGHT_IPS),
            "ovh-node-2": isolate266("ovh-node-2", "isolate", RIGHT_IPS),
            "aws-node-3": isolate266("aws-node-3", "isolate", LEFT_IPS),
            "ovh-node-4": isolate266("ovh-node-4", "isolate", LEFT_IPS),
        }
        isolated = list(OFFICIAL_COMPUTE_NODE_IDS)
        left_round = l265.run_round("V05L", nodes=LEFT)
        right_round = l265.run_round("V05R", nodes=RIGHT)
        left_h = {n: _http("GET", f"{HTTP[n]}/api/v1/chain/status") for n in LEFT}
        right_h = {n: _http("GET", f"{HTTP[n]}/api/v1/chain/status") for n in RIGHT}
        dual = bool(left_round.get("ok") and right_round.get("ok") and left_round.get("digest") != right_round.get("digest"))
        payload["restore_V05"] = {
            nid: isolate266(nid, "restore", RIGHT_IPS if nid in LEFT else LEFT_IPS) for nid in OFFICIAL_COMPUTE_NODE_IDS
        }
        isolated = []
        l265.replica_from_ovh1()
        after_part = l265.independent_snapshot()
        heights_p = {(after_part[n].get("height"), after_part[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS}
        v05_ok = (not dual) and (left_round.get("ok") is False) and (right_round.get("ok") is False) and len(heights_p) == 1
        payload["tests"]["V05"] = {
            "result": verdict(v05_ok),
            "left_ok": left_round.get("ok"),
            "right_ok": right_round.get("ok"),
            "dual_finality": dual,
            "height_before": height_before,
            "left_heights": {n: left_h[n].get("height") for n in LEFT},
            "right_heights": {n: right_h[n].get("height") for n in RIGHT},
            "after": {n: (after_part[n].get("height"), after_part[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS},
            "dur_ns": time.perf_counter_ns() - t05,
        }

        # V-06 — restart after certificate.
        t06 = time.perf_counter_ns()
        target = "ovh-node-4"
        view_before = _http("GET", f"{HTTP[target]}/api/v1/consensus/pbft/view").get("view")
        st_before = _http("GET", f"{HTTP[target]}/api/v1/chain/status")
        fin_before = _http("GET", f"{HTTP[target]}/api/v1/consensus/pbft/finality")
        seq_hold = int(seq) if seq is not None else int(st_before.get("height") or 1) - 1
        cert_before = _http("GET", f"{HTTP[target]}/api/v1/consensus/pbft/certificate?seq={seq_hold}")
        l265._ssh(target, "sudo systemctl restart artcb")
        wait_health(target, up=True, tries=20)
        view_after = _http("GET", f"{HTTP[target]}/api/v1/consensus/pbft/view").get("view")
        st_after = _http("GET", f"{HTTP[target]}/api/v1/chain/status")
        cert_after = _http("GET", f"{HTTP[target]}/api/v1/consensus/pbft/certificate?seq={seq_hold}")
        v06_ok = (
            st_after.get("http") == 200
            and st_after.get("height") == st_before.get("height")
            and st_after.get("last_hash") == st_before.get("last_hash")
            and view_after == view_before
            and (cert_after.get("certificate") or {}).get("digest") == (cert_before.get("certificate") or {}).get("digest")
        )
        payload["tests"]["V06"] = {
            "result": verdict(v06_ok),
            "view_before": view_before,
            "view_after": view_after,
            "height_before": st_before.get("height"),
            "height_after": st_after.get("height"),
            "hash_before": st_before.get("last_hash"),
            "hash_after": st_after.get("last_hash"),
            "cert_digest": (cert_after.get("certificate") or {}).get("digest"),
            "finality_before": fin_before.get("certificate_count"),
            "dur_ns": time.perf_counter_ns() - t06,
        }

        payload["dv02"] = dv02_flood()
        payload["tests"]["DV02"] = {"result": verdict(bool(payload["dv02"].get("ok"))), "probe": payload["dv02"]}

        ns_ok, ns_detail = ns_pbft_ok()
        payload["ns"] = ns_detail
        payload["replica_final"] = l265.replica_from_ovh1()
        payload["after"] = l265.independent_snapshot()
        payload["same_sha_after"] = l265._same_sha(payload["after"], want_sha)
        payload["active_after"] = {
            nid: l265._ssh(nid, "systemctl is-active artcb; echo BOOK=$(wc -l < /home/ubuntu/artcb/data/chain/blocks.jsonl | tr -d ' '); echo R266=$(sudo iptables-save | grep -c artcb266 || true)").get("stdout")
            for nid in OFFICIAL_COMPUTE_NODE_IDS
        }
        results = {k: (v or {}).get("result") for k, v in payload["tests"].items()}
        required = ("V01", "V02", "V03", "V04", "V05", "V06", "V07")
        all_pass = all(results.get(k) == "PASS" for k in required)
        payload["results"] = results
        payload["PBFT_LIVE_E2E_PASS"] = bool(all_pass and ns_ok and payload["same_sha_after"])
        if not payload["PBFT_LIVE_E2E_PASS"]:
            payload["PBFT_LIVE_E2E_NOT_VALIDATED"] = True
            payload["fail_reason"] = {k: results.get(k) for k in required if results.get(k) != "PASS"}
            if not ns_ok:
                payload["fail_reason"]["ns"] = "FAIL"
    finally:
        if stopped:
            l265._ssh(stopped, "sudo systemctl start artcb || true")
        restore_all()

    dest_dir = ROOT / "logs"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"266_pbft_cert_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (dest_dir / "266_pbft_cert_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"wrote": str(dest), "PBFT_LIVE_E2E_PASS": payload.get("PBFT_LIVE_E2E_PASS"), "results": payload.get("results")}, indent=2))
    return 0 if payload.get("PBFT_LIVE_E2E_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
