#!/usr/bin/env python3
"""Simulation 208 — finish DV-02 C (bounded HTTP flood) + DV-06 (netem) on live book.

Keep-book already done. Does not deploy, does not wipe, does not SYN-flood.
Updates validation/DV-02 and DV-06 RESULT.json only from measured outcomes.
Never flips OPERATOR_MAINNET_CERTIFICATION_GO.
"""

from __future__ import annotations

import json
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.devnet_validation import certification_gate, load_dv_verdicts  # noqa: E402
from artcb.node_registry import NODES, OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

CTX = ssl._create_unverified_context()
SSH = {
    "ovh-node-1": (Path.home() / ".ssh" / "artcb_ovh_deploy", ROOT / "deploy" / "ovh_artcb_node_1.known_hosts"),
    "ovh-node-2": (Path.home() / ".ssh" / "artcb_ovh_node_2", ROOT / "deploy" / "ovh_artcb_node_2.known_hosts"),
    "aws-node-3": (Path.home() / ".ssh" / "artcb_aws_node_3", ROOT / "deploy" / "aws_artcb_node_3.known_hosts"),
    "ovh-node-4": (Path.home() / ".ssh" / "artcb_ovh_node_4", ROOT / "deploy" / "ovh_artcb_node_4.known_hosts"),
}


def _http(url: str, method: str = "GET", body: dict | None = None, timeout: int = 8) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"Accept": "application/json"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=hdrs)
    try:
        with urlopen(req, timeout=timeout, context=CTX if url.startswith("https") else None) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:200]}
            return resp.status, parsed if isinstance(parsed, dict) else {"raw": parsed}
    except HTTPError as exc:
        return exc.code, {"detail": exc.read().decode("utf-8", errors="replace")[:200]}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__}


def _ssh(node_id: str, remote: str) -> dict:
    import subprocess

    key, known = SSH[node_id]
    spec = NODES[node_id]
    proc = subprocess.run(
        [
            "ssh",
            "-i",
            str(key),
            "-o",
            f"UserKnownHostsFile={known}",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            f"{spec.ssh_user}@{spec.ssh_host}",
            remote,
        ],
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    return {"rc": proc.returncode, "stdout": (proc.stdout or "")[-1500:], "stderr": (proc.stderr or "")[-400:]}


def flood(ip: str, n: int = 64) -> dict:
    def ping() -> int:
        code, _ = _http(f"http://{ip}:8000/health", timeout=8)
        return code

    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(lambda _: ping(), range(n)))
    return {"n": n, "http_200": codes.count(200), "codes": sorted(set(codes))}


def unauth_locks(ip: str) -> dict:
    d, _ = _http(f"http://{ip}:8000/api/v1/p2p/peers/peer_probe_unauth", method="DELETE")
    s, _ = _http(f"http://{ip}:8000/api/v1/p2p/sync", method="POST", body={})
    g, _ = _http(f"http://{ip}:8000/api/v1/p2p/gossip/announce", method="POST", body={})
    ssrf, _ = _http(
        f"http://{ip}:8000/api/v1/network/announce",
        method="POST",
        body={"node_public_url": "http://169.254.169.254/latest", "network_id": "artcb-mainnet-1"},
    )
    return {"delete": d, "sync": s, "gossip": g, "ssrf": ssrf}


def netem_ovh4() -> dict:
    apply_cmd = r"""
set -euo pipefail
IFACE=$(ip -o route get 1.1.1.1 | awk '{print $5; exit}')
echo IFACE=$IFACE
sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true
sudo tc qdisc add dev "$IFACE" root netem loss 25% delay 80ms
echo APPLY_OK
"""
    restore_cmd = r"""
set -euo pipefail
IFACE=$(ip -o route get 1.1.1.1 | awk '{print $5; exit}')
sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true
echo RESTORED_IFACE=$IFACE
"""
    applied = _ssh("ovh-node-4", apply_cmd)
    during = []
    try:
        for i in range(12):
            code, _ = _http("http://91.134.45.8:8000/health", timeout=6)
            during.append({"try": i + 1, "http": code})
            time.sleep(0.4)
    finally:
        restored = _ssh("ovh-node-4", restore_cmd)
    time.sleep(2)
    after = []
    for i in range(8):
        code, _ = _http("http://91.134.45.8:8000/health", timeout=6)
        after.append({"try": i + 1, "http": code})
        time.sleep(0.3)
    return {
        "applied": applied,
        "during": during,
        "restored": restored,
        "after": after,
        "during_200": sum(1 for r in during if r.get("http") == 200),
        "after_200": sum(1 for r in after if r.get("http") == 200),
    }


def write_result(letter: str, status: str, note: str) -> None:
    path = ROOT / "validation" / letter / "RESULT.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "at": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
                "id": letter,
                "sim": "e2e208_dv02_dv06_live",
                "status": status,
                "note": note,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    print("install.sh not executed")
    print("init_genesis.py not executed")
    print("blocks.jsonl not emptied")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    floods = {}
    locks = {}
    health = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        ip = NODES[nid].ssh_host or ""
        code, body = _http(f"http://{ip}:8000/health")
        health[nid] = {
            "http": code,
            "git_sha": body.get("git_sha"),
            "certified": body.get("certified_distributed_mainnet"),
        }
        floods[nid] = flood(ip)
        locks[nid] = unauth_locks(ip)
    netem = netem_ovh4()
    flood_ok = all(row.get("http_200") == 64 for row in floods.values())
    unauth_ok = all(row.get("delete") == 401 and row.get("sync") == 401 and row.get("gossip") == 401 for row in locks.values())
    ssrf_ok = all(row.get("ssrf") == 400 for row in locks.values())
    netem_ran = netem.get("applied", {}).get("rc") == 0
    netem_restored = netem.get("after_200", 0) >= 6
    dv02 = "PASS" if flood_ok and unauth_ok and ssrf_ok else "PARTIAL"
    dv06 = "PASS" if netem_ran and netem_restored else "PARTIAL"
    write_result("DV-02", dv02, "bounded HTTP flood 64×4 + unauth 401 + SSRF 400; not SYN")
    write_result("DV-06", dv06, "tc netem 25%/80ms on OVH4 then restore; not chaos C")
    verdicts = load_dv_verdicts()
    gate = certification_gate(verdicts)
    out = {
        "stamp": stamp,
        "health": health,
        "floods": floods,
        "locks": locks,
        "netem": {
            "applied_rc": netem.get("applied", {}).get("rc"),
            "during_200": netem.get("during_200"),
            "after_200": netem.get("after_200"),
            "restored_rc": netem.get("restored", {}).get("rc"),
        },
        "verdicts": {"DV-02": dv02, "DV-06": dv06, **{k: v for k, v in verdicts.items() if k not in {"DV-02", "DV-06"}}},
        "gate": gate,
        "forbidden": [
            "install.sh not executed",
            "blocks.jsonl not emptied",
            "OPERATOR_MAINNET_CERTIFICATION_GO not flipped by this script",
        ],
    }
    dest = ROOT / "logs" / f"208_dv02_dv06_{stamp}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(dest), "DV-02": dv02, "DV-06": dv06, "certified": gate["certified_distributed_mainnet"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
