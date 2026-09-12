#!/usr/bin/env python3
"""R331 — execute open P0s: auto VC probe, ORG commitment×4, pollution live, Mac restart.

Does not wipe. CERTIFIED_100 stays false unless all measured PASS.
Parallel to #77 live277 (run separately).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from artcb_dns_fix import install as _dns

    _dns()
except Exception:  # noqa: BLE001
    pass

SEEDS = {
    "ovh-node-1": "https://artcb.me",
    "ovh-node-2": "https://n2.artcb.me",
    "aws-node-3": "https://n3.artcb.me",
    "ovh-node-4": "https://n4.artcb.me",
}


def _git() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return ""


def http(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    auth: bool = False,
    timeout: float = 45.0,
) -> tuple[int, dict]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    key = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if auth and len(key) >= 16:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return int(r.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return int(e.code), json.loads(raw)
        except Exception:  # noqa: BLE001
            return int(e.code), {"detail": raw[:400]}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:200]}


def probe_auto_vc() -> dict:
    """Force VIEW-CHANGE to next *reachable* primary; measure Q + NEW-VIEW.

    Skips Mac-only views without public tunnel (Mac stays in membership).
    """
    from src.artcb.consensus.pbft_view import next_reachable_view, primary_of

    t0 = time.perf_counter_ns()
    _, v0 = http("GET", f"{SEEDS['ovh-node-4']}/api/v1/consensus/pbft/view")
    cur = int((v0 or {}).get("view") or 0)
    plan = next_reachable_view(cur)
    if not plan.get("ok"):
        return {"ok": False, "reason": "no_reachable_primary", "plan": plan, "pass_auto_vc": False}
    target = int(plan["target_view"])
    new_primary = str(plan["primary"])
    reason = f"r331_reachable_vc:from={cur}:to={target}:primary={new_primary}"
    emits: dict = {}
    vc_rows: list[dict] = []
    for nid, base in SEEDS.items():
        c, b = http(
            "POST",
            f"{base}/api/v1/consensus/pbft/view-change",
            body={"view": target, "reason": reason},
            auth=True,
        )
        emits[nid] = {"http": c, "ok": b.get("ok"), "replica_id": b.get("replica_id"), "detail": b.get("detail")}
        if c == 200 and isinstance(b, dict) and b.get("signature"):
            vc = {k: b[k] for k in b if k != "ok"}
            vc_rows.append(vc)
            for peer, pbase in SEEDS.items():
                if peer == nid:
                    continue
                http(
                    "POST",
                    f"{pbase}/api/v1/consensus/pbft/view-change/receive",
                    body={"view_change": vc},
                    auth=True,
                )
    quorums = {}
    for nid, base in SEEDS.items():
        c, b = http("GET", f"{base}/api/v1/consensus/pbft/view-changes?view={target}")
        rows = (b or {}).get("view_changes") or (b or {}).get("rows") or []
        quorums[nid] = {"http": c, "count": len(rows), "quorum": (b or {}).get("quorum") or (b or {}).get("ok")}
    primary_base = SEEDS.get(new_primary) or SEEDS["ovh-node-1"]
    c_nv, b_nv = http(
        "POST",
        f"{primary_base}/api/v1/consensus/pbft/new-view",
        body={"view": target, "view_changes": vc_rows},
        auth=True,
    )
    nv_fan = {}
    if c_nv == 200 and b_nv.get("new_view"):
        for nid, base in SEEDS.items():
            if nid == new_primary:
                continue
            ic, ib = http(
                "POST",
                f"{base}/api/v1/consensus/pbft/new-view",
                body={"view": target, "view_changes": vc_rows, "new_view": b_nv.get("new_view")},
                auth=True,
            )
            nv_fan[nid] = {"http": ic, "ok": ib.get("ok"), "detail": ib.get("detail") or ib.get("reason")}
    _, v1 = http("GET", f"{SEEDS['ovh-node-4']}/api/v1/consensus/pbft/view")
    view_after = (v1 or {}).get("view")
    q_ok = any(int(v.get("count") or 0) >= 3 for v in quorums.values())
    nv_ok = c_nv == 200 and bool(b_nv.get("ok") or b_nv.get("new_view"))
    view_moved = view_after is not None and int(view_after or 0) >= target
    return {
        "from_view": cur,
        "to_view": target,
        "plan": plan,
        "expected_primary": new_primary,
        "primary_of_check": primary_of(target),
        "vc_rows_collected": len(vc_rows),
        "emits": emits,
        "quorums": quorums,
        "new_view_primary": {
            "http": c_nv,
            "ok": b_nv.get("ok"),
            "detail": b_nv.get("detail") or b_nv.get("reason"),
            "has_new_view": bool(b_nv.get("new_view")),
        },
        "new_view_fanout": nv_fan,
        "view_after": view_after,
        "primary_after": (v1 or {}).get("primary"),
        "dur_ns": time.perf_counter_ns() - t0,
        "pass_auto_vc": bool(q_ok and (nv_ok or view_moved)),
    }


def probe_pollution() -> dict:
    """ΔPUBLIC must be 0 across status before any new public memo; then +1 after memo."""
    before = {}
    for nid, base in SEEDS.items():
        _, st = http("GET", f"{base}/api/v1/chain/status")
        before[nid] = int((st or {}).get("public_last_index") or -1)
    # private growth via artcb.me private memo
    c_priv, b_priv = http(
        "POST",
        "https://artcb.me/api/v1/ai/memo",
        body={
            "content": f"R331 private pollution probe {time.time_ns()}",
            "visibility": "private",
            "memo_type": "agent_note",
            "tags": ["r331", "pollution"],
        },
        auth=True,
    )
    mid = {}
    for nid, base in SEEDS.items():
        _, st = http("GET", f"{base}/api/v1/chain/status")
        mid[nid] = int((st or {}).get("public_last_index") or -1)
    public_stable = all(mid[n] == before[n] for n in SEEDS)
    c_pub, b_pub = http(
        "POST",
        "https://artcb.me/api/v1/ai/memo",
        body={
            "content": f"R331 public anchor probe {time.time_ns()}",
            "visibility": "public",
            "memo_type": "agent_note",
            "tags": ["r331", "public"],
        },
        auth=True,
    )
    time.sleep(2)
    after = {}
    for nid, base in SEEDS.items():
        _, st = http("GET", f"{base}/api/v1/chain/status")
        after[nid] = {
            "public_last_index": (st or {}).get("public_last_index"),
            "public_last_hash": str((st or {}).get("public_last_hash") or "")[:16],
            "private_suffix_lines": (st or {}).get("private_suffix_lines"),
            "ledger_mode": (st or {}).get("ledger_mode"),
        }
    tips = [int(after[n]["public_last_index"]) for n in SEEDS if after[n]["public_last_index"] is not None]
    return {
        "before": before,
        "after_private_memo": mid,
        "private_memo": {"http": c_priv, "block_index": (b_priv or {}).get("block_index")},
        "public_memo": {"http": c_pub, "block_index": (b_pub or {}).get("block_index"), "hash": str((b_pub or {}).get("block_hash") or "")[:16]},
        "after": after,
        "public_stable_after_private": public_stable,
        "public_advanced": c_pub == 200 and (b_pub or {}).get("block_index") is not None,
        "tips_equal": len(set(tips)) == 1 and len(tips) == 4,
    }


def probe_orgs() -> dict:
    rows = {}
    for nid, base in SEEDS.items():
        c, b = http("GET", f"{base}/api/v1/authz/orgs")
        orgs = (b or {}).get("orgs") if isinstance(b, dict) else []
        rows[nid] = {
            "http": c,
            "count": len(orgs or []),
            "hashes": sorted({str(o.get("content_hash") or "")[:16] for o in (orgs or []) if o.get("content_hash")}),
            "leak_founder": any("founder_address" in o for o in (orgs or [])),
        }
    return rows


def mac_restart() -> dict:
    """Restart local Mac launchd artcb if present — live process restart proof."""
    out: dict = {"attempted": False, "ok": False}
    plist = "me.artcb.node"
    try:
        r1 = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{plist}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out["print_rc"] = r1.returncode
        out["attempted"] = True
        if r1.returncode != 0:
            out["detail"] = "launchd_label_missing"
            return out
        h_before = http("GET", "http://127.0.0.1:8001/health")[1]
        st_before = http("GET", "http://127.0.0.1:8001/api/v1/chain/status")[1]
        out["before_sha"] = str((h_before or {}).get("git_sha") or "")[:12]
        out["before_public"] = (st_before or {}).get("public_last_index")
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{plist}"],
            timeout=30,
            check=False,
        )
        # wait until healthy (up to ~45s)
        after = (0, {})
        after_tip: dict = {}
        for _ in range(15):
            time.sleep(3)
            after = http("GET", "http://127.0.0.1:8001/health")
            if after[0] == 200 and (after[1] or {}).get("git_sha"):
                after_tip = http("GET", "http://127.0.0.1:8001/api/v1/chain/status")[1] or {}
                break
        out["after_http"] = after[0]
        out["after_sha"] = str((after[1] or {}).get("git_sha") or "")[:12]
        out["after_public"] = after_tip.get("public_last_index")
        out["public_preserved"] = out["before_public"] == out["after_public"] and out["after_public"] is not None
        out["ok"] = after[0] == 200 and bool(out["public_preserved"])
    except Exception as exc:  # noqa: BLE001
        out["error"] = type(exc).__name__
        out["detail"] = str(exc)[:200]
    return out


def probe_org_body_multinode() -> dict:
    """R330-A — try export ORG body from ovh1 + import hash-preserve on n2 (session ACL)."""
    out: dict = {"pass": False, "note": "requires session principal controller"}
    # List public commitments (no body)
    c1, b1 = http("GET", f"{SEEDS['ovh-node-1']}/api/v1/authz/orgs")
    orgs = (b1 or {}).get("orgs") if isinstance(b1, dict) else []
    out["ovh1_org_count"] = len(orgs or [])
    out["ovh1_hashes"] = sorted({str(o.get("content_hash") or "")[:16] for o in (orgs or []) if o.get("content_hash")})
    c2, b2 = http("GET", f"{SEEDS['ovh-node-2']}/api/v1/authz/orgs")
    orgs2 = (b2 or {}).get("orgs") if isinstance(b2, dict) else []
    out["ovh2_org_count"] = len(orgs2 or [])
    out["ovh2_hashes"] = sorted({str(o.get("content_hash") or "")[:16] for o in (orgs2 or []) if o.get("content_hash")})
    out["commitment_equal"] = bool(out["ovh1_hashes"]) and out["ovh1_hashes"] == out["ovh2_hashes"]
    # Body export needs session auth — measure honest 401 without inventing credentials
    if orgs:
        dom = None
        # domains list if exposed
        cd, bd = http("GET", f"{SEEDS['ovh-node-1']}/api/v1/authz/domains")
        out["domains_http"] = cd
        domains = (bd or {}).get("domains") if isinstance(bd, dict) else []
        for d in domains or []:
            if d.get("domain_type") == "organization":
                dom = d.get("domain_id")
                break
        if dom:
            ce, be = http("POST", f"{SEEDS['ovh-node-1']}/api/v1/authz/domains/{dom}/export", auth=True)
            out["export_http"] = ce
            out["export_detail"] = (be or {}).get("detail") or (be or {}).get("error")
            if ce == 200 and isinstance(be, dict) and be.get("genesis_body"):
                out["export_hash"] = str((be.get("manifest") or {}).get("genesis_hash") or "")[:16]
                ci, bi = http(
                    "POST",
                    f"{SEEDS['ovh-node-2']}/api/v1/authz/domains/import",
                    body={"bundle": be},
                    auth=True,
                )
                out["import_http"] = ci
                out["import_detail"] = (bi or {}).get("detail") or (bi or {}).get("error")
                out["pass"] = ci in (200, 409) and (
                    (bi or {}).get("imported") is True
                    or str(out.get("import_detail") or "").startswith("already")
                    or ci == 409
                )
            else:
                out["note"] = "export_requires_session_controller"
        else:
            out["note"] = "no_org_domain_id_listed"
    # Unit-equivalent: commitment×4 probe already in orgs; body multi-node remains OPEN if export 401
    if out.get("export_http") in (401, 403) or out.get("note") == "export_requires_session_controller":
        out["body_multinode"] = "NOT_PROVEN_acl_session"
    elif out.get("pass"):
        out["body_multinode"] = "PASS"
    else:
        out["body_multinode"] = "OPEN"
    return out


def main() -> int:
    # load key
    for p in (Path.home() / ".artcb/cursor_agent.env", Path.home() / ".artcb/cursor_hooks.env"):
        if p.is_file():
            for line in p.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    commit = _git()
    out: dict = {
        "measurement_id": f"R331_{time.strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}",
        "ts_ns": time.time_ns(),
        "commit_sha": commit,
        "certified_100": False,
        "issues": {"77": "OPEN_until_live277", "86": "IN_PROGRESS"},
    }
    out["orgs"] = probe_orgs()
    out["org_body_multinode"] = probe_org_body_multinode()
    out["pollution"] = probe_pollution()
    vc = probe_auto_vc()
    out["auto_vc"] = vc
    out["mac_restart"] = mac_restart()

    out["criteria"] = {
        "pollution_private_no_public_move": out["pollution"]["public_stable_after_private"],
        "public_memo_ok": out["pollution"]["public_advanced"],
        "tips_equal_after": out["pollution"]["tips_equal"],
        "org_no_founder_leak": all(not out["orgs"][n]["leak_founder"] for n in SEEDS),
        "org_body_multinode": out["org_body_multinode"].get("body_multinode"),
        "auto_vc_measured": bool(vc.get("pass_auto_vc")),
        "mac_restart_live": bool(out["mac_restart"].get("ok")),
        "O_certified_100": False,
    }
    d = ROOT / "logs" / "R331"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "measurement.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "criteria": out["criteria"], "vc_view": vc.get("view_after"), "tips": out["pollution"].get("after")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
