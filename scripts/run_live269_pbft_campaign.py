#!/usr/bin/env python3
"""R269 live — P9…P18 on the four official nodes. No HPC. No wipe.

Mutate certificates, Byzantine PREPARE, replay, crash/restart, truncated
PBFT state, agent identity/idempotency conflict, cert/block binding.
Processes restored. AWS stays the current t3.small.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.consensus.pbft_finality import verify_certificate  # noqa: E402
from artcb.consensus.pbft_view import primary_of  # noqa: E402
from artcb.live import http_json, resolve_api_key, resolve_api_url  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = l265.HTTP
STATE = "/home/ubuntu/artcb/data/consensus/pbft_finality.json"


def _mutate(cert: dict, kind: str) -> dict:
    row = copy.deepcopy(cert)
    commits = list(row.get("commits") or [])
    if kind == "view":
        row["view"] = int(row.get("view") or 0) + 9
    elif kind == "seq":
        row["seq"] = int(row.get("seq") or 0) + 99
    elif kind == "digest":
        row["digest"] = "ab" * 32
    elif kind == "replica_id_all":
        row["commits"] = [dict(c, replica_id="evil-node") for c in commits]
    elif kind == "signature_all":
        row["commits"] = [dict(c, signature="00" * 32) for c in commits]
    elif kind == "drop_commit":
        row["commits"] = commits[:1]
    elif kind == "dup_commit" and commits:
        row["commits"] = [commits[0], dict(commits[0]), dict(commits[0])]
    else:
        row["seq"] = 999999
    return row


def _wait(nid: str, *, up: bool, tries: int = 24) -> bool:
    for _ in range(tries):
        h = l265._http("GET", f"{HTTP[nid]}/health", timeout=8)
        alive = h.get("http") == 200
        if alive == up:
            return True
        time.sleep(2)
    return False


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    try:
        import subprocess

        want = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        want = ""
    payload: dict = {"stamp": stamp, "protocol": "269-pbft-p9-p18", "git_sha_agent": want, "hpc": False, "wipe": False}
    before = l265.independent_snapshot()
    payload["before"] = {
        n: {k: (before[n] or {}).get(k) for k in ("git_sha", "height", "last_hash", "view", "primary")}
        for n in OFFICIAL_COMPUTE_NODE_IDS
    }
    payload["sha_equal"] = l265._same_sha(before, want)
    tests: dict = {}
    payload["tests"] = tests
    if not payload["sha_equal"]:
        payload["ok"] = False
        payload["reason"] = "sha_mismatch"
        _write(payload, stamp)
        return 3

    tip = str((before.get("ovh-node-1") or {}).get("last_hash") or "")
    height = int((before.get("ovh-node-1") or {}).get("height") or 0)
    last_seq = height - 1
    view = int((before.get("ovh-node-1") or {}).get("view") or 0)
    primary = primary_of(view)
    replica = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != primary][0]

    got = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/certificate?seq={last_seq}")
    cert = got.get("certificate") if isinstance(got.get("certificate"), dict) else None
    tests["P9_have_cert"] = {"http": got.get("http"), "ok": bool(cert) and verify_certificate(cert)}
    kinds = ["view", "seq", "digest", "replica_id_all", "signature_all", "drop_commit", "dup_commit"]
    p9 = {}
    if cert:
        for kind in kinds:
            mutated = _mutate(cert, kind)
            r = l265._http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/certificate", {"certificate": mutated, "block": None})
            p9[kind] = {"http": r.get("http"), "detail": str(r.get("detail") or r.get("error") or "")[:180], "rejected": r.get("http") == 409}
        tests["P9"] = {"ok": all(v.get("rejected") for v in p9.values()), "cases": p9}
    else:
        tests["P9"] = {"ok": False, "reason": "no_cert"}

    proposed = l265._http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/propose", {"graph_id": f"269-p10-{stamp}", "graph_root": "x", "source": "pbft:269"})
    pp = proposed.get("pre_prepare") if isinstance(proposed.get("pre_prepare"), dict) else None
    block = proposed.get("block") if isinstance(proposed.get("block"), dict) else None
    second = l265._http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/propose", {"graph_id": f"269-p10-y-{stamp}", "graph_root": "y", "source": "pbft:269-y"})
    tests["P10"] = {
        "ok": proposed.get("http") == 200 and second.get("http") == 409,
        "first": proposed.get("http"),
        "second": second.get("http"),
        "detail": str(second.get("detail") or "")[:180],
    }
    seq = int((block or {}).get("index") or -1)
    digest = str((pp or {}).get("digest") or (block or {}).get("hash") or "")
    if pp:
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            if nid != primary:
                l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
    bad_prep = l265._http("POST", f"{HTTP[replica]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": "ee" * 32})
    tests["P11"] = {
        "ok": bad_prep.get("http") == 409,
        "http": bad_prep.get("http"),
        "detail": str(bad_prep.get("detail") or "")[:180],
    }
    if seq >= 0 and digest:
        good = l265._http("POST", f"{HTTP[replica]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": digest})
        replay = dict(good.get("prepare") or {})
        replay["view"] = view + 11
        inj = l265._http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/prepare", {"prepare": replay}) if replay else {"http": 0}
        tests["P12"] = {
            "ok": inj.get("http") == 409 or inj.get("ok") is False,
            "http": inj.get("http"),
            "detail": str(inj.get("detail") or inj.get("reason") or "")[:180],
        }
    else:
        tests["P12"] = {"ok": False, "reason": "no_prepare"}

    wrote = {}
    if pp and block and seq >= 0 and digest:
        prepares = {}
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            prepares[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": digest})
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            for src, row in prepares.items():
                prep = row.get("prepare")
                if src == nid or not isinstance(prep, dict):
                    continue
                l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": prep})
        cert2 = None
        commits = {}
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            commits[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/commit", {"view": view, "seq": seq, "digest": digest})
            if isinstance(commits[nid].get("certificate"), dict):
                cert2 = commits[nid]["certificate"]
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            cmsg = commits[nid].get("commit") if isinstance(commits[nid], dict) else None
            if not isinstance(cmsg, dict):
                continue
            for dst in OFFICIAL_COMPUTE_NODE_IDS:
                if dst == nid:
                    continue
                got = l265._http("POST", f"{HTTP[dst]}/api/v1/consensus/pbft/commit", {"commit": cmsg})
                if isinstance(got.get("certificate"), dict):
                    cert2 = got["certificate"]
        if cert2:
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                wrote[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/certificate", {"certificate": cert2, "block": block})
        tests["P10_finalize"] = {"ok": bool(cert2) and all(w.get("wrote") for w in wrote.values()), "cert": bool(cert2), "writes": {n: w.get("wrote") for n, w in wrote.items()}}
        if cert2:
            cert = cert2
            last_seq = seq
            tip = digest

    target = replica
    tests["P13_stop"] = l265._ssh(target, "sudo systemctl stop artcb; systemctl is-active artcb || true")
    down = _wait(target, up=False)
    tests["P13_start"] = l265._ssh(target, "sudo systemctl start artcb")
    up = _wait(target, up=True)
    after_crash = l265.independent_snapshot()
    tips = {(after_crash[n] or {}).get("last_hash") for n in OFFICIAL_COMPUTE_NODE_IDS}
    tests["P13"] = {
        "ok": down and up and len(tips) == 1 and str(next(iter(tips))) == tip,
        "down": down,
        "up": up,
        "tips": list(tips),
    }

    tests["P14_bak"] = l265._ssh(target, f"cp -a {STATE} /tmp/pbft_finality.bak269 && printf '{{truncated' > {STATE}")
    tests["P14_restart"] = l265._ssh(target, "sudo systemctl restart artcb")
    _wait(target, up=True)
    bogus = l265._http("GET", f"{HTTP[target]}/api/v1/consensus/pbft/certificate?seq={last_seq}")
    invented = bogus.get("http") == 200 and isinstance(bogus.get("certificate"), dict) and verify_certificate(bogus.get("certificate") or {})
    tests["P14_restore"] = l265._ssh(target, f"cp -a /tmp/pbft_finality.bak269 {STATE} && sudo systemctl restart artcb")
    restored = _wait(target, up=True)
    tests["P14"] = {
        "ok": restored and not invented,
        "invented_valid_cert": invented,
        "bogus_http": bogus.get("http"),
        "restored": restored,
    }

    url = resolve_api_url()
    key = resolve_api_key()
    aid = f"agent_269_{uuid.uuid4().hex[:8]}"
    r1_h, r1 = http_json("POST", f"{url}/api/v1/agent/register", api_key=key, body={"provider": "cursor", "label": "p15", "agent_id": aid, "capabilities": ["memory:read"]}, timeout=30)
    r2_h, r2 = http_json("POST", f"{url}/api/v1/agent/register", api_key=key, body={"provider": "claude", "label": "p15b", "agent_id": aid, "capabilities": ["memory:read"]}, timeout=30)
    tests["P15"] = {"ok": r1_h == 200 and r2_h == 409, "first": r1_h, "second": r2_h, "detail": str((r2 or {}).get("detail") if isinstance(r2, dict) else r2)[:180]}
    eid = f"evt_269_{uuid.uuid4().hex[:12]}"
    body_a = {"event_id": eid, "kind": "observation", "content": f"269-A {stamp}", "visibility": "private", "tags": ["269"], "session_id": "269"}
    e1_h, e1 = http_json("POST", f"{url}/api/v1/agent/events", api_key=key, body=body_a, timeout=60)
    e2_h, e2 = http_json("POST", f"{url}/api/v1/agent/events", api_key=key, body={**body_a, "content": f"269-B {stamp}"}, timeout=60)
    tests["P16"] = {
        "ok": e1_h == 200 and e2_h == 409,
        "first": e1_h,
        "second": e2_h,
        "detail": str((e2 or {}).get("detail") if isinstance(e2, dict) else e2)[:180],
        "includes_thinking": False,
    }

    if cert:
        mismatch = dict(cert)
        mismatch["digest"] = "11" * 32
        p17 = l265._http("POST", f"{HTTP[replica]}/api/v1/consensus/pbft/certificate", {"certificate": mismatch, "block": {"index": last_seq, "hash": tip, "visibility": "public"}})
        tests["P17"] = {"ok": p17.get("http") == 409, "http": p17.get("http"), "detail": str(p17.get("detail") or "")[:180]}
    else:
        tests["P17"] = {"ok": False}

    p18_ok = 0
    p18_n = 0
    if cert:
        for kind in kinds * 4:
            p18_n += 1
            mutated = _mutate(cert, kind)
            r = l265._http("POST", f"{HTTP[replica]}/api/v1/consensus/pbft/certificate", {"certificate": mutated})
            if r.get("http") == 409:
                p18_ok += 1
    tests["P18"] = {"ok": p18_n > 0 and p18_ok == p18_n, "rejected": p18_ok, "n": p18_n}

    after = l265.independent_snapshot()
    payload["after"] = {
        n: {k: (after[n] or {}).get(k) for k in ("git_sha", "height", "last_hash", "view", "primary")}
        for n in OFFICIAL_COMPUTE_NODE_IDS
    }
    after_tips = {(after[n] or {}).get("last_hash") for n in OFFICIAL_COMPUTE_NODE_IDS}
    payload["converged"] = len(after_tips) == 1
    payload["ok"] = bool(
        payload["sha_equal"]
        and payload["converged"]
        and all((tests.get(k) or {}).get("ok") for k in ("P9", "P10", "P10_finalize", "P11", "P12", "P13", "P14", "P15", "P16", "P17", "P18"))
    )
    _write(payload, stamp)
    summary = {k: (tests.get(k) or {}).get("ok") for k in ("P9", "P10", "P10_finalize", "P11", "P12", "P13", "P14", "P15", "P16", "P17", "P18")}
    print(json.dumps({"ok": payload["ok"], "sha_equal": payload["sha_equal"], "tests": summary, "height": (payload["after"].get("ovh-node-1") or {}).get("height")}, indent=2))
    return 0 if payload["ok"] else 4


def _write(payload: dict, stamp: str) -> None:
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    dest = out / f"269_p9_p18_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "269_p9_p18_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
