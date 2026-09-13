"""R338 — Hardware capability discovery BEFORE attestation / C04.

Capability-first: never install/workaround TPM software to fake a missing RoT.

Verdicts:
  PASS / FAIL / NOT_PROVEN / UNSUPPORTED_HARDWARE / NOT_APPLICABLE

C04 is **hardware-backed node identity** (policy of accepted RoT), not ``must find TPM``.
Software Keychain fallback must never be marked security-equivalent to hardware RoT.
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any


def _sh(cmd: str, timeout: float = 20.0) -> tuple[str, int]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return ((r.stdout or "") + (r.stderr or "")).strip(), int(r.returncode)
    except Exception as exc:  # noqa: BLE001
        return str(exc), -1


def discover_mac_root_of_trust() -> dict[str, Any]:
    """Preflight for this host (typically mac-node-local)."""
    model, _ = _sh("sysctl -n hw.model")
    cpu, _ = _sh("sysctl -n machdep.cpu.brand_string")
    arch = platform.machine()
    macos = platform.mac_ver()[0]
    apple_silicon = arch == "arm64"
    spi, _ = _sh("ioreg -l -p IODeviceTree 2>/dev/null | grep -i SPiBridge | head -5")
    t2_prof, _ = _sh("system_profiler SPiBridgeDataType 2>/dev/null | head -40")
    t2_detected = bool(spi) or ("T2" in t2_prof) or ("Apple T2" in t2_prof)
    tpm_nodes = {
        p: Path(p).exists() for p in ("/dev/tpm0", "/dev/tpmrm0")
    }
    tpm_device = any(tpm_nodes.values())

    if apple_silicon:
        rot = "APPLE_SILICON_SEP_CANDIDATE"
        c04 = "NOT_PROVEN"  # still need crypto op + attestation proof
        reason = "Apple Silicon present; SEP candidate — crypto attestation not proven here"
    elif t2_detected:
        rot = "INTEL_T2_CANDIDATE"
        c04 = "NOT_PROVEN"
        reason = "T2 candidate detected — attestation API path not proven here"
    elif tpm_device:
        rot = "TPM_DEVICE_PRESENT"
        c04 = "NOT_PROVEN"
        reason = "/dev/tpm* present — quote/verify path not proven here"
    else:
        rot = "NOT_AVAILABLE_ON_THIS_MAC"
        c04 = "UNSUPPORTED_HARDWARE"
        reason = "No Apple Silicon, no T2 (SPiBridge), no /dev/tpm* — do not force C04"

    return {
        "protocol": "r338-capability-discovery-v1",
        "ts_ns": time.time_ns(),
        "model": model or "UNKNOWN",
        "cpu": cpu,
        "arch": arch,
        "macos": macos,
        "apple_silicon": apple_silicon,
        "t2_detected": t2_detected,
        "tpm_device_nodes": tpm_nodes,
        "TPM_ROOT_OF_TRUST": rot,
        "C04_verdict": c04,
        "C04_reason": reason,
        "software_fallback": "AVAILABLE_BUT_NOT_EQUIVALENT",
        "security_equivalence_to_hardware_rot": False,
        "method": "CAPABILITY_DISCOVERY_FIRST",
        "certified_100": False,
        "policy": (
            "C04 = hardware-backed identity under accepted RoT policy; "
            "TPM is one implementation, not the requirement name"
        ),
    }


def classify_c04(*, capability: dict[str, Any], crypto_attested: bool | None = None) -> str:
    """Map discovery (+ optional crypto proof) to certification bucket."""
    base = str(capability.get("C04_verdict") or "NOT_PROVEN")
    if base == "UNSUPPORTED_HARDWARE":
        return "UNSUPPORTED_HARDWARE"
    if crypto_attested is True:
        return "PASS"
    if crypto_attested is False:
        return "FAIL"
    return "NOT_PROVEN"


def write_report(path: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = payload or discover_mac_root_of_trust()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data
