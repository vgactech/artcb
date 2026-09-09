"""Platform attestation: hardware TPM when present, cloud identity on VMs.

These four official nodes are VMs. `/dev/tpm0` is typically absent. That is
not a license to invent a TPM quote, and it is not a license to forget that
bare-metal operators will have a real TPM.

Classes (honest, never recast):
    tpm_hardware          — /dev/tpm0 present; quote may still be missing
    cloud_instance_identity — AWS IMDS / OVH metadata closest analog
    vm_unattested         — hypervisor VM, no TPM, no verifiable cloud doc
    unknown

A cloud instance-identity document is NOT a TPM quote. A software TPM
(swtpm) is NOT a hardware TPM. Bare-metal path stays implemented and idle
until a device appears.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from src.artcb.trace.ns import now_wall_ns


def _read_text(path: Path, limit: int = 400) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()[:limit]
    except OSError:
        return ""


def _cmd(args: list[str], timeout: int = 8) -> dict[str, Any]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": type(exc).__name__, "stdout": ""}
    return {
        "ok": proc.returncode == 0,
        "rc": proc.returncode,
        "stdout": (proc.stdout or "")[-500:],
        "stderr": (proc.stderr or "")[-160:],
    }


def _http_plain(url: str, headers: dict[str, str] | None = None, timeout: int = 2, method: str = "GET") -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {}, method=method, data=b"" if method == "PUT" else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "http": resp.status, "body": raw[:4000]}
    except Exception as exc:
        return {"ok": False, "http": 0, "error": type(exc).__name__, "body": ""}


def tpm_probe() -> dict[str, Any]:
    tpm0 = Path("/dev/tpm0").exists()
    tpmrm = Path("/dev/tpmrm0").exists()
    tools = _cmd(["bash", "-lc", "command -v tpm2_getcap >/dev/null && echo yes || echo no"])
    has_tools = "yes" in (tools.get("stdout") or "")
    quote = None
    pcrs = None
    if tpm0 and has_tools:
        pcrs = _cmd(["tpm2_pcrread", "sha256:0,1,7"], timeout=10)
        quote = None  # a real AK quote needs an enrolled AK; do not fake one
    return {
        "present": bool(tpm0 or tpmrm),
        "tpm0": tpm0,
        "tpmrm0": tpmrm,
        "tpm2_tools": has_tools,
        "quote": quote,
        "pcrs": pcrs,
        "verdict": "HARDWARE_PRESENT_QUOTE_MISSING" if tpm0 and quote is None else ("ABSENT" if not tpm0 else "NOT_PROVEN"),
        "note": "device presence ≠ attested quote. swtpm is not hardware TPM.",
    }


def virt_probe() -> dict[str, Any]:
    detect = _cmd(["systemd-detect-virt"])
    virt = (detect.get("stdout") or "").strip() or "unknown"
    return {
        "systemd_detect_virt": virt,
        "is_vm": virt not in {"", "none", "unknown"} and detect.get("ok") is True,
        "dmi_sys_vendor": _read_text(Path("/sys/class/dmi/id/sys_vendor")),
        "dmi_product": _read_text(Path("/sys/class/dmi/id/product_name")),
        "dmi_uuid": _read_text(Path("/sys/class/dmi/id/product_uuid")),
        "machine_id": _read_text(Path("/etc/machine-id")),
        "hostname": socket.gethostname(),
    }


def aws_imds_probe() -> dict[str, Any]:
    token = _http_plain(
        "http://169.254.169.254/latest/api/token",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
        timeout=1,
        method="PUT",
    )
    hdr = {}
    if token.get("ok") and token.get("body"):
        hdr["X-aws-ec2-metadata-token"] = token["body"].strip()
    doc = _http_plain("http://169.254.169.254/latest/dynamic/instance-identity/document", headers=hdr, timeout=1)
    pkcs7 = _http_plain("http://169.254.169.254/latest/dynamic/instance-identity/pkcs7", headers=hdr, timeout=1)
    parsed = None
    if doc.get("ok") and (doc.get("body") or "").lstrip().startswith("{"):
        try:
            parsed = json.loads(doc["body"])
        except json.JSONDecodeError:
            parsed = None
    return {
        "reachable": bool(doc.get("ok") or token.get("http")),
        "document_ok": bool(parsed),
        "pkcs7_present": bool(pkcs7.get("ok") and pkcs7.get("body")),
        "instance_id": (parsed or {}).get("instanceId"),
        "instance_type": (parsed or {}).get("instanceType"),
        "region": (parsed or {}).get("region"),
        "account": (parsed or {}).get("accountId"),
        "note": "AWS instance-identity document is a cloud analog, not a TPM quote.",
    }


def ovh_metadata_probe() -> dict[str, Any]:
    # OVH Public Cloud / OpenStack metadata (when present).
    doc = _http_plain("http://169.254.169.254/openstack/latest/meta_data.json", timeout=1)
    parsed = None
    if doc.get("ok") and (doc.get("body") or "").lstrip().startswith("{"):
        try:
            parsed = json.loads(doc["body"])
        except json.JSONDecodeError:
            parsed = None
    return {
        "reachable": bool(doc.get("ok")),
        "document_ok": bool(parsed),
        "uuid": (parsed or {}).get("uuid"),
        "name": (parsed or {}).get("name"),
        "project_id": (parsed or {}).get("project_id"),
        "note": "OpenStack/OVH metadata is a cloud analog, not a TPM quote.",
    }


def classify(*, tpm: dict[str, Any], virt: dict[str, Any], aws: dict[str, Any], ovh: dict[str, Any]) -> str:
    if tpm.get("present"):
        return "tpm_hardware"
    if aws.get("document_ok"):
        return "cloud_instance_identity"
    if ovh.get("document_ok"):
        return "cloud_instance_identity"
    if virt.get("is_vm"):
        return "vm_unattested"
    return "unknown"


def collect_platform_attestation() -> dict[str, Any]:
    tpm = tpm_probe()
    virt = virt_probe()
    aws = aws_imds_probe()
    ovh = ovh_metadata_probe()
    klass = classify(tpm=tpm, virt=virt, aws=aws, ovh=ovh)
    tpm_certified = bool(tpm.get("present") and tpm.get("quote"))
    return {
        "protocol": "278-platform-attestation",
        "ts_ns": now_wall_ns(),
        "platform_class": klass,
        "tpm": tpm,
        "virt": virt,
        "aws_imds": aws,
        "ovh_metadata": ovh,
        "tpm_quote_proven": tpm_certified,
        "cloud_identity_closest_analog": klass == "cloud_instance_identity",
        "bare_metal_tpm_path_implemented": True,
        "certified_hardware_identity": False,
        "note": (
            "VM cloud identity ≠ TPM. Hardware TPM path is implemented and waits "
            "for /dev/tpm0 (bare-metal users). Do not recast ABSENT as PASS."
        ),
    }


def overlay_path() -> Path:
    extra = (os.getenv("ARTCB_REPLICA_OVERLAY") or "").strip()
    return Path(extra) if extra else Path("/etc/artcb/replica_overlay.json")
