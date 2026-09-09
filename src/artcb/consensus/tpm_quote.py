"""TPM/vTPM quote — fail-closed. Never invent a signature.

On a VM, /dev/tpm0 is a vTPM (or NitroTPM). That is L3, never L4.
Bare-metal /dev/tpm0 is L4 only after a verified quote.

Guest swtpm without a hypervisor device is NOT this module's live path.
DEVICE_ABSENT is the honest result on the current four official VMs.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

PCR_SELECTION = "sha256:0,1,7"
STATE_DEFAULT = Path("/var/lib/artcb/node/tpm")


def tpm_device_present() -> bool:
    return Path("/dev/tpm0").exists() or Path("/dev/tpmrm0").exists()


def state_dir() -> Path:
    extra = (os.getenv("ARTCB_TPM_STATE") or "").strip()
    return Path(extra) if extra else STATE_DEFAULT


def _run(args: list[str], timeout: int = 15, cwd: Path | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": type(exc).__name__, "stdout": "", "stderr": "", "rc": -1}
    return {
        "ok": proc.returncode == 0,
        "rc": proc.returncode,
        "stdout": (proc.stdout or "")[-800:],
        "stderr": (proc.stderr or "")[-400:],
    }


def _which(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def attempt_attestation_quote(*, extra_data: bytes, is_vm: bool) -> dict[str, Any]:
    """Produce and verify a TPM2 quote. extra_data is the anti-replay qualifier (≤32 bytes)."""
    kind = "vtpm" if is_vm else "tpm_hardware"
    if not tpm_device_present():
        return {
            "verified": False,
            "ok": False,
            "reason": "DEVICE_ABSENT",
            "kind": kind,
            "quote": None,
            "note": (
                "No /dev/tpm0 on this machine. OVH Public Cloud does not expose "
                "hypervisor vTPM. AWS NitroTPM requires RegisterImage boot-mode=uefi "
                "tpm-support=v2.0 then a new launch; it cannot be toggled on a "
                "running instance. Do not recast cloud identity or guest swtpm "
                "as a TPM quote."
            ),
        }
    if not _which("tpm2_quote") or not _which("tpm2_checkquote"):
        return {
            "verified": False,
            "ok": False,
            "reason": "TOOLS_MISSING",
            "kind": kind,
            "quote": None,
            "note": "tpm2-tools required for quote + checkquote",
        }
    qualifier = (extra_data or b"")[:32].ljust(32, b"\x00")
    qhex = qualifier.hex()
    root = state_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"verified": False, "ok": False, "reason": f"STATE_UNWRITABLE:{type(exc).__name__}", "kind": kind, "quote": None}

    ak_ctx = root / "ak.ctx"
    ak_pub = root / "ak.pub"
    ek_ctx = root / "ek.ctx"
    if not ak_ctx.is_file() or not ak_pub.is_file():
        ek = _run(["tpm2_createek", "-c", str(ek_ctx), "-G", "rsa"], cwd=root)
        if not ek["ok"]:
            return {"verified": False, "ok": False, "reason": "EK_CREATE_FAILED", "kind": kind, "detail": ek.get("stderr"), "quote": None}
        ak = _run(
            ["tpm2_createak", "-C", str(ek_ctx), "-c", str(ak_ctx), "-G", "rsa", "-u", str(ak_pub), "-n", str(root / "ak.name")],
            cwd=root,
        )
        if not ak["ok"]:
            return {"verified": False, "ok": False, "reason": "AK_CREATE_FAILED", "kind": kind, "detail": ak.get("stderr"), "quote": None}

    msg = root / "quote.msg"
    sig = root / "quote.sig"
    pcr = root / "quote.pcr"
    quoted = _run(
        [
            "tpm2_quote",
            "-c",
            str(ak_ctx),
            "-l",
            PCR_SELECTION,
            "-q",
            qhex,
            "-m",
            str(msg),
            "-s",
            str(sig),
            "-o",
            str(pcr),
            "-g",
            "sha256",
        ],
        cwd=root,
    )
    if not quoted["ok"]:
        return {"verified": False, "ok": False, "reason": "QUOTE_FAILED", "kind": kind, "detail": quoted.get("stderr"), "quote": None}

    check = _run(
        [
            "tpm2_checkquote",
            "-u",
            str(ak_pub),
            "-m",
            str(msg),
            "-s",
            str(sig),
            "-f",
            str(pcr),
            "-g",
            "sha256",
            "-q",
            qhex,
        ],
        cwd=root,
    )
    if not check["ok"]:
        return {"verified": False, "ok": False, "reason": "QUOTE_VERIFY_FAILED", "kind": kind, "detail": check.get("stderr"), "quote": None}

    pcrs = _run(["tpm2_pcrread", PCR_SELECTION], cwd=root)
    return {
        "verified": True,
        "ok": True,
        "reason": "ok",
        "kind": kind,
        "pcr_selection": PCR_SELECTION,
        "qualifier_sha256": qhex if len(qhex) == 64 else None,
        "ak_pub_bytes": ak_pub.stat().st_size if ak_pub.is_file() else 0,
        "pcrs_ok": bool(pcrs.get("ok")),
        "quote": {
            "msg_bytes": msg.stat().st_size if msg.is_file() else 0,
            "sig_bytes": sig.stat().st_size if sig.is_file() else 0,
        },
        "note": "Verified TPM2 quote. VM device is vTPM (L3), not hardware TPM (L4).",
    }
