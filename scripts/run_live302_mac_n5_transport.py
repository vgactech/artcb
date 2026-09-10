#!/usr/bin/env python3
"""R302 live — membership N=5 vs seed HTTP ×4 vs Mac transport.

Does not claim Mac is a live PBFT replica. Does not claim CERTIFIED_100.
Never prints Doppler values. Never adds Mac to OFFICIAL_COMPUTE_NODE_IDS.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from artcb.mac_node_access import is_lan_only_host, select_cloud_remote  # noqa: E402
from artcb.node_registry import (  # noqa: E402
    MAC_NODE_ID,
    OFFICIAL_COMPUTE_IPV4,
    OFFICIAL_COMPUTE_NODE_IDS,
    NODES,
    mac_has_registered_replica_key,
    official_pbft_n_f_q,
    official_pbft_replica_ids,
    pbft_membership_vs_transport,
    pbft_reachable_http_map,
)
from artcb.p2p.official_replica import replica_peer_allowed  # noqa: E402
from artcb.trace.ns import emit, now_mono_ns, now_wall_ns  # noqa: E402

SEED_HTTP = {
    nid: f"http://{ip}:8000" for nid, ip in zip(OFFICIAL_COMPUTE_NODE_IDS, OFFICIAL_COMPUTE_IPV4)
}
MAC_LOCAL = "http://127.0.0.1:8001"


def _http(url: str, timeout: float = 8.0) -> tuple[int, dict, int]:
    t0 = now_mono_ns()
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
            return int(resp.status), parsed if isinstance(parsed, dict) else {"raw": parsed}, now_mono_ns() - t0
    except HTTPError as exc:
        return int(exc.code), {"error": "HTTPError"}, now_mono_ns() - t0
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}, now_mono_ns() - t0


def _health_view(body: dict) -> dict:
    return {
        "git_sha": body.get("git_sha"),
        "height": body.get("height") or body.get("chain_height"),
        "last_hash": body.get("last_hash") or body.get("tip_hash"),
        "view": body.get("view") or (body.get("pbft") or {}).get("view"),
        "primary": body.get("primary") or (body.get("pbft") or {}).get("primary"),
        "chain_valid": body.get("chain_valid"),
        "node_id": body.get("node_id") or body.get("artcb_node_id"),
    }


def _doppler_name_present() -> dict:
    """Name-only. Never --plain. Never store secret values."""
    env = os.environ.copy()
    # Shared Cursor DOPPLER_TOKEN is artcb-blockchain; it cannot read artcb-1/prd.
    env.pop("DOPPLER_TOKEN", None)
    out: dict = {"plain_invoked": False, "name_present": False}
    json_cmd = [
        "doppler",
        "secrets",
        "--only-names",
        "--json",
        "--project",
        "artcb-1",
        "--config",
        "prd",
    ]
    vis_cmd = [
        "doppler",
        "secrets",
        "--only-names",
        "--visibility",
        "--project",
        "artcb-1",
        "--config",
        "prd",
    ]
    try:
        proc = subprocess.run(json_cmd, capture_output=True, text=True, timeout=40, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        out.update({"ok": False, "rc": None, "error": type(exc).__name__})
        return out
    names: list[str] = []
    parsed = False
    try:
        blob = json.loads(proc.stdout or "{}")
        parsed = True
        if isinstance(blob, dict):
            names = [str(k) for k in blob.keys()]
        elif isinstance(blob, list):
            names = [str(x) for x in blob]
    except json.JSONDecodeError:
        names = []
    present = "MAC_SUDO_PASSWORD" in names
    err = (proc.stderr or "").strip().splitlines()
    err0 = err[0][:160] if err else ""
    if "dp.st" in err0.lower() or "password" in err0.lower():
        err0 = "redacted"
    out.update(
        {
            "ok": proc.returncode == 0,
            "rc": proc.returncode,
            "parsed_json": parsed,
            "name_count": len(names),
            "json_stderr_head": err0,
        }
    )
    if not present:
        try:
            vis = subprocess.run(vis_cmd, capture_output=True, text=True, timeout=40, env=env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            out["visibility_error"] = type(exc).__name__
            out["name_present"] = False
            return out
        present = "MAC_SUDO_PASSWORD" in (vis.stdout or "")
        out["visibility_rc"] = vis.returncode
        out["ok"] = out["ok"] or vis.returncode == 0
    out["name_present"] = present
    return out


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    t0 = now_wall_ns()
    origin = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "origin/main"], text=True).strip()
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    split = pbft_membership_vs_transport()
    ids = official_pbft_replica_ids()
    n, f, q = official_pbft_n_f_q()
    seeds: dict = {}
    for nid, url in SEED_HTTP.items():
        code, body, dur = _http(f"{url}/health")
        t_code, t_body, t_dur = _http(f"{url}/api/v1/consensus/tip-attest")
        row = {"http": code, "dur_ns": dur, **_health_view(body if isinstance(body, dict) else {})}
        if t_code == 200 and isinstance(t_body, dict):
            row["height"] = t_body.get("height")
            row["last_hash"] = t_body.get("last_hash")
            row["tip_node_id"] = t_body.get("node_id")
            row["tip_attest_http"] = t_code
            row["tip_attest_dur_ns"] = t_dur
        if code != 200:
            row["error"] = body.get("error") if isinstance(body, dict) else type(body).__name__
        seeds[nid] = row
        emit(
            ROOT / "data",
            {"kind": "http_health", "node_id": nid, "ok": code == 200, "dur_ns": dur, "http": code},
        )
    mac_code, mac_body, mac_dur = _http(f"{MAC_LOCAL}/health")
    mac_t_code, mac_t_body, mac_t_dur = _http(f"{MAC_LOCAL}/api/v1/consensus/tip-attest")
    mac_lan = (NODES[MAC_NODE_ID].health_http or "").strip()
    lan_code, lan_body, lan_dur = (0, {"error": "empty"}, 0)
    if mac_lan:
        lan_code, lan_body, lan_dur = _http(f"{mac_lan.rstrip('/')}/health", timeout=4.0)
    # VM → Mac RFC1918: this host is the Mac; from here LAN may work. Record replica_peer_allowed.
    inbound = {}
    for ip in OFFICIAL_COMPUTE_IPV4:
        inbound[ip] = {
            "replica_peer_allowed_to_mac_lan": replica_peer_allowed("10.234.49.2"),
            "note": "seed source IPs are public; Mac RFC1918 is never an official replica peer",
        }
    mac_to_seeds = {}
    for nid, url in SEED_HTTP.items():
        code, body, dur = _http(f"{url}/api/v1/consensus/status", timeout=8.0)
        code2, body2, dur2 = _http(f"{url}/api/v1/consensus/tip-attest", timeout=8.0)
        mac_to_seeds[nid] = {
            "status_http": code,
            "status_dur_ns": dur,
            "tip_attest_http": code2,
            "tip_attest_dur_ns": dur2,
            "ok": code == 200 or code2 == 200,
            "not_pbft_prepare_commit": True,
        }
    remote = select_cloud_remote()
    payload = {
        "stamp": stamp,
        "protocol": "302-mac-n5-transport",
        "ts_ns": t0,
        "origin_main": origin,
        "head": head,
        "n_f_q": [n, f, q],
        "official_pbft_replica_ids": list(ids),
        "official_compute_seeds": list(OFFICIAL_COMPUTE_NODE_IDS),
        "membership_vs_transport": split,
        "reachable_http_ids": list(pbft_reachable_http_map().keys()),
        "seeds_health": seeds,
        "mac_local_health": {
            "http": mac_code,
            "dur_ns": mac_dur,
            **_health_view(mac_body if isinstance(mac_body, dict) else {}),
            "tip_attest_http": mac_t_code,
            "tip_attest_dur_ns": mac_t_dur,
            "height": mac_t_body.get("height") if isinstance(mac_t_body, dict) else None,
            "last_hash": mac_t_body.get("last_hash") if isinstance(mac_t_body, dict) else None,
            "tip_node_id": mac_t_body.get("node_id") if isinstance(mac_t_body, dict) else None,
        },
        "mac_lan_health": {"url_is_lan": is_lan_only_host(mac_lan), "http": lan_code, "dur_ns": lan_dur},
        "mac_to_seed_pbft": mac_to_seeds,
        "replica_peer_rfc1918": replica_peer_allowed("10.234.49.2"),
        "inbound_from_seeds_note": inbound,
        "tunnel": {
            "select_cloud_remote_ok": bool(remote.get("ok")),
            "reason": remote.get("reason"),
            "health_http": remote.get("health_http"),
            "tunnel_required": remote.get("tunnel_required"),
        },
        "mac_key_registered": mac_has_registered_replica_key(),
        "doppler_mac_sudo_name_only": _doppler_name_present(),
        "includes_thinking": False,
        "certified_100": False,
        "mac_live_pbft_replica": False,
        "verdict": "TRANSPORT_GAP",
    }
    sha_ok = all((row.get("http") == 200 and row.get("git_sha") == origin) for row in seeds.values())
    mac_sha = payload["mac_local_health"].get("git_sha")
    payload["sha_seeds_eq_origin"] = sha_ok
    payload["sha_mac_eq_origin"] = mac_sha == origin if mac_sha else False
    seed_heights = {nid: row.get("height") for nid, row in seeds.items()}
    seed_tips = {nid: row.get("last_hash") for nid, row in seeds.items()}
    payload["seed_heights"] = seed_heights
    payload["mac_tip_is_mac_node_local"] = payload["mac_local_health"].get("tip_node_id") == MAC_NODE_ID
    official_tip = next((h for h in seed_tips.values() if h), None)
    payload["mac_book_same_tip_as_seeds"] = bool(
        official_tip and payload["mac_local_health"].get("last_hash") == official_tip
    )
    if payload["tunnel"]["select_cloud_remote_ok"] and payload["mac_to_seed_pbft"] and all(v.get("ok") for v in mac_to_seeds.values()):
        payload["verdict"] = "PARTIAL_OUTBOUND"
    out_dir = ROOT / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"302_mac_n5_transport_{stamp}.json"
    latest = out_dir / "302_mac_n5_transport_latest.json"
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    print(json.dumps({"ok": True, "path": str(path), "verdict": payload["verdict"], "certified_100": False, "n_f_q": payload["n_f_q"], "sha_seeds_eq_origin": sha_ok}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
