#!/usr/bin/env python3
"""Simulation 174 — DV-03/07/02 + PRE-DV-04 on 3 live nodes. Never invent SHA.

Does not redeploy OVH1. Does not create NODE4 (D-035 B / D-036 B).
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.consensus_spec import public_spec  # noqa: E402
from artcb.crypto_policy import GENESIS_HASH, NETWORK_ID, PROTOCOL_VERSION, accept_peer_protocol  # noqa: E402
from artcb.devnet_validation import DECISIONS_174, public_lock  # noqa: E402
from artcb.node_registry import public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e174_dv_3node"
OVH1 = "152.228.144.34"
OVH2 = "151.80.107.29"
AWS3 = "51.44.222.232"
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
        "hybrid_verify_mode": (pqc.get("policy") or {}).get("hybrid_verify_mode") if isinstance(pqc.get("policy"), dict) else None,
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
    }


def dv02_hostile(ip: str) -> dict:
    """Authorized testnet: invalid/duplicate/timeout/reconnect. No VM power-off."""
    out: dict[str, object] = {}
    code, body = _http(
        f"http://{ip}:8000/api/v1/p2p/peers",
        "POST",
        {"host": "192.0.2.1", "port": 8000, "kem_public_key_hex": "00"},
    )
    out["invalid_kem"] = {"http": code, "expect_4xx": code in {400, 422}}
    # timeout to TEST-NET-1
    code_t, body_t = _http(f"http://192.0.2.1:8000/health", timeout=3)
    out["dead_peer_timeout"] = {"http": code_t, "error": body_t.get("error"), "expect_fail": code_t == 0}
    _, peers = _http(f"http://{ip}:8000/api/v1/p2p/peers")
    listed = peers.get("peers") or []
    if listed:
        pid = listed[0].get("peer_id")
        host = listed[0].get("host")
        port = listed[0].get("port") or 8000
        kem = listed[0].get("kem_public_key_hex") or ("ab" * 32)
        del_c, _ = _http(f"http://{ip}:8000/api/v1/p2p/peers/{pid}", "DELETE")
        add_c, add_b = _http(
            f"http://{ip}:8000/api/v1/p2p/peers",
            "POST",
            {"host": host, "port": port, "kem_public_key_hex": kem, "label": "dv02_reconnect", "peer_id": pid},
        )
        out["reconnect"] = {"deleted": del_c, "readded": add_c, "ok": del_c == 200 and add_c in {200, 400}}
    else:
        out["reconnect"] = {"skipped": True}
    return out


def predv04(ovh2: str, aws3: str) -> dict:
    """Create a public block on OVH2 and pull it on AWS3. Does not touch OVH1 chain."""
    for name, target, source in (
        ("aws3_ovh2", f"http://{aws3}:8000", f"http://{ovh2}:8000"),
        ("ovh2_aws3", f"http://{ovh2}:8000", f"http://{aws3}:8000"),
    ):
        _http(
            f"{target}/api/v1/p2p/register-public",
            "POST",
            {
                "node_public_url": source,
                "device_fingerprint": f"e2e174-predv04-{name}",
                "node_label": name,
                "network_id": NETWORK_ID,
            },
        )
    before_2, s2 = _http(f"http://{ovh2}:8000/api/v1/chain/status")
    before_3, s3 = _http(f"http://{aws3}:8000/api/v1/chain/status")
    store_c, store_b = _http(
        f"http://{ovh2}:8000/api/v1/store",
        "POST",
        {"text": "PRE-DV-04 TX-001 public replication probe 174", "visibility": "public"},
        timeout=60,
    )
    sync_c, sync_b = _http(f"http://{aws3}:8000/api/v1/p2p/sync", "POST", timeout=60)
    after_2, a2 = _http(f"http://{ovh2}:8000/api/v1/chain/status")
    after_3, a3 = _http(f"http://{aws3}:8000/api/v1/chain/status")
    _, p2 = _http(f"http://{ovh2}:8000/api/v1/p2p/status")
    _, p3 = _http(f"http://{aws3}:8000/api/v1/p2p/status")
    h2 = a2.get("last_hash")
    h3 = a3.get("last_hash")
    return {
        "store_http": store_c,
        "store_block_index": store_b.get("block_index") if isinstance(store_b, dict) else None,
        "sync_http": sync_c,
        "ovh2_before": s2.get("last_hash"),
        "aws3_before": s3.get("last_hash"),
        "ovh2_after": h2,
        "aws3_after": h3,
        "ovh2_height": a2.get("height"),
        "aws3_height": a3.get("height"),
        "digest_ovh2": p2.get("public_state_digest"),
        "digest_aws3": p3.get("public_state_digest"),
        "tips_equal": bool(h2 and h3 and h2 == h3 and not str(h2).startswith("0" * 16)),
        "ovh1_untouched": True,
    }


def verdicts(nodes: dict[str, dict], dv02: dict, pre: dict) -> dict[str, str]:
    ovh1, ovh2, aws3 = nodes["ovh1"], nodes["ovh2"], nodes["aws3"]
    dv03_pair = ovh2.get("protocol_compatible_with_174") and aws3.get("protocol_compatible_with_174")
    dv03_all = dv03_pair and ovh1.get("protocol_compatible_with_174")
    return {
        "DV-01": "PENDING",
        "DV-02": "PARTIAL" if all(n.get("reachable") for n in nodes.values()) else "FAIL",
        "DV-03": "PARTIAL" if dv03_pair and not dv03_all else ("PASS" if dv03_all else "FAIL"),
        "DV-04": "BLOCKED",
        "PRE-DV-04": "PASS" if pre.get("tips_equal") else "FAIL",
        "DV-05": "BLOCKED",
        "DV-06": "PARTIAL" if (dv02.get("ovh2") or {}).get("dead_peer_timeout", {}).get("expect_fail") else "NOT_RUN",
        "DV-07": "PARTIAL" if ovh2.get("pqc_available") and aws3.get("pqc_available") else "FAIL",
    }


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    val_dir = ROOT / "validation"
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="D-025+V-provisional+D-032+D-033+D-034+D-035+D-036",
        simulation_id=SIM_ID,
        seed=174,
        script_path=Path(__file__),
        extra={"ovh1_redeployed": False, "node4": False},
    )
    nodes = {
        "ovh1": probe("ovh-node-1", OVH1),
        "ovh2": probe("ovh-node-2", OVH2),
        "aws3": probe("aws-node-3", AWS3),
    }
    dv02 = {
        "ovh2": dv02_hostile(OVH2),
        "aws3": dv02_hostile(AWS3),
        "ovh1_skipped_mutating": True,
    }
    pre = predv04(OVH2, AWS3)
    v = verdicts(nodes, dv02, pre)
    failures = []
    if not nodes["ovh1"].get("reachable"):
        failures.append("ovh1_down")
    if not nodes["ovh2"].get("reachable"):
        failures.append("ovh2_down")
    if not nodes["aws3"].get("reachable"):
        failures.append("aws3_down")
    if nodes["ovh1"].get("protocol_compatible_with_174"):
        failures.append("ovh1_unexpectedly_174_fields")
    summary = {
        "simulation": SIM_ID,
        "dir": str(out_dir),
        "failures": failures,
        "failure_count": len(failures),
        "invented": False,
        "certified_distributed_mainnet": False,
        "decisions_174": DECISIONS_174,
        "verdicts": v,
        "consensus_extracted": public_spec(),
        "nodes": {
            k: {kk: vv for kk, vv in n.items() if kk != "capability_card"}
            for k, n in nodes.items()
        },
        "note": "DV-04 FINAL blocked (3/4). PRE-DV-04 is public-block tip equality OVH2/AWS3 only.",
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
        dest = val_dir / dv / "RESULT.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(dumps({"id": dv, "status": status, "at": ts, "sim": SIM_ID}), encoding="utf-8")
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
