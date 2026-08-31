#!/usr/bin/env python3
"""Simulation 175 — OVH4 join + PRE-DV-04 on 3 protocol-compatible nodes.

Does not redeploy OVH1. Homogeneous 174 set = OVH2 + AWS3 + OVH4.
DV-04 FINAL stays BLOCKED (OVH1 legacy, only 3 protocol-compatible nodes).
Never invent SHA / balances / Settlement.
"""

from __future__ import annotations

import json
import ssl
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.consensus_spec import public_spec  # noqa: E402
from artcb.crypto_policy import GENESIS_HASH, NETWORK_ID, PROTOCOL_VERSION, accept_peer_protocol  # noqa: E402
from artcb.devnet_validation import DECISIONS_174, DECISIONS_175, public_lock  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e175_ovh4_node"
OVH1 = NODES["ovh-node-1"].ssh_host or "152.228.144.34"
OVH2 = NODES["ovh-node-2"].ssh_host or "151.80.107.29"
AWS3 = NODES["aws-node-3"].ssh_host or "51.44.222.232"
OVH4 = NODES["ovh-node-4"].ssh_host or ""
CTX = ssl._create_unverified_context()


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _http(url: str, method: str = "GET", body: dict | None = None, timeout: int = 20) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout, context=CTX if url.startswith("https://") else None) as resp:
            raw = resp.read().decode()
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed if isinstance(parsed, dict) else {"raw": parsed}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        try:
            parsed = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return exc.code, parsed if isinstance(parsed, dict) else {"detail": detail}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "url": url}


def probe(name: str, ip: str) -> dict:
    http_c, health = _http(f"http://{ip}:8000/health")
    https_c, _ = _http(f"https://{ip}:8443/health")
    _, chain = _http(f"http://{ip}:8000/api/v1/chain/status")
    _, verify = _http(f"http://{ip}:8000/api/v1/chain/verify")
    _, p2p = _http(f"http://{ip}:8000/api/v1/p2p/status")
    proto_ok, proto_reason = accept_peer_protocol(
        advertised_network_id=health.get("network_id") or p2p.get("network_id"),
        advertised_protocol_version=health.get("protocol_version") or p2p.get("protocol_version"),
        advertised_genesis_hash=health.get("genesis_hash") or p2p.get("genesis_hash"),
    )
    pqc = health.get("pqc") if isinstance(health.get("pqc"), dict) else {}
    policy = pqc.get("policy") if isinstance(pqc.get("policy"), dict) else {}
    return {
        "classification": "PROBE LIVE",
        "name": name,
        "ip": ip,
        "http": http_c,
        "https": https_c,
        "git_sha": health.get("git_sha"),
        "git_branch": health.get("git_branch"),
        "network_id": health.get("network_id") or p2p.get("network_id"),
        "protocol_version": health.get("protocol_version") or p2p.get("protocol_version"),
        "genesis_hash": health.get("genesis_hash") or p2p.get("genesis_hash"),
        "pqc": pqc.get("algorithm"),
        "pqc_available": pqc.get("available"),
        "hybrid_verify_mode": policy.get("hybrid_verify_mode"),
        "height": chain.get("height"),
        "last_hash": chain.get("last_hash"),
        "chain_valid": chain.get("chain_valid") or verify.get("valid"),
        "hybrid_signatures": verify.get("hybrid_signatures"),
        "public_state_digest": p2p.get("public_state_digest"),
        "capability_signed": bool((p2p.get("capability_card") or {}).get("signed")),
        "peer_count": p2p.get("peer_count"),
        "protocol_compatible_with_174": proto_ok,
        "protocol_reason": proto_reason,
        "reachable": http_c == 200 or https_c == 200,
        "bootstrap_mode": health.get("bootstrap_mode"),
    }


def register_pair(target_ip: str, source_ip: str, label: str) -> dict:
    code, body = _http(
        f"http://{target_ip}:8000/api/v1/p2p/register-public",
        "POST",
        {
            "node_public_url": f"http://{source_ip}:8000",
            "device_fingerprint": f"e2e175-{label}",
            "node_label": label,
            "network_id": NETWORK_ID,
        },
        timeout=30,
    )
    return {"http": code, "status": (body or {}).get("status"), "peer_id": (body or {}).get("peer_id")}


def dv02_hostile(ip: str) -> dict:
    out: dict[str, object] = {}
    code, _body = _http(
        f"http://{ip}:8000/api/v1/p2p/peers",
        "POST",
        {"host": "192.0.2.1", "port": 8000, "kem_public_key_hex": "00"},
    )
    out["invalid_kem"] = {"http": code, "expect_4xx": code in {400, 422}}
    code_t, body_t = _http("http://192.0.2.1:8000/health", timeout=3)
    out["dead_peer_timeout"] = {"http": code_t, "error": body_t.get("error"), "expect_fail": code_t == 0}
    _, peers = _http(f"http://{ip}:8000/api/v1/p2p/peers")
    listed = peers.get("peers") or []
    if listed:
        pid = listed[0].get("peer_id")
        host = listed[0].get("host")
        port = listed[0].get("port") or 8000
        kem = listed[0].get("kem_public_key_hex") or ("ab" * 32)
        del_c, _ = _http(f"http://{ip}:8000/api/v1/p2p/peers/{pid}", "DELETE")
        add_c, _add_b = _http(
            f"http://{ip}:8000/api/v1/p2p/peers",
            "POST",
            {"host": host, "port": port, "kem_public_key_hex": kem, "label": "dv02_reconnect", "peer_id": pid},
        )
        out["reconnect"] = {"deleted": del_c, "readded": add_c, "ok": del_c == 200 and add_c in {200, 400}}
    else:
        out["reconnect"] = {"skipped": True}
    return out


def predv04_triple(ovh2: str, aws3: str, ovh4: str) -> dict:
    """Public TX on OVH2, sync AWS3+OVH4. Never extends OVH1."""
    mesh = (
        ("ovh2_aws3", ovh2, aws3),
        ("ovh2_ovh4", ovh2, ovh4),
        ("aws3_ovh2", aws3, ovh2),
        ("aws3_ovh4", aws3, ovh4),
        ("ovh4_ovh2", ovh4, ovh2),
        ("ovh4_aws3", ovh4, aws3),
    )
    registrations = {}
    for name, target, source in mesh:
        registrations[name] = register_pair(target, source, name)
    before = {
        "ovh2": _http(f"http://{ovh2}:8000/api/v1/chain/status")[1],
        "aws3": _http(f"http://{aws3}:8000/api/v1/chain/status")[1],
        "ovh4": _http(f"http://{ovh4}:8000/api/v1/chain/status")[1],
        "ovh1": _http(f"http://{OVH1}:8000/api/v1/chain/status")[1],
    }
    store_c, store_b = _http(
        f"http://{ovh2}:8000/api/v1/store",
        "POST",
        {"text": "PRE-DV-04 TX-002 public replication probe 175 ovh4", "visibility": "public"},
        timeout=60,
    )
    syncs = {
        "aws3": _http(f"http://{aws3}:8000/api/v1/p2p/sync", "POST", timeout=60),
        "ovh4": _http(f"http://{ovh4}:8000/api/v1/p2p/sync", "POST", timeout=60),
    }
    after = {
        "ovh2": _http(f"http://{ovh2}:8000/api/v1/chain/status")[1],
        "aws3": _http(f"http://{aws3}:8000/api/v1/chain/status")[1],
        "ovh4": _http(f"http://{ovh4}:8000/api/v1/chain/status")[1],
        "ovh1": _http(f"http://{OVH1}:8000/api/v1/chain/status")[1],
    }
    digests = {
        "ovh2": _http(f"http://{ovh2}:8000/api/v1/p2p/status")[1].get("public_state_digest"),
        "aws3": _http(f"http://{aws3}:8000/api/v1/p2p/status")[1].get("public_state_digest"),
        "ovh4": _http(f"http://{ovh4}:8000/api/v1/p2p/status")[1].get("public_state_digest"),
    }
    h2, h3, h4 = after["ovh2"].get("last_hash"), after["aws3"].get("last_hash"), after["ovh4"].get("last_hash")
    tips_equal = bool(h2 and h3 and h4 and h2 == h3 == h4 and not str(h2).startswith("0" * 16))
    ovh1_unchanged = before["ovh1"].get("last_hash") == after["ovh1"].get("last_hash")
    return {
        "registrations": registrations,
        "store_http": store_c,
        "store_block_index": store_b.get("block_index") if isinstance(store_b, dict) else None,
        "sync_http": {k: v[0] for k, v in syncs.items()},
        "before_hashes": {k: v.get("last_hash") for k, v in before.items()},
        "after_hashes": {k: v.get("last_hash") for k, v in after.items()},
        "heights": {k: v.get("height") for k, v in after.items()},
        "digests": digests,
        "tips_equal_homogeneous": tips_equal,
        "ovh1_untouched": ovh1_unchanged,
    }


def verdicts(nodes: dict[str, dict], dv02: dict, pre: dict) -> dict[str, str]:
    compatible = [n for n in nodes.values() if n.get("protocol_compatible_with_174")]
    reachable = [n for n in nodes.values() if n.get("reachable")]
    dv03_homogeneous = all(
        nodes[k].get("protocol_compatible_with_174") for k in ("ovh2", "aws3", "ovh4")
    )
    ovh1_legacy = not nodes["ovh1"].get("protocol_compatible_with_174")
    pqc_ok = all(nodes[k].get("pqc_available") for k in ("ovh2", "aws3", "ovh4"))
    return {
        "DV-01": "PENDING",
        "DV-02": "PARTIAL" if len(reachable) == 4 else "FAIL",
        "DV-03": "PARTIAL" if dv03_homogeneous and ovh1_legacy else ("FAIL" if not dv03_homogeneous else "PASS"),
        "DV-04": "BLOCKED",
        "PRE-DV-04": "PASS" if pre.get("tips_equal_homogeneous") and pre.get("ovh1_untouched") else "FAIL",
        "DV-05": "BLOCKED",
        "DV-06": "PARTIAL" if (dv02.get("ovh4") or {}).get("dead_peer_timeout", {}).get("expect_fail") else "NOT_RUN",
        "DV-07": "PARTIAL" if pqc_ok else "FAIL",
        "compatible_node_count": str(len(compatible)),
    }


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    val_dir = ROOT / "validation"
    if not OVH4 or OVH4 in {"152.228.144.34", "151.80.107.29"}:
        print(dumps({"ok": False, "error": "ovh4_ip_missing_or_forbidden"}))
        return 2
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="D-025+V-provisional+D-032..D-037",
        simulation_id=SIM_ID,
        seed=175,
        script_path=Path(__file__),
        extra={"ovh1_redeployed": False, "node4": True, "ovh4_ip": OVH4},
    )
    nodes = {
        "ovh1": probe("ovh-node-1", OVH1),
        "ovh2": probe("ovh-node-2", OVH2),
        "aws3": probe("aws-node-3", AWS3),
        "ovh4": probe("ovh-node-4", OVH4),
    }
    dv02 = {
        "ovh4": dv02_hostile(OVH4),
        "ovh2": dv02_hostile(OVH2),
        "ovh1_skipped_mutating": True,
    }
    pre = predv04_triple(OVH2, AWS3, OVH4)
    v = verdicts(nodes, dv02, pre)
    failures = []
    for key in ("ovh1", "ovh2", "aws3", "ovh4"):
        if not nodes[key].get("reachable"):
            failures.append(f"{key}_down")
    if nodes["ovh1"].get("protocol_compatible_with_174"):
        failures.append("ovh1_unexpectedly_174_fields")
    if nodes["ovh4"].get("bootstrap_mode") is True:
        failures.append("ovh4_still_bootstrap")
    if not nodes["ovh4"].get("protocol_compatible_with_174"):
        failures.append("ovh4_protocol_incompatible")
    summary = {
        "simulation": SIM_ID,
        "dir": str(out_dir),
        "failures": failures,
        "failure_count": len(failures),
        "invented": False,
        "certified_distributed_mainnet": False,
        "decisions_174": DECISIONS_174,
        "decisions_175": DECISIONS_175,
        "verdicts": v,
        "consensus_extracted": public_spec(),
        "nodes": nodes,
        "note": (
            "Four live machines exist, but OVH1 remains legacy (D-036). "
            "Homogeneous 174 set is OVH2+AWS3+OVH4 (3). DV-04 FINAL C stays BLOCKED."
        ),
    }
    _write(out_dir, "00_manifest.json", finish(manifest))
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_lock.json", public_lock())
    _write(out_dir, "12_nodes.json", nodes)
    _write(out_dir, "13_dv02.json", dv02)
    _write(out_dir, "14_predv04.json", pre)
    _write(out_dir, "15_consensus.json", public_spec())
    _write(out_dir, "16_verdicts.json", v)
    _write(out_dir, "17_failures.json", failures)
    _write(out_dir, "18_summary.json", summary)
    for dv, status in v.items():
        if not dv.startswith("DV") and dv != "PRE-DV-04":
            continue
        dest = val_dir / dv / "RESULT.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(dumps({"id": dv, "status": status, "at": ts, "sim": SIM_ID}), encoding="utf-8")
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
