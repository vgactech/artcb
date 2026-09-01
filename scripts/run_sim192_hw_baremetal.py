#!/usr/bin/env python3
"""Simulation 192 — hardware A–E + OVH3 bare-metal quote.

Never invent SHA, TPM, or a 10 EUR balance.
Does not run install.sh, init_genesis.py, or init-node.
Does not empty the live book. Does not deploy origin/main.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
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

from artcb.crypto_policy import NETWORK_ID, PROTOCOL_VERSION  # noqa: E402
from artcb.devnet_validation import DECISIONS_192, certification_gate, public_lock  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.security.hardware_identity import (  # noqa: E402
    classify_hardware_assurance,
    public_machine_view,
    tee_facts,
    tpm_sysfs_facts,
    virtualization_facts,
)
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e192_hw_baremetal"
BRANCH = "cursor/ovh3-baremetal-hw-16d8"
CTX = ssl._create_unverified_context()
LABELS = {
    "ovh1": NODES["ovh-node-1"].ssh_host or "152.228.144.34",
    "ovh2": NODES["ovh-node-2"].ssh_host or "151.80.107.29",
    "aws3": NODES["aws-node-3"].ssh_host or "51.44.222.232",
    "ovh4": NODES["ovh-node-4"].ssh_host or "91.134.45.8",
}
SSH = {
    "ovh1": (Path.home() / ".ssh" / "artcb_ovh_deploy", ROOT / "deploy" / "ovh_artcb_node_1.known_hosts", LABELS["ovh1"]),
    "ovh2": (Path.home() / ".ssh" / "artcb_ovh_node_2", ROOT / "deploy" / "ovh_artcb_node_2.known_hosts", LABELS["ovh2"]),
    "aws3": (Path.home() / ".ssh" / "artcb_aws_node_3", ROOT / "deploy" / "aws_artcb_node_3.known_hosts", LABELS["aws3"]),
    "ovh4": (Path.home() / ".ssh" / "artcb_ovh_node_4", ROOT / "deploy" / "ovh_artcb_node_4.known_hosts", LABELS["ovh4"]),
}


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _http(url: str, timeout: int = 15) -> tuple[int, dict]:
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout, context=CTX if url.startswith("https") else None) as resp:
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


def _ssh(name: str, remote: str, timeout: int = 30) -> dict:
    key, known, ip = SSH[name]
    if not key.is_file():
        return {"name": name, "returncode": -1, "error": "ssh_key_missing"}
    cmd = [
        "ssh", "-i", str(key),
        "-o", "UserKnownHostsFile=" + str(known),
        "-o", "StrictHostKeyChecking=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        f"ubuntu@{ip}",
        remote,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return {"name": name, "returncode": proc.returncode, "stdout": (proc.stdout or "")[-2000:], "stderr": (proc.stderr or "")[-400:]}


def slice_health(h: dict) -> dict:
    m = h.get("machine") or {}
    return {
        "git_sha": h.get("git_sha"),
        "git_branch": h.get("git_branch"),
        "network_id": h.get("network_id"),
        "protocol_version": h.get("protocol_version"),
        "bootstrap_mode": h.get("bootstrap_mode"),
        "certified_distributed_mainnet": h.get("certified_distributed_mainnet"),
        "tpm_device_present": m.get("tpm_device_present"),
        "hardware_assurance_level": m.get("hardware_assurance_level"),
        "hardware_kind": m.get("hardware_kind"),
        "chassis_virtual": m.get("chassis_virtual"),
        "tee_detected": m.get("tee_detected"),
        "cloud_provider": m.get("cloud_provider"),
        "device_fingerprint_prefix": m.get("device_fingerprint_prefix"),
    }


def probe_node(label: str, ip: str) -> dict:
    base = f"http://{ip}:8000"
    hc, health = _http(f"{base}/health")
    cc, chain = _http(f"{base}/api/v1/chain/status")
    dc, directory = _http(f"{base}/api/v1/network/nodes")
    pc, peers = _http(f"{base}/api/v1/p2p/peers")
    seeds = directory.get("seeds") if isinstance(directory, dict) else []
    announced = []
    if isinstance(directory, dict):
        for n in directory.get("announced") or []:
            if isinstance(n, dict):
                announced.append(n.get("url"))
            else:
                announced.append(str(n))
    peer_urls = []
    if isinstance(peers, dict):
        for p in peers.get("peers") or []:
            if isinstance(p, dict):
                peer_urls.append(p.get("base_url") or p.get("host"))
    return {
        "label": label,
        "ip": ip,
        "health_http": hc,
        "health": slice_health(health) if hc == 200 and isinstance(health, dict) else health,
        "chain_http": cc,
        "height": chain.get("height") if isinstance(chain, dict) else None,
        "last_hash": chain.get("last_hash") if isinstance(chain, dict) else None,
        "seeds": seeds,
        "announced": announced,
        "peers_http": pc,
        "peer_urls": peer_urls,
        "stale_link_local_hidden": (peers.get("stale_link_local_hidden") if isinstance(peers, dict) else None),
        "has_169254_in_api_list": any("169.254" in str(u) for u in peer_urls),
    }


REMOTE_HW = r"""
python3 - <<'PY'
import json, os
from pathlib import Path
def t(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace").strip() or None
    except OSError:
        return None
print(json.dumps({
    "tpm0": Path("/dev/tpm0").exists(),
    "sys_vendor": t("/sys/class/dmi/id/sys_vendor"),
    "product_name": t("/sys/class/dmi/id/product_name"),
    "sev": Path("/dev/sev").exists(),
    "sgx": Path("/dev/sgx_enclave").exists(),
    "hostname": os.uname().nodename,
}))
PY
"""


def classify_ssh(name: str) -> dict:
    raw = _ssh(name, REMOTE_HW)
    body = {}
    try:
        body = json.loads((raw.get("stdout") or "").strip() or "{}")
    except json.JSONDecodeError:
        body = {"parse_error": True, "stdout": (raw.get("stdout") or "")[:200]}
    tpm = bool(body.get("tpm0"))
    product = str(body.get("product_name") or "").lower()
    vendor = str(body.get("sys_vendor") or "").lower()
    virt = "openstack" in product or "amazon" in vendor or "nova" in product
    grade = classify_hardware_assurance(
        tpm_device_present=tpm,
        chassis_virtual=virt,
        tee_kind="sev" if body.get("sev") else None,
        hsm_bound=False,
    )
    return {"ssh": {"returncode": raw.get("returncode")}, "facts": body, "grade": grade}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{stamp}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="192-hw-baremetal",
        simulation_id=SIM_ID,
        seed=192,
        script_path=Path(__file__),
        extra={"branch_expected": BRANCH},
    )
    _write(out_dir, "00_manifest.json", manifest)
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_lock.json", public_lock())

    local_view = public_machine_view(None)
    local_tpm = tpm_sysfs_facts()
    local_virt = virtualization_facts()
    local_tee = tee_facts()
    _write(
        out_dir,
        "12_local_detector.json",
        {
            "machine": local_view,
            "tpm": local_tpm,
            "virt": {k: local_virt.get(k) for k in ("chassis_virtual", "virt_tech", "sys_vendor", "product_name")},
            "tee": local_tee,
            "note": "This runner is not a live seed. Do not treat it as OVH1.",
        },
    )

    matrix = {label: probe_node(label, ip) for label, ip in LABELS.items()}
    _write(out_dir, "20_live_matrix.json", matrix)

    hw = {label: classify_ssh(label) for label in LABELS}
    _write(out_dir, "21_ssh_hardware.json", hw)

    sys.path.insert(0, str(ROOT / "scripts"))
    from ovh_baremetal_quote import quote as quote_fn  # noqa: E402

    quoted = quote_fn(want_order=False)
    _write(out_dir, "22_ovh_quote.json", quoted)

    shas = {k: (v.get("health") or {}).get("git_sha") for k, v in matrix.items()}
    hashes = {k: v.get("last_hash") for k, v in matrix.items()}
    heights = {k: v.get("height") for k, v in matrix.items()}
    gate = certification_gate(
        {letter: "PASS" for letter in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")}
    )
    failures: list[str] = []
    if len({x for x in shas.values() if x}) != 1:
        failures.append("sha_mismatch")
    if len({x for x in hashes.values() if x}) != 1:
        failures.append("hash_mismatch")
    if any(h != 1 for h in heights.values()):
        failures.append("height_not_1")
    ssh_levels = {k: (hw[k].get("grade") or {}).get("hardware_assurance_level") for k in hw}
    if any(lv != "E" for lv in ssh_levels.values() if lv):
        failures.append("vm_not_level_E")
    if any((hw[k].get("facts") or {}).get("tpm0") for k in hw):
        failures.append("invented_or_unexpected_tpm")
    if quoted.get("order", {}).get("executed"):
        failures.append("order_executed_without_ovh3")
    if gate.get("certified_distributed_mainnet"):
        failures.append("certified_true")
    if "ovh-baremetal-1" not in NODES:
        failures.append("baremetal_registry_missing")
    if NODES["ovh-baremetal-1"].ssh_host == "152.228.144.34":
        failures.append("reused_ovh1")

    summary = {
        "sim": SIM_ID,
        "decisions_192": DECISIONS_192,
        "live_shas": shas,
        "heights": heights,
        "last_hashes": hashes,
        "ssh_levels": ssh_levels,
        "quote_cheapest": quoted.get("selected"),
        "ovh3_credit_reason": (quoted.get("ovh3_credit") or {}).get("reason"),
        "order_executed": quoted.get("order", {}).get("executed"),
        "certification_gate": gate,
        "failures": failures,
        "install_sh": False,
        "init_genesis": False,
        "init_node": False,
        "book_wiped": False,
        "note": (
            "D-046: live book kept. TPM not faked. OVH3 not ordered. "
            "Four VMs stay level E. ovh-baremetal-1 is a slot, not a rewrite."
        ),
    }
    _write(out_dir, "24_summary.json", summary)
    _write(out_dir, "00_manifest.json", finish(manifest))
    print(dumps({"out_dir": str(out_dir), "failures": failures, "summary": summary}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
