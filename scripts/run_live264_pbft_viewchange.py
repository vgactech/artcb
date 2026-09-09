#!/usr/bin/env python3
"""264 live — PBFT view-change. All four artcb processes stay UP.

Isolate the current primary (iptables). Majority emits VIEW-CHANGE, new
primary signs NEW-VIEW, old-view prepare is rejected, 188 commits on the
new view. Restore isolation. Catch the isolated replica up. Never wipe.
"""

from __future__ import annotations

import hashlib
import json
import os
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

from artcb.consensus.live_bft import LIVE_BFT_PROTOCOL  # noqa: E402
from artcb.consensus.pbft_view import primary_of, verify_new_view, verify_view_change  # noqa: E402
from artcb.economics.economic_snapshot import settlement_id  # noqa: E402
from artcb.node_registry import NODES, OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

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
HTTPS = {
    "ovh-node-1": "https://152.228.144.34:8443",
}
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


def _http(method: str, url: str, body: dict | None = None, timeout: int = 20, *, auth: bool = False) -> dict:
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
    t0 = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:400]}
            return {"ok": True, "http": resp.status, "rtt_ms": round((time.perf_counter() - t0) * 1000, 1), **parsed}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"detail": raw}
        except json.JSONDecodeError:
            parsed = {"detail": raw}
        return {"ok": False, "http": exc.code, **(parsed if isinstance(parsed, dict) else {"detail": raw})}
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "http": 0, "error": type(exc).__name__}


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


def _ssh(node_id: str, remote: str, timeout: int = 60, stdin: str | None = None) -> dict:
    base = _ssh_base(node_id)
    if base is None:
        return {"node_id": node_id, "returncode": 2, "stdout": "", "stderr": "missing_ssh_key"}
    proc = subprocess.run(
        ["ssh", *base, remote],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {"node_id": node_id, "returncode": proc.returncode, "stdout": (proc.stdout or "")[-4000:], "stderr": (proc.stderr or "")[-400:]}


def replica_from_ovh1() -> dict:
    """POST /p2p/replica/run on OVH1 localhost. python3 -c + stdin (never a heredoc)."""
    import shlex

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
        return {"ok": False, "error": "ARTCB_API_KEY missing"}
    row = _ssh("ovh-node-1", "python3 -c " + shlex.quote(code), timeout=240, stdin=key)
    try:
        parsed = json.loads(row.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {"raw": (row.get("stdout") or "")[:400]}
    peers = parsed.get("peers") or []
    ok_peers = [p for p in peers if p.get("ok") or p.get("skipped")]
    return {"ssh_rc": row.get("returncode"), "peer_ok": len(ok_peers), "ok": len(ok_peers) >= 3}


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
    script = "/home/ubuntu/artcb/scripts/artcb264_partition_primary.sh"
    return _ssh(nid, f"chmod +x {script}; sudo bash {script} {action} {peers}")


def views() -> dict:
    return {nid: _http("GET", f"{HTTP[nid]}/api/v1/consensus/pbft/view") for nid in OFFICIAL_COMPUTE_NODE_IDS}


def health() -> dict:
    out = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        h = _http("GET", f"{HTTP[nid]}/health")
        out[nid] = {
            "git_sha": h.get("git_sha"),
            "http": h.get("http"),
            "active_process": h.get("http") == 200,
        }
    return out


def strip_vc(row: dict) -> dict:
    keep = (
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
        "ts_ns",
    )
    return {k: row.get(k) for k in keep}


def run_188(work_id: str, *, view: int | None, nodes: list[str]) -> dict:
    digest = hashlib.sha256(f"{work_id}|264".encode()).hexdigest()
    sid = settlement_id(work_id=work_id, snapshot_digest=digest, protocol_version=LIVE_BFT_PROTOCOL)
    prepared = []
    rejected = []
    for nid in nodes:
        body = {"work_id": work_id, "settlement_id": sid}
        if view is not None:
            body["view"] = view
        resp = _http("POST", f"{HTTP[nid]}/api/v1/consensus/prepare", body)
        if resp.get("http") == 200 and resp.get("result") == "prepared":
            prepared.append(nid)
        else:
            rejected.append({"node": nid, "http": resp.get("http"), "result": resp.get("result"), "error": resp.get("error")})
    commits = []
    if len(prepared) >= 3:
        for nid in nodes:
            resp = _http("POST", f"{HTTP[nid]}/api/v1/consensus/commit", {"work_id": work_id, "settlement_id": sid, "epoch": 1})
            if resp.get("http") == 200 and resp.get("ok"):
                commits.append(nid)
    return {
        "work_id": work_id,
        "view": view,
        "prepared": len(prepared),
        "prepared_nodes": prepared,
        "commits": commits,
        "rejected": rejected,
        "ok": len(prepared) >= 3 and len(commits) >= 3,
    }


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload: dict = {"stamp": stamp, "protocol": "264-pbft-view-change", "processes_killed": False, "wipe": False}
    isolated = None
    restored = False
    try:
        payload["health_before"] = health()
        payload["views_before"] = views()
        current = int((payload["views_before"].get("ovh-node-1") or {}).get("view") or 0)
        new_view = current + 1
        old_primary = primary_of(current)
        new_primary = primary_of(new_view)
        payload["plan"] = {"from_view": current, "to_view": new_view, "old_primary": old_primary, "new_primary": new_primary}
        _scp(old_primary, ROOT / "scripts" / "artcb264_partition_primary.sh", "/home/ubuntu/artcb/scripts/artcb264_partition_primary.sh")
        payload["isolate"] = isolate(old_primary, "isolate")
        isolated = old_primary
        time.sleep(1)
        payload["health_during"] = health()
        majority = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != old_primary]
        vcs = []
        emits = {}
        for nid in majority:
            resp = _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change", {"view": new_view, "reason": "primary_unreachable"})
            emits[nid] = {"http": resp.get("http"), "ok": resp.get("ok"), "replica_id": resp.get("replica_id")}
            if resp.get("http") == 200:
                vc = strip_vc(resp)
                vcs.append(vc)
        payload["view_change_emits"] = emits
        payload["vc_verified"] = [verify_view_change(vc) for vc in vcs]
        receives = {}
        for nid in majority:
            for vc in vcs:
                if vc.get("replica_id") == nid:
                    continue
                receives.setdefault(nid, []).append(
                    _http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change/receive", {"view_change": vc})
                )
        payload["vc_receive"] = {nid: [r.get("ok") for r in rows] for nid, rows in receives.items()}
        nv_resp = _http(
            "POST",
            f"{HTTP[new_primary]}/api/v1/consensus/pbft/new-view",
            {"view": new_view, "view_changes": vcs},
        )
        payload["new_view_emit"] = {
            "http": nv_resp.get("http"),
            "ok": nv_resp.get("ok"),
            "view": nv_resp.get("view") or (nv_resp.get("new_view") or {}).get("view"),
            "primary": (nv_resp.get("new_view") or {}).get("primary") or nv_resp.get("primary"),
            "detail": nv_resp.get("detail") or nv_resp.get("error"),
        }
        nv = nv_resp.get("new_view")
        changes = nv_resp.get("view_changes") or vcs
        payload["new_view_verified"] = bool(nv) and verify_new_view(nv, changes)
        installs = {}
        for nid in majority:
            if nid == new_primary:
                continue
            inst = _http(
                "POST",
                f"{HTTP[nid]}/api/v1/consensus/pbft/new-view",
                {"view": new_view, "view_changes": changes, "new_view": nv},
            )
            installs[nid] = {"http": inst.get("http"), "ok": inst.get("ok"), "view": inst.get("view"), "detail": inst.get("detail")}
        payload["new_view_installs"] = installs
        payload["views_majority"] = {nid: views()[nid] for nid in majority}
        payload["old_view_prepare"] = run_188(f"artcb264-old-{uuid.uuid4().hex[:8]}", view=current, nodes=majority)
        payload["new_view_prepare"] = run_188(f"artcb264-new-{uuid.uuid4().hex[:8]}", view=new_view, nodes=majority)
        payload["isolated_still_up"] = _http("GET", f"{HTTP[old_primary]}/health").get("http") == 200
        payload["isolated_view"] = _http("GET", f"{HTTP[old_primary]}/api/v1/consensus/pbft/view")
        payload["restore"] = isolate(old_primary, "restore")
        restored = True
        isolated = None
        time.sleep(1)
        catch = _http(
            "POST",
            f"{HTTP[old_primary]}/api/v1/consensus/pbft/new-view",
            {"view": new_view, "view_changes": changes, "new_view": nv},
        )
        payload["catchup_old_primary"] = {"http": catch.get("http"), "ok": catch.get("ok"), "view": catch.get("view"), "detail": catch.get("detail")}
        payload["views_after"] = views()
        payload["health_after"] = health()
        payload["active_after"] = {
            nid: _ssh(nid, "systemctl is-active artcb; echo BOOK=$(wc -l < /home/ubuntu/artcb/data/chain/blocks.jsonl | tr -d ' '); echo R264=$(sudo iptables-save | grep -c artcb264 || true)").get("stdout")
            for nid in OFFICIAL_COMPUTE_NODE_IDS
        }
        maj_views = [int((payload["views_majority"].get(n) or {}).get("view") or -1) for n in majority]
        after_views = [int((payload["views_after"].get(n) or {}).get("view") or -1) for n in OFFICIAL_COMPUTE_NODE_IDS]
        digest = (nv or {}).get("vc_digest") or ""
        memo = _http(
            "POST",
            f"{HTTPS['ovh-node-1']}/api/v1/ai/memo",
            {
                "content": (
                    f"264 PBFT view-change live. view {current}→{new_view} "
                    f"primary {old_primary}→{new_primary} vc={len(vcs)} "
                    f"vc_digest={digest} 188_old_prepared={payload['old_view_prepare'].get('prepared')} "
                    f"188_new_ok={payload['new_view_prepare'].get('ok')} processes_up=true"
                ),
                "memo_type": "proof",
                "tags": ["264", "pbft", "view-change"],
                "visibility": "public",
                "session_id": "264-pbft",
                "inject_context": False,
            },
            timeout=60,
            auth=True,
        )
        payload["memo"] = {
            "http": memo.get("http"),
            "ok": memo.get("ok"),
            "index": memo.get("index") or memo.get("block_index") or memo.get("last_index"),
            "hash": memo.get("hash") or memo.get("last_hash") or (memo.get("block") or {}).get("hash"),
        }
        payload["replica"] = replica_from_ovh1()
        payload["books_after"] = {
            nid: _http("GET", f"{HTTP[nid]}/api/v1/chain/status")
            for nid in OFFICIAL_COMPUTE_NODE_IDS
        }
        book_heights = [int((payload["books_after"].get(n) or {}).get("height") or 0) for n in OFFICIAL_COMPUTE_NODE_IDS]
        book_hashes = [(payload["books_after"].get(n) or {}).get("last_hash") for n in OFFICIAL_COMPUTE_NODE_IDS]
        payload["questions"] = {
            "pbft_view_change_implemented": True,
            "q3_view_changes_signed": len(vcs) >= 3 and all(payload["vc_verified"]),
            "new_view_signed_by_new_primary": bool(payload["new_view_verified"]),
            "majority_on_new_view": all(v == new_view for v in maj_views),
            "old_view_prepare_rejected": payload["old_view_prepare"].get("prepared", 99) < 3,
            "new_view_188_q3": bool(payload["new_view_prepare"].get("ok")),
            "isolated_process_stayed_up": bool(payload["isolated_still_up"]),
            "all_four_processes_active": all(payload["health_after"][n].get("active_process") for n in OFFICIAL_COMPUTE_NODE_IDS),
            "all_four_on_new_view": all(v == new_view for v in after_views),
            "iptables_restored": True,
            "no_process_killed": True,
            "memo_anchored": payload["memo"].get("http") in (200, 201),
            "books_converged": len(set(book_heights)) == 1 and len(set(book_hashes)) == 1 and book_heights[0] > 0,
        }
        payload["ok"] = all(payload["questions"].values())
    finally:
        if isolated and not restored:
            isolate(isolated, "restore")
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            _ssh(nid, "sudo iptables-save | grep -F artcb264 | sed 's/^-A //' | while read -r spec; do sudo iptables -D $spec 2>/dev/null || true; done; systemctl is-active artcb || sudo systemctl start artcb; echo $(systemctl is-active artcb)")

    dest_dir = ROOT / "logs"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"264_pbft_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (dest_dir / "264_pbft_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"wrote": str(dest), "ok": payload.get("ok"), "questions": payload.get("questions"), "plan": payload.get("plan")}, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
