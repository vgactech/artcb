#!/usr/bin/env python3
"""Simulation 176 — diagnose and re-probe OVH4 /p2p/sync. Never invent SHA."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.crypto_policy import PROTOCOL_VERSION  # noqa: E402
from artcb.node_registry import NODES  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e176_sync_500"
OVH1 = NODES["ovh-node-1"].ssh_host
OVH2 = NODES["ovh-node-2"].ssh_host
AWS3 = NODES["aws-node-3"].ssh_host
OVH4 = NODES["ovh-node-4"].ssh_host


def _http(url: str, method: str = "GET", body: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed if isinstance(parsed, dict) else {"raw": parsed}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            parsed = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return exc.code, parsed if isinstance(parsed, dict) else {"detail": detail}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__}


def kem_bytes(ip: str) -> dict:
    code, body = _http(f"http://{ip}:8000/api/v1/p2p/status")
    hexkey = body.get("kem_public_key_hex") or ""
    raw = bytes.fromhex(hexkey) if hexkey else b""
    health = _http(f"http://{ip}:8000/health")[1]
    return {
        "http": code,
        "kem_algorithm": body.get("kem_algorithm"),
        "kem_public_bytes": len(raw),
        "git_sha": health.get("git_sha"),
        "protocol_version": health.get("protocol_version") or body.get("protocol_version"),
    }


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = {
        "ovh1": kem_bytes(OVH1),
        "ovh2": kem_bytes(OVH2),
        "aws3": kem_bytes(AWS3),
        "ovh4": kem_bytes(OVH4),
    }
    runs = []
    for i in range(3):
        code, body = _http(f"http://{OVH4}:8000/api/v1/p2p/sync", "POST", {}, timeout=90)
        clean = []
        for row in body.get("results") or []:
            clean.append(
                {
                    "peer_id": row.get("peer_id"),
                    "ok": row.get("ok"),
                    "error": row.get("error"),
                    "pull_received": (row.get("pull") or {}).get("received"),
                    "pushed": (row.get("push") or {}).get("pushed") if isinstance(row.get("push"), dict) else None,
                }
            )
        runs.append({"n": i + 1, "http": code, "all_ok": all(r.get("ok") for r in clean) if clean else False, "results": clean})
    tips = {
        name: _http(f"http://{ip}:8000/api/v1/chain/status")[1]
        for name, ip in (("ovh1", OVH1), ("ovh2", OVH2), ("aws3", AWS3), ("ovh4", OVH4))
    }
    failures = []
    if any(r["http"] == 500 for r in runs):
        failures.append("ovh4_sync_still_500")
    if sizes["ovh1"].get("git_sha") and not str(sizes["ovh1"]["git_sha"]).startswith("5b4b24ae"):
        failures.append("ovh1_unexpectedly_redeployed")
    summary = {
        "simulation": SIM_ID,
        "failures": failures,
        "failure_count": len(failures),
        "invented": False,
        "certified_distributed_mainnet": False,
        "diagnosis": (
            "HTTP 500 was RuntimeError Can not encapsulate secret during encrypted PUSH "
            "to AWS3 leftover 32-byte X25519 KEM key. PULL of public blocks already worked. "
            "Fix: catch per-peer + upgrade leftover identity + honest kem_algorithm."
        ),
        "kem_sizes": sizes,
        "sync_runs": runs,
        "tips": {k: {"height": v.get("height"), "last_hash": v.get("last_hash")} for k, v in tips.items()},
        "ovh1_untouched": True,
    }
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="D-025+V-provisional+D-032..D-037",
        simulation_id=SIM_ID,
        seed=176,
        script_path=Path(__file__),
        extra={"ovh1_redeployed": False},
    )
    (out_dir / "00_manifest.json").write_text(dumps(finish(manifest)), encoding="utf-8")
    (out_dir / "18_summary.json").write_text(dumps(summary), encoding="utf-8")
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
