"""TPM device kind — /dev/tpm0 is not a trust root by itself.

    HARDWARE_TPM      bare-metal proven + hardware device
    HYPERVISOR_VTPM   hypervisor-provided vTPM (incl. NitroTPM)
    NITROTPM          AWS NitroTPM (subset of hypervisor vTPM)
    SOFTWARE_TPM      swtpm / guest emulation — never L3
    UNKNOWN_TPM       device present, root not proven
    ABSENT            no device
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

KIND_HARDWARE = "HARDWARE_TPM"
KIND_HYPERVISOR = "HYPERVISOR_VTPM"
KIND_NITRO = "NITROTPM"
KIND_SOFTWARE = "SOFTWARE_TPM"
KIND_UNKNOWN = "UNKNOWN_TPM"
KIND_ABSENT = "ABSENT"

L3_KINDS = frozenset({KIND_HYPERVISOR, KIND_NITRO})
SOFTWARE_MANUFACTURERS = frozenset({"SW", "SW  ", "SWTP", "SWTPM"})
NITRO_MANUFACTURERS = frozenset({"AMZN"})

KNOWN_VM_VIRT = frozenset(
    {
        "kvm",
        "qemu",
        "amazon",
        "microsoft",
        "oracle",
        "vmware",
        "xen",
        "parallels",
        "bhyve",
        "bochs",
        "uml",
        "zvm",
        "powervm",
        "wsl",
        "lxc",
        "lxc-libvirt",
        "docker",
        "podman",
        "container",
        "openvz",
        "systemd-nspawn",
        "proxmox",
    }
)


def parse_tpm2_properties(stdout: str) -> dict[str, str]:
    text = str(stdout or "")
    manufacturer = ""
    vendor_parts: list[str] = []
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if "TPM2_PT_MANUFACTURER" in line:
            current = "manufacturer"
            continue
        if "TPM2_PT_VENDOR_STRING" in line:
            current = "vendor"
            continue
        if line.startswith("value:"):
            value = line.split(":", 1)[1].strip().strip('"')
            if current == "manufacturer":
                manufacturer = value
            elif current == "vendor" and value:
                vendor_parts.append(value)
            current = ""
    # Hex ASCII fallback: 0x414D5A4E → AMZN
    if not manufacturer:
        m = re.search(r"TPM2_PT_MANUFACTURER.*?0x([0-9A-Fa-f]{8})", text, re.S)
        if m:
            raw_hex = m.group(1)
            try:
                manufacturer = bytes.fromhex(raw_hex).decode("ascii", errors="replace").strip()
            except ValueError:
                manufacturer = ""
    return {"manufacturer": manufacturer, "vendor": "".join(vendor_parts).strip()}


def software_tpm_observed(tpm: dict[str, Any] | None = None) -> bool:
    extra = tpm or {}
    if extra.get("software_tpm") is True:
        return True
    if str(extra.get("device_kind") or "") == KIND_SOFTWARE:
        return True
    vendor = str(extra.get("vendor") or extra.get("tpm_vendor") or "").lower()
    if "swtpm" in vendor or "software tpm" in vendor:
        return True
    manu = str(extra.get("manufacturer") or extra.get("tpm_manufacturer") or "").upper().strip()
    if manu in SOFTWARE_MANUFACTURERS:
        return True
    try:
        if Path("/var/run/swtpm").exists() or Path("/tmp/swtpm-sock").exists():
            return True
    except OSError:
        pass
    return False


def environment_certainty(virt: dict[str, Any]) -> str:
    explicit = str(virt.get("environment_certainty") or "").strip()
    if explicit in {"VM_PROVEN", "BARE_METAL_PROVEN", "UNKNOWN"}:
        return explicit
    if virt.get("bare_metal_proven") is True:
        return "BARE_METAL_PROVEN"
    if virt.get("is_vm") is True:
        return "VM_PROVEN"
    return "UNKNOWN"


def classify_tpm_kind(*, tpm: dict[str, Any], virt: dict[str, Any]) -> str:
    """Device kind. Presence alone never yields HYPERVISOR_VTPM or HARDWARE_TPM."""
    if tpm.get("device_kind") in {
        KIND_HARDWARE,
        KIND_HYPERVISOR,
        KIND_NITRO,
        KIND_SOFTWARE,
        KIND_UNKNOWN,
        KIND_ABSENT,
    }:
        return str(tpm["device_kind"])
    if not tpm.get("present"):
        return KIND_ABSENT
    if software_tpm_observed(tpm):
        return KIND_SOFTWARE
    manu = str(tpm.get("manufacturer") or tpm.get("tpm_manufacturer") or "").upper().strip()
    vendor = str(tpm.get("vendor") or tpm.get("tpm_vendor") or "").lower()
    if manu in NITRO_MANUFACTURERS or "nitrotpm" in vendor:
        return KIND_NITRO
    certainty = environment_certainty(virt)
    if certainty == "BARE_METAL_PROVEN":
        return KIND_HARDWARE
    if certainty == "VM_PROVEN":
        # Device on a VM without vendor proof is unknown, not L3.
        return KIND_UNKNOWN
    return KIND_UNKNOWN


def hypervisor_vtpm_proven(kind: str) -> bool:
    return kind in L3_KINDS
