"""Multi-root platform attestation — TPM is one root, not the only one.

Policy (R283): ENVIRONMENT → CAPABILITIES → MAXIMUM LEVEL → REQUIRED
EVIDENCE → VERIFY → PROFILE CERTIFICATION.

Never: « every node must satisfy L4 hardware TPM ».
L4 on a VM is NOT_APPLICABLE / NOT_REACHABLE, not a universal FAIL.

Best available proof on this machine, never recast:

    L4  TPM hardware + quote + PCR     → TPM_ATTESTED
    L3  vTPM + quote                   → VTPM_ATTESTED
    L2  cloud instance identity        → CLOUD_ATTESTED
    L1  VM / machine identity observed → VM_UNATTESTED (observed)
    L0  nothing reliable               → UNKNOWN / UNATTESTED

A cloud Instance Identity Document is NOT a TPM Quote.
A software TPM (swtpm) / vTPM is NOT a hardware TPM.
CLOUD_ATTESTED is valid for a cloud VM security level; it is never
certified_hardware_identity.

L2 CLOUD_ATTESTED means: provider instance identity was observed and
bound to the ARTCB registry. It is NOT a CA-verified cryptographic
attestation and it is NOT a TPM quote.

`attestation_crypto_verified` stays false until a TPM/vTPM quote verifies.
An AWS RSA-2048 pin against the published regional cert is a *sub*-verdict
(`aws_iid_rsa2048_pin`); it does not flip L3/L4 or CERTIFIED_100.
OVH metadata remains unsigned in this implementation.

`CERTIFIED_100` on a node means: 100 % of requirements applicable to the
detected environment profile are PASS. It does not mean L4 everywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from src.artcb.consensus.tpm_kind import (
    KIND_ABSENT,
    KIND_HARDWARE,
    KIND_SOFTWARE,
    KIND_UNKNOWN,
    KNOWN_VM_VIRT,
    classify_tpm_kind,
    environment_certainty,
    hypervisor_vtpm_proven,
    parse_tpm2_properties,
    software_tpm_observed,
)
from src.artcb.trace.agent_run import POLICY_ID, POLICY_VERSION, policy_hash
from src.artcb.trace.ns import now_wall_ns

NETWORK_ID = "artcb-official"
BINDING_REL = Path(__file__).resolve().parent / "official_platform_binding.json"

TRUST_L4_TPM = 4
TRUST_L3_VTPM = 3
TRUST_L2_CLOUD = 2
TRUST_L1_OBSERVED = 1
TRUST_L0_NONE = 0

_binding_override: dict[str, dict[str, str]] | None = None


def _read_text(path: Path, limit: int = 400) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()[:limit]
    except OSError:
        return ""


def _cmd(args: list[str], timeout: int = 8, keep: int = 500) -> dict[str, Any]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": type(exc).__name__, "stdout": ""}
    return {
        "ok": proc.returncode == 0,
        "rc": proc.returncode,
        "stdout": (proc.stdout or "")[:keep] if keep > 500 else (proc.stdout or "")[-keep:],
        "stderr": (proc.stderr or "")[-160:],
    }


def _http_plain(url: str, headers: dict[str, str] | None = None, timeout: int = 2, method: str = "GET") -> dict[str, Any]:
    import urllib.request

    req = urllib.request.Request(url, headers=headers or {}, method=method, data=b"" if method == "PUT" else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "http": resp.status, "body": raw[:4000]}
    except Exception as extra:
        return {"ok": False, "http": 0, "error": type(extra).__name__, "body": ""}


def tpm_probe() -> dict[str, Any]:
    tpm0 = Path("/dev/tpm0").exists()
    tpmrm = Path("/dev/tpmrm0").exists()
    tools = _cmd(["bash", "-lc", "command -v tpm2_getcap >/dev/null && echo yes || echo no"])
    has_tools = "yes" in (tools.get("stdout") or "")
    quote = None
    pcrs = None
    props = {"manufacturer": "", "vendor": ""}
    if (tpm0 or tpmrm) and has_tools:
        pcrs = _cmd(["tpm2_pcrread", "sha256:0,1,7"], timeout=10)
        cap = _cmd(["tpm2_getcap", "properties-fixed"], timeout=10, keep=4000)
        props = parse_tpm2_properties(str(cap.get("stdout") or ""))
        quote = None  # a real AK quote needs an enrolled AK; do not fake one
    sw = software_tpm_observed({"manufacturer": props.get("manufacturer"), "vendor": props.get("vendor")})
    sw_proc = _cmd(["bash", "-lc", "pgrep -a swtpm || true"])
    if "swtpm" in (sw_proc.get("stdout") or "").lower():
        sw = True
    return {
        "present": bool(tpm0 or tpmrm),
        "tpm0": tpm0,
        "tpmrm0": tpmrm,
        "tpm2_tools": has_tools,
        "manufacturer": props.get("manufacturer") or "",
        "vendor": props.get("vendor") or "",
        "software_tpm": sw,
        "quote": quote,
        "pcrs": pcrs,
        "verdict": (
            "HARDWARE_PRESENT_QUOTE_MISSING"
            if tpm0 and quote is None
            else ("ABSENT" if not tpm0 else "NOT_PROVEN")
        ),
        "note": (
            "device presence ≠ attested quote. swtpm is SOFTWARE_TPM, never L3. "
            "NitroTPM requires manufacturer AMZN / vendor NitroTPM, not /dev/tpm0 alone."
        ),
    }


def virt_probe() -> dict[str, Any]:
    detect = _cmd(["systemd-detect-virt"])
    virt = (detect.get("stdout") or "").strip().lower() or "unknown"
    cmd_ok = detect.get("ok") is True
    dmi_vendor = _read_text(Path("/sys/class/dmi/id/sys_vendor"))
    dmi_product = _read_text(Path("/sys/class/dmi/id/product_name"))
    if cmd_ok and virt == "none":
        certainty = "BARE_METAL_PROVEN"
        is_vm = False
        bare = True
    elif cmd_ok and virt in KNOWN_VM_VIRT:
        certainty = "VM_PROVEN"
        is_vm = True
        bare = False
    else:
        certainty = "UNKNOWN"
        is_vm = False
        bare = False
        blob = f"{dmi_vendor} {dmi_product}".lower()
        if any(token in blob for token in ("amazon", "qemu", "google", "xen", "ovh", "kvm", "bochs", "vmware")):
            certainty = "VM_PROVEN"
            is_vm = True
    return {
        "systemd_detect_virt": virt,
        "systemd_detect_virt_ok": cmd_ok,
        "environment_certainty": certainty,
        "bare_metal_proven": bare,
        "is_vm": is_vm,
        "dmi_sys_vendor": dmi_vendor,
        "dmi_product": dmi_product,
        "dmi_uuid": _read_text(Path("/sys/class/dmi/id/product_uuid")),
        "machine_id": _read_text(Path("/etc/machine-id")),
        "hostname": socket.gethostname(),
        "note": "UNKNOWN is not BARE_METAL. A failed virt probe must not raise trust.",
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
    rsa2048 = _http_plain("http://169.254.169.254/latest/dynamic/instance-identity/rsa2048", headers=hdr, timeout=1)
    parsed = None
    raw_doc = doc.get("body") or ""
    if doc.get("ok") and raw_doc.lstrip().startswith("{"):
        try:
            parsed = json.loads(raw_doc)
        except json.JSONDecodeError:
            parsed = None
    return {
        "reachable": bool(doc.get("ok") or token.get("http")),
        "document_ok": bool(parsed),
        "pkcs7_present": bool(pkcs7.get("ok") and pkcs7.get("body")),
        "pkcs7_verified": False,
        "rsa2048_present": bool(rsa2048.get("ok") and rsa2048.get("body")),
        "instance_id": (parsed or {}).get("instanceId"),
        "instance_type": (parsed or {}).get("instanceType"),
        "region": (parsed or {}).get("region"),
        "_document_raw": raw_doc if parsed else "",
        "_rsa2048_raw": (rsa2048.get("body") or "") if rsa2048.get("ok") else "",
        "note": (
            "AWS instance-identity document is a cloud analog, not a TPM quote. "
            "accountId omitted from public fields. RSA-2048 pin uses the published "
            "regional cert; that is not a TPM quote and not CERTIFIED_100."
        ),
    }


def ovh_metadata_probe() -> dict[str, Any]:
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
        "signature_verified": False,
        "note": (
            "OpenStack/OVH metadata is a cloud analog, not a TPM quote. "
            "project_id omitted. Link-local document is unsigned in this revision."
        ),
    }


def classify(*, tpm: dict[str, Any], virt: dict[str, Any], aws: dict[str, Any], ovh: dict[str, Any]) -> str:
    """Primary evidence class. Device presence is not hypervisor vTPM or hardware TPM."""
    kind = classify_tpm_kind(tpm=tpm, virt=virt)
    certainty = environment_certainty(virt)
    if kind == KIND_HARDWARE and certainty == "BARE_METAL_PROVEN":
        return "tpm_hardware"
    if hypervisor_vtpm_proven(kind):
        return "vtpm"
    if aws.get("document_ok") or ovh.get("document_ok"):
        return "cloud_instance_identity"
    if certainty == "VM_PROVEN" or virt.get("is_vm"):
        return "vm_unattested"
    return "unknown"


def quote_present(tpm: dict[str, Any]) -> bool:
    """True only for a cryptographically verified quote. A dict of failure is not a quote."""
    quote = tpm.get("quote")
    if not isinstance(quote, dict):
        return False
    return quote.get("verified") is True


def completed_trust_level(
    *,
    klass: str,
    tpm: dict[str, Any],
    virt: dict[str, Any],
    aws: dict[str, Any],
    ovh: dict[str, Any],
) -> int:
    """Highest *completed* proof. Device-without-quote does not grant L4/L3.

    SOFTWARE_TPM and UNKNOWN_TPM quotes never grant L3.
    UNKNOWN environment never grants L4.
    """
    has_quote = quote_present(tpm)
    kind = classify_tpm_kind(tpm=tpm, virt=virt)
    certainty = environment_certainty(virt)
    if klass == "tpm_hardware" and has_quote and kind == KIND_HARDWARE and certainty == "BARE_METAL_PROVEN":
        return TRUST_L4_TPM
    if klass == "vtpm" and has_quote and hypervisor_vtpm_proven(kind):
        return TRUST_L3_VTPM
    if aws.get("document_ok") or ovh.get("document_ok"):
        return TRUST_L2_CLOUD
    if virt.get("is_vm") or klass == "vm_unattested" or certainty == "VM_PROVEN":
        return TRUST_L1_OBSERVED
    if klass == "tpm_hardware" or klass == "vtpm":
        return TRUST_L1_OBSERVED
    return TRUST_L0_NONE


def hardware_tpm_attestation(*, klass: str, tpm: dict[str, Any], virt: dict[str, Any]) -> str:
    """L4 hardware TPM axis. On a VM or UNKNOWN environment this is not L4."""
    certainty = environment_certainty(virt)
    if virt.get("is_vm") or certainty == "VM_PROVEN" or klass in {"vtpm", "cloud_instance_identity", "vm_unattested"}:
        return "NOT_APPLICABLE"
    if certainty != "BARE_METAL_PROVEN":
        return "NOT_PROVEN"
    if klass == "tpm_hardware" and quote_present(tpm):
        return "TPM_HARDWARE_ATTESTED"
    if klass == "tpm_hardware":
        return "HARDWARE_PRESENT_QUOTE_MISSING"
    if not tpm.get("present"):
        return "NOT_REACHABLE"
    return "NOT_REACHABLE"


def vtpm_attestation(*, klass: str, tpm: dict[str, Any]) -> str:
    if klass != "vtpm":
        return "NOT_APPLICABLE"
    if quote_present(tpm):
        return "VTPM_ATTESTED"
    return "VTPM_PRESENT_QUOTE_MISSING"


def platform_identity_attestation(*, aws: dict[str, Any], ovh: dict[str, Any], klass: str) -> str:
    if aws.get("document_ok"):
        return "AWS_CLOUD_ATTESTED"
    if ovh.get("document_ok"):
        return "OVH_CLOUD_ATTESTED"
    if klass == "vm_unattested":
        return "VM_UNATTESTED"
    if klass in {"tpm_hardware", "vtpm"}:
        return "NOT_APPLICABLE"
    return "UNKNOWN"


def overall_platform_trust(level: int) -> str:
    return {
        TRUST_L4_TPM: "TPM_ATTESTED",
        TRUST_L3_VTPM: "VTPM_ATTESTED",
        TRUST_L2_CLOUD: "CLOUD_ATTESTED",
        TRUST_L1_OBSERVED: "VM_UNATTESTED",
        TRUST_L0_NONE: "UNKNOWN",
    }.get(level, "UNKNOWN")


def detect_environment(*, virt: dict[str, Any], aws: dict[str, Any], ovh: dict[str, Any]) -> str:
    """UNKNOWN ≠ BARE_METAL. Cloud identity is independent VM proof."""
    if aws.get("document_ok") or ovh.get("document_ok"):
        return "CLOUD_VM"
    certainty = environment_certainty(virt)
    if certainty == "VM_PROVEN" or virt.get("is_vm"):
        return "VM"
    if certainty == "BARE_METAL_PROVEN":
        return "BARE_METAL"
    return "UNKNOWN"


def detect_environment_profile(
    *,
    virt: dict[str, Any],
    tpm: dict[str, Any],
    aws: dict[str, Any],
    ovh: dict[str, Any],
) -> str:
    env = detect_environment(virt=virt, aws=aws, ovh=ovh)
    kind = classify_tpm_kind(tpm=tpm, virt=virt)
    if env == "UNKNOWN":
        return "UNKNOWN"
    if env == "BARE_METAL":
        return "BARE_METAL"
    if hypervisor_vtpm_proven(kind) and env == "CLOUD_VM":
        return "CLOUD_VM_VTPM"
    if hypervisor_vtpm_proven(kind):
        return "VM_VTPM"
    if kind == KIND_SOFTWARE:
        return "CLOUD_VM_SOFTWARE_TPM" if env == "CLOUD_VM" else "VM_SOFTWARE_TPM"
    if kind == KIND_UNKNOWN and tpm.get("present"):
        return "CLOUD_VM_TPM_UNKNOWN" if env == "CLOUD_VM" else "VM_TPM_UNKNOWN"
    if env == "CLOUD_VM":
        return "CLOUD_VM"
    return "VM_UNATTESTED"


def maximum_theoretical_level(profile: str, *, tpm: dict[str, Any], virt: dict[str, Any] | None = None) -> int:
    """What this *class* could reach if evidence were complete. Not a proven max."""
    virt = virt or {}
    kind = classify_tpm_kind(tpm=tpm, virt=virt)
    if profile == "UNKNOWN":
        return TRUST_L0_NONE
    if kind == KIND_SOFTWARE:
        return TRUST_L2_CLOUD if profile.startswith("CLOUD_") else TRUST_L1_OBSERVED
    if profile == "BARE_METAL":
        return TRUST_L4_TPM if tpm.get("present") and kind == KIND_HARDWARE else TRUST_L1_OBSERVED
    if profile in {"CLOUD_VM_VTPM", "VM_VTPM"}:
        return TRUST_L3_VTPM
    if profile in {"CLOUD_VM_TPM_UNKNOWN", "VM_TPM_UNKNOWN"}:
        return TRUST_L3_VTPM
    if profile.startswith("CLOUD_"):
        return TRUST_L2_CLOUD
    if profile in {"VM_UNATTESTED", "VM_SOFTWARE_TPM"}:
        return TRUST_L1_OBSERVED
    return TRUST_L0_NONE


def maximum_verified_level(*, attested: int, kind: str, profile: str) -> int:
    """Highest level the *proven* root actually supports. swtpm never L3."""
    if kind == KIND_SOFTWARE:
        return min(attested, TRUST_L2_CLOUD if profile.startswith("CLOUD_") else TRUST_L1_OBSERVED)
    if kind == KIND_UNKNOWN:
        return min(attested, TRUST_L2_CLOUD if profile.startswith("CLOUD_") else TRUST_L1_OBSERVED)
    if profile == "UNKNOWN":
        return TRUST_L0_NONE
    return attested


def maximum_supported_level(profile: str, *, tpm: dict[str, Any], virt: dict[str, Any] | None = None) -> int:
    """Compat alias of maximum_theoretical_level. Do not read as verified max."""
    return maximum_theoretical_level(profile, tpm=tpm, virt=virt)


def _axis_applicability(profile: str, *, tpm_present: bool, kind: str) -> tuple[str, str]:
    """(l3_axis, l4_axis) — APPLICABLE / NOT_APPLICABLE / NOT_REACHABLE / NOT_PROVEN."""
    if profile == "UNKNOWN":
        return "NOT_PROVEN", "NOT_PROVEN"
    if kind == KIND_SOFTWARE:
        return "NOT_APPLICABLE", "NOT_APPLICABLE"
    if profile in {"CLOUD_VM_VTPM", "VM_VTPM"}:
        return "APPLICABLE", "NOT_APPLICABLE"
    if profile in {"CLOUD_VM_TPM_UNKNOWN", "VM_TPM_UNKNOWN"}:
        return "NOT_PROVEN", "NOT_APPLICABLE"
    if profile == "CLOUD_VM":
        return "NOT_REACHABLE", "NOT_APPLICABLE"
    if profile == "VM_UNATTESTED":
        return "NOT_REACHABLE", "NOT_APPLICABLE"
    if profile == "BARE_METAL":
        if tpm_present and kind == KIND_HARDWARE:
            return "NOT_APPLICABLE", "APPLICABLE"
        return "NOT_APPLICABLE", "NOT_REACHABLE"
    return "NOT_APPLICABLE", "NOT_APPLICABLE"


def _core_satisfied(value: str) -> bool:
    """NOT_REACHABLE does not satisfy a core requirement."""
    return value in {"PASS", "NOT_APPLICABLE"}


def _certified_100(requirements: dict[str, str]) -> bool:
    """Applicable satisfied / applicable == 100%. NOT_APPLICABLE is excluded.

    NOT_REACHABLE stays in the denominator and is not satisfied.
    """
    applicable = [v for v in requirements.values() if v != "NOT_APPLICABLE"]
    if not applicable:
        return False
    return all(v == "PASS" for v in applicable)


def missing_requirements(requirements: dict[str, str]) -> list[str]:
    return [k for k, v in requirements.items() if v not in {"PASS", "NOT_APPLICABLE"}]


def evaluate_environment_profile_policy(
    *,
    virt: dict[str, Any],
    tpm: dict[str, Any],
    aws: dict[str, Any],
    ovh: dict[str, Any],
    klass: str,
    level: int,
    binding: dict[str, Any],
    recast: bool,
    iid_pin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Four axes: environment, max level, attested level, profile certification."""
    environment = detect_environment(virt=virt, aws=aws, ovh=ovh)
    profile = detect_environment_profile(virt=virt, tpm=tpm, aws=aws, ovh=ovh)
    kind = classify_tpm_kind(tpm=tpm, virt=virt)
    max_theo = maximum_theoretical_level(profile, tpm=tpm, virt=virt)
    quote_ok = quote_present(tpm)
    q = tpm.get("quote") if isinstance(tpm.get("quote"), dict) else {}
    pin = iid_pin or {}
    official = set(load_platform_binding_registry())
    declared = str(binding.get("declared_node_id") or "")

    l3_app, l4_app = _axis_applicability(profile, tpm_present=bool(tpm.get("present")), kind=kind)
    if l3_app != "APPLICABLE":
        l3 = l3_app
    elif quote_ok and klass == "vtpm":
        l3 = "PASS"
    else:
        l3 = "NOT_PROVEN"
    if l4_app != "APPLICABLE":
        l4 = l4_app
    elif quote_ok and klass == "tpm_hardware":
        l4 = "PASS"
    else:
        l4 = "NOT_PROVEN"

    if aws.get("document_ok") or ovh.get("document_ok"):
        cloud = "PASS"
    elif profile == "BARE_METAL":
        cloud = "NOT_APPLICABLE"
    else:
        cloud = "NOT_PROVEN"

    if binding.get("identity_mismatch"):
        registry = "FAIL"
    elif binding.get("binding_verified"):
        registry = "PASS"
    else:
        registry = "NOT_PROVEN"

    if aws.get("document_ok"):
        meta = "PASS" if pin.get("verified") is True else "NOT_PROVEN"
    elif ovh.get("document_ok"):
        meta = "NOT_PROVEN"
    else:
        meta = "NOT_APPLICABLE"

    if klass in {"vtpm", "tpm_hardware"}:
        ek = "PASS" if q.get("ek_manufacturer_verified") is True else "NOT_PROVEN"
        prefix = str(q.get("binding_prefix_hex") or "")
        qbind = "PASS" if quote_ok and prefix and prefix != ("00" * 16) else "NOT_PROVEN"
        if q.get("freshness_bound") is True and quote_ok:
            freshness = "PASS"
        else:
            freshness = "NOT_PROVEN"
        quote_req = "PASS" if quote_ok else "NOT_PROVEN"
    else:
        ek = "NOT_APPLICABLE"
        qbind = "NOT_APPLICABLE"
        freshness = "NOT_APPLICABLE" if profile in {"CLOUD_VM", "VM_UNATTESTED"} else "NOT_PROVEN"
        quote_req = "NOT_APPLICABLE" if profile in {"CLOUD_VM", "VM_UNATTESTED"} else "NOT_PROVEN"

    capabilities = {
        "instance_identity": bool(aws.get("document_ok") or ovh.get("document_ok")),
        "vtpm_or_nitrotpm": hypervisor_vtpm_proven(kind),
        "tpm20_interface": bool(tpm.get("present")),
        "tpm_quote": quote_ok,
        "quote_verification": quote_ok,
        "hardware_tpm": kind == KIND_HARDWARE,
        "tpm_kind": kind,
        "software_tpm": kind == KIND_SOFTWARE,
    }

    if profile == "UNKNOWN":
        core = {"environment_detected": "NOT_PROVEN"}
        completeness = {"environment_certainty": "NOT_PROVEN"}
    elif profile == "CLOUD_VM":
        core = {
            "environment_detected": "PASS",
            "cloud_identity_observed": cloud,
            "registry_binding": registry,
        }
        completeness = {
            "metadata_signature": meta,
            "freshness_challenge": "NOT_PROVEN",
        }
    elif profile in {"CLOUD_VM_SOFTWARE_TPM", "CLOUD_VM_TPM_UNKNOWN"}:
        core = {
            "environment_detected": "PASS",
            "cloud_identity_observed": cloud,
            "registry_binding": registry,
        }
        completeness = {
            "metadata_signature": meta,
            "hypervisor_vtpm_provenance": "NOT_PROVEN" if profile.endswith("UNKNOWN") else "NOT_APPLICABLE",
            "freshness_challenge": "NOT_PROVEN",
        }
    elif profile in {"CLOUD_VM_VTPM", "VM_VTPM"}:
        core = {
            "environment_detected": "PASS",
            "vtpm_present": "PASS" if tpm.get("present") else "NOT_PROVEN",
            "quote_verified": quote_req,
        }
        if profile == "CLOUD_VM_VTPM" or declared in official:
            core["registry_binding"] = registry
        completeness = {
            "quote_freshness": freshness,
            "ek_ak_provenance": ek,
            "quote_node_binding": qbind,
        }
    elif profile == "BARE_METAL":
        present = bool(tpm.get("present")) and kind == KIND_HARDWARE
        core = {
            "environment_detected": "PASS",
            "hardware_tpm_present": "PASS" if present else "NOT_REACHABLE",
            "quote_verified": quote_req if present else "NOT_REACHABLE",
        }
        completeness = {
            "quote_freshness": freshness if present else "NOT_REACHABLE",
            "ek_ak_provenance": ek if present else "NOT_REACHABLE",
            "quote_node_binding": qbind if present else "NOT_REACHABLE",
        }
    else:
        core = {"environment_detected": "PASS" if environment != "UNKNOWN" else "NOT_PROVEN"}
        completeness = {"attested_identity": "NOT_PROVEN"}

    requirements = {**core, **completeness, "l3": l3, "l4": l4}
    missing = missing_requirements(requirements)
    max_verified = maximum_verified_level(attested=level, kind=kind, profile=profile)
    mismatch = bool(binding.get("identity_mismatch"))
    if recast or mismatch:
        certification = "FAIL"
        certified_100 = False
    elif profile in {"VM_UNATTESTED", "UNKNOWN", "VM_SOFTWARE_TPM", "VM_TPM_UNKNOWN"}:
        certification = "NOT_PROVEN"
        certified_100 = False
    elif any(v == "FAIL" for v in core.values()):
        certification = "FAIL"
        certified_100 = False
    elif not all(_core_satisfied(v) for v in core.values()):
        certification = "NOT_PROVEN"
        certified_100 = False
    else:
        certified_100 = _certified_100(requirements)
        if certified_100:
            certification = "PASS"
        elif profile in {"CLOUD_VM_VTPM", "VM_VTPM", "BARE_METAL"}:
            certification = "PARTIAL"
        else:
            certification = "PASS"

    q_sig = "PASS" if quote_ok else ("NOT_APPLICABLE" if kind in {KIND_ABSENT} else "NOT_PROVEN")
    return {
        "environment": environment,
        "environment_certainty": environment_certainty(virt),
        "environment_profile": profile,
        "tpm_kind": kind,
        "maximum_supported_level": max_theo,
        "maximum_theoretical_level": max_theo,
        "maximum_verified_level": max_verified,
        "attested_level": level,
        "capabilities": capabilities,
        "core_requirements": core,
        "completeness_requirements": completeness,
        "requirements": requirements,
        "missing_requirements": missing,
        "l3": l3,
        "l4": l4,
        "quote_freshness": freshness,
        "freshness_kind": (
            "VERIFIER_CHALLENGE"
            if q.get("verifier_challenge") is True
            else ("LOCAL_GENERATED" if q.get("freshness_bound") is True else "ABSENT")
        ),
        "ek_ak_provenance": ek,
        "quote_signature_verified": q_sig,
        "ak_provenance_verified": "PASS" if q.get("ak_manufacturer_verified") is True else "NOT_PROVEN",
        "ek_provenance_verified": "PASS" if q.get("ek_manufacturer_verified") is True else "NOT_PROVEN",
        "manufacturer_chain_verified": "PASS" if q.get("manufacturer_chain_verified") is True else "NOT_PROVEN",
        "quote_node_binding": qbind,
        "profile_certification": certification,
        "profile_certified_100": certified_100,
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "policy_hash": policy_hash(),
        "note": (
            "profile_certification is scored against the detected environment. "
            "UNKNOWN is not BARE_METAL. SOFTWARE_TPM is never L3. "
            "L4 on a VM is NOT_APPLICABLE, not FAIL. CERTIFIED_100 = applicable "
            "PASS / applicable requirements; NOT_APPLICABLE is excluded; "
            "NOT_REACHABLE is not satisfied. L3 is never L4. "
            "LOCAL_GENERATED nonce is not a verifier challenge."
        ),
    }


AWS_IID_CERT_DIR = Path(__file__).resolve().parent / "aws_iid_certs"


def _wrap_pkcs7(raw: str) -> str:
    blob = "".join(str(raw or "").split())
    if "BEGIN" in str(raw or ""):
        return str(raw)
    lines = [blob[i : i + 64] for i in range(0, len(blob), 64)]
    return "-----BEGIN PKCS7-----\n" + "\n".join(lines) + "\n-----END PKCS7-----\n"


def verify_aws_iid_rsa2048_pin(*, document: str, rsa2048_body: str, region: str) -> dict[str, Any]:
    """Pin-verify AWS IID RSA-2048 against the published regional cert.

    This is the procedure AWS documents (`openssl smime -verify -noverify`).
    `-noverify` means the cert is pinned, not walked to a public CA.
    Success is NOT a TPM quote, NOT freshness/challenge, NOT Ed25519 bind,
    and NOT CERTIFIED_100.
    """
    region = str(region or "").strip()
    cert_path = AWS_IID_CERT_DIR / f"{region}-rsa2048.pem"
    if not document.strip() or not str(rsa2048_body or "").strip():
        return {"verified": False, "reason": "missing_document_or_signature", "region": region}
    if not cert_path.is_file():
        return {"verified": False, "reason": "no_pinned_rsa2048_cert", "region": region}
    import tempfile

    wrapped = _wrap_pkcs7(rsa2048_body)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            sig = Path(tmp) / "rsa2048"
            doc = Path(tmp) / "document"
            out = Path(tmp) / "out"
            sig.write_text(wrapped, encoding="utf-8")
            doc.write_text(document, encoding="utf-8")
            proc = subprocess.run(
                [
                    "openssl",
                    "smime",
                    "-verify",
                    "-in",
                    str(sig),
                    "-inform",
                    "PEM",
                    "-content",
                    str(doc),
                    "-certfile",
                    str(cert_path),
                    "-noverify",
                    "-out",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"verified": False, "reason": type(exc).__name__, "region": region}
    ok = proc.returncode == 0
    return {
        "verified": ok,
        "reason": "ok" if ok else ((proc.stderr or proc.stdout or "openssl_failed")[-240:]),
        "region": region,
        "pinned_cert": cert_path.name,
        "note": "AWS-documented pin. Not a CA walk, not a TPM quote, not node-key binding.",
    }


def split_platform_verdicts(
    *,
    overall: str,
    hardware_tpm: str,
    attestation_crypto_verified: bool,
    certified_hardware_identity: bool,
    iid_pin: dict[str, Any] | None = None,
    recast_cloud_as_tpm: bool = False,
    profile_certification: str | None = None,
    l3: str | None = None,
    l4: str | None = None,
    profile_certified_100: bool = False,
) -> dict[str, Any]:
    """Dashboard-safe names. observed PASS ≠ crypto PASS ≠ profile CERTIFIED_100.

    `certification` is the environment-profile result (PASS/PARTIAL/NOT_PROVEN/FAIL),
    not a universal L4 hardware-TPM gate.
    """
    if recast_cloud_as_tpm or (certified_hardware_identity and hardware_tpm != "TPM_HARDWARE_ATTESTED"):
        observed = "FAIL"
        certification = "FAIL"
    elif overall in {"CLOUD_ATTESTED", "TPM_ATTESTED", "VTPM_ATTESTED", "VM_UNATTESTED", "UNKNOWN"}:
        observed = "PASS"
        certification = profile_certification or "NOT_PROVEN"
    else:
        observed = "FAIL"
        certification = "FAIL"
    pin = iid_pin or {}
    if pin.get("verified") is True:
        pin_verdict = "PASS"
    elif pin.get("reason") in {"missing_document_or_signature", "no_pinned_rsa2048_cert", None} and not pin.get("verified"):
        pin_verdict = "NOT_PROVEN"
    elif pin.get("reason") == "not_aws":
        pin_verdict = "NOT_APPLICABLE"
    else:
        pin_verdict = "FAIL" if pin.get("verified") is False and pin.get("reason") not in {
            "missing_document_or_signature",
            "no_pinned_rsa2048_cert",
        } else "NOT_PROVEN"
    return {
        "platform_level_observed": observed,
        "platform_crypto_attestation": "PASS" if attestation_crypto_verified else "NOT_PROVEN",
        "hardware_tpm": hardware_tpm,
        "certification": certification,
        "l3": l3 or "NOT_PROVEN",
        "l4": l4 or ("NOT_APPLICABLE" if hardware_tpm in {"NOT_APPLICABLE", "NOT_AVAILABLE"} else "NOT_PROVEN"),
        "profile_certified_100": bool(profile_certified_100) and certification == "PASS",
        "aws_iid_rsa2048_pin": pin_verdict,
        "note": (
            "platform_level_observed PASS = classification + registry binding, "
            "not a CA-verified attestation. platform_crypto_attestation stays "
            "NOT_PROVEN until a TPM/vTPM quote verifies. aws_iid_rsa2048_pin is "
            "a pin of the AWS IID signature only (no freshness, no Ed25519 bind). "
            "certification is the detected environment profile (L2/L3/L4 as "
            "applicable). L4 on a VM is NOT_APPLICABLE. profile_certified_100 "
            "is 100 % of that profile, not a demand that every node be L4."
        ),
    }


def load_platform_binding_registry() -> dict[str, dict[str, str]]:
    if _binding_override is not None:
        return dict(_binding_override)
    extra = (os.getenv("ARTCB_PLATFORM_BINDING") or "").strip()
    path = Path(extra) if extra else BINDING_REL
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("replicas") if isinstance(payload.get("replicas"), dict) else {}
    out: dict[str, dict[str, str]] = {}
    for nid, raw in rows.items():
        if not isinstance(raw, dict):
            continue
        inst = str(raw.get("provider_instance_id") or "").strip()
        if not inst:
            continue
        out[str(nid)] = {
            "node_id": str(nid),
            "provider": str(raw.get("provider") or ""),
            "provider_instance_id": inst,
            "ipv4": str(raw.get("ipv4") or ""),
            "ed25519_b64": str(raw.get("ed25519_b64") or ""),
        }
    return out


@contextmanager
def override_platform_binding(rows: dict[str, dict[str, str]]) -> Iterator[None]:
    global _binding_override
    prev = _binding_override
    _binding_override = {str(k): dict(v) for k, v in rows.items()}
    try:
        yield
    finally:
        _binding_override = prev


def node_binding_digest(
    *,
    network_id: str,
    node_id: str,
    provider: str,
    provider_instance_id: str,
    attestation_public_key: str,
) -> str:
    raw = "|".join(
        [
            str(network_id or ""),
            str(node_id or ""),
            str(provider or ""),
            str(provider_instance_id or ""),
            str(attestation_public_key or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def lookup_node_by_instance(instance_id: str, registry: dict[str, dict[str, str]] | None = None) -> str:
    needle = str(instance_id or "").strip()
    if not needle:
        return ""
    rows = registry if registry is not None else load_platform_binding_registry()
    for nid, row in rows.items():
        if str(row.get("provider_instance_id") or "").strip() == needle:
            return str(nid)
    return ""


def evaluate_node_platform_binding(
    *,
    declared_node_id: str,
    observed_instance_id: str,
    observed_provider: str,
    attestation_public_key: str = "",
    registry: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Compare declared NodeID with the provider instance. Env cannot rewrite this."""
    rows = registry if registry is not None else load_platform_binding_registry()
    declared = str(declared_node_id or "").strip()
    observed = str(observed_instance_id or "").strip()
    provider = str(observed_provider or "").strip()
    bound = lookup_node_by_instance(observed, rows)
    expected = rows.get(declared) or {}
    expected_id = str(expected.get("provider_instance_id") or "")
    expected_key = str(expected.get("ed25519_b64") or "")
    key = str(attestation_public_key or expected_key)
    mismatch = bool(bound and declared and bound != declared)
    instance_mismatch = bool(declared and expected_id and observed and expected_id != observed)
    key_mismatch = bool(expected_key and key and expected_key != key)
    digest = (
        node_binding_digest(
            network_id=NETWORK_ID,
            node_id=bound or declared,
            provider=provider or str(expected.get("provider") or ""),
            provider_instance_id=observed or expected_id,
            attestation_public_key=key,
        )
        if (observed or expected_id)
        else ""
    )
    verified = bool(observed and bound and not mismatch and not instance_mismatch)
    return {
        "declared_node_id": declared,
        "observed_provider": provider,
        "observed_instance_id": observed,
        "expected_instance_id": expected_id,
        "platform_bound_node_id": bound,
        "identity_mismatch": mismatch or instance_mismatch,
        "key_mismatch": key_mismatch,
        "binding_verified": verified,
        "node_binding": digest,
        "network_id": NETWORK_ID,
        "note": (
            "ARTCB_NODE_ID / official_node are declarative labels. "
            "Provider instance id is the platform identity. "
            "A mismatch is IDENTITY_MISMATCH — do not adopt the env NodeID."
        ),
    }


def _declared_node_and_key() -> tuple[str, str]:
    declared = ""
    key = ""
    try:
        from src.artcb.node_registry import official_replica_id

        declared = official_replica_id() or ""
    except Exception:
        declared = (os.getenv("ARTCB_NODE_ID") or "").strip()
    try:
        from src.artcb.consensus.replica_identity import local_ed25519_b64, local_identity_status

        key = local_ed25519_b64() or ""
        status = local_identity_status()
        env_id = str(status.get("env_node_id") or "")
        file_id = str(status.get("official_node_file") or "")
        # Declared label = env/file (weak). Key owner is a different identity.
        declared = env_id or file_id or declared
    except Exception:
        pass
    return declared, key


def collect_platform_attestation(
    *,
    declared_node_id: str | None = None,
    attestation_public_key: str | None = None,
    tpm: dict[str, Any] | None = None,
    virt: dict[str, Any] | None = None,
    aws: dict[str, Any] | None = None,
    ovh: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tpm = tpm if tpm is not None else tpm_probe()
    virt = virt if virt is not None else virt_probe()
    aws = aws if aws is not None else aws_imds_probe()
    ovh = ovh if ovh is not None else ovh_metadata_probe()
    klass = classify(tpm=tpm, virt=virt, aws=aws, ovh=ovh)
    level = completed_trust_level(klass=klass, tpm=tpm, virt=virt, aws=aws, ovh=ovh)
    hw = hardware_tpm_attestation(klass=klass, tpm=tpm, virt=virt)
    vt = vtpm_attestation(klass=klass, tpm=tpm)
    plat = platform_identity_attestation(aws=aws, ovh=ovh, klass=klass)
    overall = overall_platform_trust(level)
    provider = "aws" if aws.get("document_ok") else ("ovh" if ovh.get("document_ok") else "")
    instance_id = str(aws.get("instance_id") or ovh.get("uuid") or "")
    if declared_node_id is None or attestation_public_key is None:
        auto_id, auto_key = _declared_node_and_key()
        declared = declared_node_id if declared_node_id is not None else auto_id
        pubkey = attestation_public_key if attestation_public_key is not None else auto_key
    else:
        declared = declared_node_id
        pubkey = attestation_public_key
    binding = evaluate_node_platform_binding(
        declared_node_id=declared,
        observed_instance_id=instance_id,
        observed_provider=provider,
        attestation_public_key=pubkey or "",
    )
    extra_hex = str(binding.get("node_binding") or "")
    try:
        digest = bytes.fromhex(extra_hex) if extra_hex else b"\x00" * 16
    except ValueError:
        digest = b"\x00" * 16
    bind16 = digest[:16].ljust(16, b"\x00")[:16]
    freshness_nonce = os.urandom(16)
    extra = bind16 + freshness_nonce
    if not quote_present(tpm):
        from src.artcb.consensus.tpm_quote import attempt_attestation_quote

        tpm = dict(tpm)
        quote = attempt_attestation_quote(extra_data=extra, is_vm=bool(virt.get("is_vm")))
        if quote.get("verified") is True:
            quote = dict(quote)
            quote["freshness_bound"] = True
            quote["freshness_nonce_hex"] = freshness_nonce.hex()
            quote["binding_prefix_hex"] = bind16.hex()
            quote["ek_provenance"] = "LOCAL_CREATEEK"
            quote["ek_manufacturer_verified"] = False
        tpm["quote"] = quote
    tpm = dict(tpm)
    tpm["device_kind"] = classify_tpm_kind(tpm=tpm, virt=virt)
    klass = classify(tpm=tpm, virt=virt, aws=aws, ovh=ovh)
    level = completed_trust_level(klass=klass, tpm=tpm, virt=virt, aws=aws, ovh=ovh)
    hw = hardware_tpm_attestation(klass=klass, tpm=tpm, virt=virt)
    vt = vtpm_attestation(klass=klass, tpm=tpm)
    plat = platform_identity_attestation(aws=aws, ovh=ovh, klass=klass)
    overall = overall_platform_trust(level)
    kind_now = str(tpm.get("device_kind") or "")
    crypto_verified = bool(
        (klass == "tpm_hardware" and quote_present(tpm) and kind_now == KIND_HARDWARE)
        or (klass == "vtpm" and quote_present(tpm) and hypervisor_vtpm_proven(kind_now))
    )
    recast = bool(virt.get("is_vm")) and (overall == "TPM_ATTESTED" or level == TRUST_L4_TPM)
    recast = recast or (level == TRUST_L4_TPM and hw != "TPM_HARDWARE_ATTESTED")
    recast = recast or (overall == "TPM_ATTESTED" and hw in {"NOT_AVAILABLE", "NOT_APPLICABLE"})
    iid_pin: dict[str, Any]
    if aws.get("document_ok"):
        iid_pin = verify_aws_iid_rsa2048_pin(
            document=str(aws.get("_document_raw") or ""),
            rsa2048_body=str(aws.get("_rsa2048_raw") or ""),
            region=str(aws.get("region") or ""),
        )
    else:
        iid_pin = {"verified": False, "reason": "not_aws"}
    public_aws = {k: v for k, v in aws.items() if not str(k).startswith("_")}
    public_aws["rsa2048_pin"] = {
        "verified": bool(iid_pin.get("verified")),
        "reason": iid_pin.get("reason"),
        "region": iid_pin.get("region"),
    }
    policy = evaluate_environment_profile_policy(
        virt=virt,
        tpm=tpm,
        aws=aws,
        ovh=ovh,
        klass=klass,
        level=level,
        binding=binding,
        recast=recast,
        iid_pin=iid_pin,
    )
    splits = split_platform_verdicts(
        overall=overall,
        hardware_tpm=hw,
        attestation_crypto_verified=crypto_verified,
        certified_hardware_identity=level == TRUST_L4_TPM,
        iid_pin=iid_pin,
        recast_cloud_as_tpm=recast,
        profile_certification=str(policy["profile_certification"]),
        l3=str(policy["l3"]),
        l4=str(policy["l4"]),
        profile_certified_100=bool(policy["profile_certified_100"]),
    )
    evidence = {
        "platform_class": klass,
        "trust_level": level,
        "provider": provider,
        "instance_id": instance_id,
        "hardware_tpm_attestation": hw,
        "platform_identity_attestation": plat,
        "overall_platform_trust": overall,
        "environment_profile": policy["environment_profile"],
        "binding": binding.get("node_binding"),
    }
    evidence_hash = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "protocol": "284-environment-classification",
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "policy_hash": policy["policy_hash"],
        "ts_ns": now_wall_ns(),
        "environment": policy["environment"],
        "environment_certainty": policy["environment_certainty"],
        "environment_profile": policy["environment_profile"],
        "tpm_kind": policy["tpm_kind"],
        "maximum_supported_level": policy["maximum_supported_level"],
        "maximum_theoretical_level": policy["maximum_theoretical_level"],
        "maximum_verified_level": policy["maximum_verified_level"],
        "attested_level": policy["attested_level"],
        "missing_requirements": policy["missing_requirements"],
        "freshness_kind": policy["freshness_kind"],
        "quote_signature_verified": policy["quote_signature_verified"],
        "ak_provenance_verified": policy["ak_provenance_verified"],
        "ek_provenance_verified": policy["ek_provenance_verified"],
        "manufacturer_chain_verified": policy["manufacturer_chain_verified"],
        "capabilities": policy["capabilities"],
        "profile_requirements": policy["requirements"],
        "core_requirements": policy["core_requirements"],
        "completeness_requirements": policy["completeness_requirements"],
        "profile_certification": policy["profile_certification"],
        "profile_certified_100": policy["profile_certified_100"],
        "l3": policy["l3"],
        "l4": policy["l4"],
        "quote_freshness": policy["quote_freshness"],
        "ek_ak_provenance": policy["ek_ak_provenance"],
        "quote_node_binding": policy["quote_node_binding"],
        "platform_class": klass,
        "trust_level": level,
        "trust_level_name": {
            4: "L4_TPM_HARDWARE_ATTESTED",
            3: "L3_VTPM_ATTESTED",
            2: "L2_CLOUD_ATTESTED",
            1: "L1_VM_OBSERVED",
            0: "L0_UNATTESTED",
        }.get(level, "L0_UNATTESTED"),
        "provider": provider,
        "attestation_type": (
            "tpm_quote"
            if klass == "tpm_hardware" and quote_present(tpm)
            else (
                "vtpm_quote"
                if klass == "vtpm" and quote_present(tpm)
                else (
                    "aws_instance_identity"
                    if aws.get("document_ok")
                    else ("ovh_openstack_metadata" if ovh.get("document_ok") else "none")
                )
            )
        ),
        "attestation_verified": bool(aws.get("document_ok") or ovh.get("document_ok") or quote_present(tpm)),
        "attestation_crypto_verified": crypto_verified,
        "split_verdicts": splits,
        "hardware_tpm_attestation": hw,
        "vtpm_attestation": vt,
        "platform_identity_attestation": plat,
        "overall_platform_trust": overall,
        "overall_platform_trust_precise": (
            "CLOUD_IDENTITY_OBSERVED" if overall == "CLOUD_ATTESTED" else overall
        ),
        "certified_hardware_identity": (
            level == TRUST_L4_TPM
            and kind_now == KIND_HARDWARE
            and environment_certainty(virt) == "BARE_METAL_PROVEN"
        ),
        "tpm_quote_proven": bool(klass == "tpm_hardware" and quote_present(tpm)),
        "cloud_identity_closest_analog": klass == "cloud_instance_identity" or level == TRUST_L2_CLOUD,
        "bare_metal_tpm_path_implemented": True,
        "identity": {
            "logical_node_id": declared,
            "machine": {
                "hostname": virt.get("hostname"),
                "machine_id": virt.get("machine_id"),
                "dmi_uuid": virt.get("dmi_uuid"),
            },
            "provider": {
                "name": provider,
                "instance_id": instance_id,
                "instance_type": aws.get("instance_type"),
                "region": aws.get("region"),
            },
            "crypto_root": "tpm_ak" if crypto_verified else "none",
        },
        "binding": binding,
        "tpm": tpm,
        "virt": virt,
        "aws_imds": public_aws,
        "ovh_metadata": ovh,
        "nonce": hashlib.sha256(f"{now_wall_ns()}|{instance_id}|{declared}".encode()).hexdigest()[:32],
        "quote_qualifier": {
            "binding_prefix_hex": bind16.hex(),
            "freshness_nonce_hex": freshness_nonce.hex() if quote_present(tpm) and (tpm.get("quote") or {}).get("freshness_bound") else None,
        },
        "evidence_hash": evidence_hash,
        "note": (
            "Policy: environment → capabilities → max level → required evidence → "
            "verify → profile certification. L4 on a VM is NOT_APPLICABLE, not FAIL. "
            "L3 NitroTPM/vTPM is never L4. CLOUD_ATTESTED is not TPM_ATTESTED. "
            "PKCS#7 / OVH metadata signatures are not a TPM quote. "
            "split_verdicts.certification is the detected profile, not a universal "
            "hardware-TPM gate. CERTIFIED_100 is 100 % of that profile (freshness + "
            "EK provenance included for L3/L4). AWS RSA-2048 pin is a sub-verdict only. "
            "Local tpm2_createek is not manufacturer EK provenance."
        ),
    }


def overlay_path() -> Path:
    extra = (os.getenv("ARTCB_REPLICA_OVERLAY") or "").strip()
    return Path(extra) if extra else Path("/etc/artcb/replica_overlay.json")
