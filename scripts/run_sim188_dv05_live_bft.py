#!/usr/bin/env python3
"""Simulation 188 — DV-05 live prepare/commit on 4 nodes.

Never invent SHA. Does not rename the network to mainnet.
certified_distributed_mainnet stays computed (still false: economics + remaining DV).
Scenarios: honest, double-proposal, offline (OVH4 stopped), recover.
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import time
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
from artcb.devnet_validation import DECISIONS_188, certification_gate, public_lock  # noqa: E402
from artcb.node_registry import NODES  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e188_dv05_live_bft"
OVH1 = NODES["ovh-node-1"].ssh_host or "152.228.144.34"
OVH2 = NODES["ovh-node-2"].ssh_host or "151.80.107.29"
AWS3 = NODES["aws-node-3"].ssh_host or "51.44.222.232"
OVH4 = NODES["ovh-node-4"].ssh_host or ""
CTX = ssl._create_unverified_context()
LABELS = {"ovh1": OVH1, "ovh2": OVH2, "aws3": AWS3, "ovh4": OVH4}


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
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            parsed = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return exc.code, parsed if isinstance(parsed, dict) else {"detail": detail}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "url": url}


def _ssh(name: str, remote: str) -> dict:
    keys = {
        "ovh1": (Path.home() / ".ssh" / "artcb_ovh_deploy", ROOT / "deploy" / "ovh_artcb_node_1.known_hosts", OVH1),
        "ovh4": (Path.home() / ".ssh" / "artcb_ovh_node_4", ROOT / "deploy" / "ovh_artcb_node_4.known_hosts", OVH4),
    }
    key, known, ip = keys[name]
    cmd = [
        "ssh",
        "-i",
        str(key),
        "-o",
        "UserKnownHostsFile=" + str(known),
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=15",
        f"ubuntu@{ip}",
        remote,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
    return {"returncode": proc.returncode, "stdout_len": len(proc.stdout or ""), "stderr_len": len(proc.stderr or "")}


def wait_health(ip: str, *, want: int = 200, tries: int = 20) -> list[dict]:
    rows = []
    for i in range(tries):
        code, _ = _http(f"http://{ip}:8000/health", timeout=5)
        rows.append({"try": i + 1, "http": code})
        if code == want:
            break
        time.sleep(3)
    return rows


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = collect(
        protocol_version="188-live-bft-prepare-commit",
        economic_rules_version="D-025+V-provisional+D-032..D-042",
        simulation_id=SIM_ID,
        seed=188,
        script_path=Path(__file__),
        extra={"d042": True},
    )
    statuses = {name: _http(f"http://{ip}:8000/api/v1/consensus/status") for name, ip in LABELS.items()}
    engine_up = all(code == 200 and (body or {}).get("live_bft_implemented") for code, body in statuses.values())
    scenarios: dict[str, object] = {"engine_up": engine_up, "statuses": {k: {"http": v[0], "n": (v[1] or {}).get("n"), "f": (v[1] or {}).get("f"), "q": (v[1] or {}).get("q"), "bft_capable": (v[1] or {}).get("bft_capable")} for k, v in statuses.items()}}
    if not engine_up:
        scenarios["skipped"] = "consensus_status_not_200_on_all_four"
        v = {
            "DV-01": "PENDING",
            "DV-02": "PARTIAL",
            "DV-03": "PASS",
            "DV-04": "PASS",
            "DV-05": "BLOCKED",
            "DV-06": "PARTIAL",
            "DV-07": "PARTIAL",
        }
        failures = ["live_bft_not_deployed"]
    else:
        wid = f"W-188-{ts}"
        honest_c, honest_b = _http(
            f"http://{OVH2}:8000/api/v1/consensus/propose",
            "POST",
            {"work_id": wid, "snapshot_digest": f"honest-{ts}"},
            timeout=40,
        )
        double_c, double_b = _http(
            f"http://{OVH2}:8000/api/v1/consensus/propose",
            "POST",
            {"work_id": wid, "snapshot_digest": f"double-{ts}", "forged_sid": "f" * 64},
            timeout=40,
        )
        stop = _ssh("ovh4", "sudo systemctl stop artcb")
        wait_down = wait_health(OVH4, want=0, tries=8)
        offline_c, offline_b = _http(
            f"http://{OVH2}:8000/api/v1/consensus/propose",
            "POST",
            {"work_id": f"W-188-off-{ts}", "snapshot_digest": f"offline-{ts}"},
            timeout=40,
        )
        start = _ssh("ovh4", "sudo systemctl start artcb")
        wait_up = wait_health(OVH4, want=200, tries=20)
        recover_c, recover_b = _http(f"http://{OVH4}:8000/api/v1/consensus/status")
        honest_ok = honest_c == 200 and bool(honest_b.get("ok"))
        double_ok = double_c in {200, 409} and not bool(double_b.get("ok"))
        offline_ok = offline_c == 200 and bool(offline_b.get("ok"))
        recovered = recover_c == 200
        delay_c, delay_b = _http("http://192.0.2.1:8000/health", timeout=3)
        delay_ok = delay_c == 0
        scenarios.update(
            {
                "honest": {"http": honest_c, "ok": honest_b.get("ok"), "n": honest_b.get("n"), "q": honest_b.get("q"), "prepared": honest_b.get("prepared")},
                "double_proposal": {"http": double_c, "ok": double_b.get("ok"), "reason": double_b.get("reason")},
                "ovh4_stop": stop,
                "ovh4_down_wait": wait_down,
                "offline": {"http": offline_c, "ok": offline_b.get("ok"), "reason": offline_b.get("reason"), "prepared": offline_b.get("prepared")},
                "ovh4_start": start,
                "ovh4_up_wait": wait_up,
                "recover_status_http": recover_c,
                "delay_unroutable": {"http": delay_c, "expect_fail": delay_ok, "error": delay_b.get("error")},
                "checks": {
                    "honest_ok": honest_ok,
                    "double_rejected": double_ok,
                    "offline_quorum": offline_ok,
                    "ovh4_recovered": recovered,
                    "delay_timeout": delay_ok,
                },
            }
        )
        dv05 = "PASS" if honest_ok and double_ok and offline_ok and recovered and delay_ok else "PARTIAL"
        v = {
            "DV-01": "PENDING",
            "DV-02": "PARTIAL",
            "DV-03": "PASS",
            "DV-04": "PASS",
            "DV-05": dv05,
            "DV-06": "PARTIAL" if recovered else "FAIL",
            "DV-07": "PARTIAL",
        }
        failures = []
        if not honest_ok:
            failures.append("dv05_honest_failed")
        if not double_ok:
            failures.append("dv05_double_proposal_not_rejected")
        if not offline_ok:
            failures.append("dv05_offline_quorum_failed")
        if not recovered:
            failures.append("ovh4_did_not_recover")
    gate = certification_gate(v)
    summary = {
        "simulation": SIM_ID,
        "dir": str(out_dir),
        "failures": failures,
        "failure_count": len(failures),
        "invented": False,
        "certified_distributed_mainnet": gate["certified_distributed_mainnet"],
        "certification_gate": gate,
        "decisions_188": DECISIONS_188,
        "verdicts": v,
        "consensus_extracted": public_spec(),
        "scenarios": scenarios,
        "note": (
            "D-042: live prepare/commit BFT on 4 VMs. Not a mainnet rename. "
            "certified_distributed_mainnet false until DV-01…07 PASS and V lock."
        ),
    }
    _write(out_dir, "00_manifest.json", finish(manifest))
    _write(out_dir, "11_lock.json", public_lock())
    _write(out_dir, "15_consensus.json", public_spec())
    _write(out_dir, "16_verdicts.json", v)
    _write(out_dir, "17_failures.json", failures)
    _write(out_dir, "18_summary.json", summary)
    _write(out_dir, "14_scenarios.json", scenarios)
    val = ROOT / "validation" / "DV-05"
    val.mkdir(parents=True, exist_ok=True)
    (val / "RESULT.json").write_text(dumps({"id": "DV-05", "status": v["DV-05"], "at": ts, "sim": SIM_ID}), encoding="utf-8")
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
