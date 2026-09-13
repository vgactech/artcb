"""R339 — MacHardwareInventory + Hardware Identity v2 (H0–H4).

Extends existing A–E / capability discovery. Does **not** invent TPM/T2/SEP.

Rules:
- Collect **all available** identifiers; missing fields ≠ reject.
- Separate: HardwareProfile vs NodePrivateKey vs NodeIdentity vs Certificate.
- Hash sensitive values before network exposure (serial, UUID, MAC).
- SSD/MAC/RAM = secondary (low stability); board/platform = higher.
- Software NodeKey (Ed25519) + challenge = H1, never H3.
- External non-exportable authenticator = H2 (binding required).
- Native TPM/T2/SEP attested = H3/H4.
- UNSUPPORTED_HARDWARE for native C04 remains honest on MacBookAir7,1.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_NODE_KEY_PATH = Path.home() / ".artcb" / "node_identity_ed25519.key"
DEFAULT_INVENTORY_PATH = Path.home() / ".artcb" / "mac_hardware_inventory.json"

# Stability weights for policy (not for inventing uniqueness)
STABILITY = {
    "platform_uuid": ("high", "medium"),
    "serial": ("high", "medium"),
    "board_id": ("high", "medium_high"),
    "boot_rom": ("high", "medium"),
    "model": ("high", "low"),
    "cpu": ("high", "low"),
    "ram": ("medium", "low"),
    "storage_serial": ("low_medium", "low"),
    "mac": ("low", "low"),
    "tpm_ek": ("very_high", "very_high"),
    "t2_se": ("very_high", "very_high"),
    "external_hw_key": ("very_high", "very_high"),
    "software_node_key": ("variable", "medium"),
}


def _sh(cmd: str, timeout: float = 25.0) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def _ioreg_field(name: str) -> str | None:
    out = _sh(f'ioreg -rd1 -c IOPlatformExpertDevice 2>/dev/null | grep "{name}"')
    # "IOPlatformUUID" = "XXXXXXXX"
    m = re.search(rf'"{re.escape(name)}"\s*=\s*"([^"]+)"', out)
    if m:
        return m.group(1)
    m = re.search(rf"{re.escape(name)}\s*=\s*([^\s]+)", out)
    return m.group(1).strip('"') if m else None


@dataclass
class HardwareEvidence:
    component: str
    value_hash: str | None
    source: str
    stability: str
    confidence: str
    present: bool
    raw_preview: str = ""  # never full serial in logs by default
    ts_ns: int = 0

    def __post_init__(self) -> None:
        if not self.ts_ns:
            self.ts_ns = time.time_ns()


@dataclass
class MacHardwareInventory:
    protocol: str = "r339-mac-hardware-inventory-v1"
    ts_ns: int = 0
    platform: dict[str, Any] = field(default_factory=dict)
    firmware: dict[str, Any] = field(default_factory=dict)
    cpu: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    storage: list[dict[str, Any]] = field(default_factory=list)
    network: list[dict[str, Any]] = field(default_factory=list)
    topology: dict[str, Any] = field(default_factory=dict)
    security: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    fingerprint_v2: str | None = None
    assurance_h: str = "H0"
    assurance_legacy_ae: str = "E"
    native_c04: str = "UNSUPPORTED_HARDWARE"
    notes: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        """Network-safe: hashes only, no raw serial/UUID/MAC."""
        d = asdict(self)
        # strip any accidental raw fields
        for key in ("platform", "firmware", "cpu", "memory"):
            block = d.get(key) or {}
            for k in list(block):
                if k.endswith("_raw") or k in {"serial", "uuid", "mac"}:
                    block.pop(k, None)
        return d


def collect_mac_hardware_inventory() -> MacHardwareInventory:
    inv = MacHardwareInventory(ts_ns=time.time_ns())
    if platform.system() != "Darwin":
        inv.notes.append("not_darwin")
        inv.assurance_h = "H0"
        return inv

    # --- A. Platform ---
    serial = _ioreg_field("IOPlatformSerialNumber")
    uuid_plat = _ioreg_field("IOPlatformUUID")
    board = _sh("sysctl -n hw.model")  # often model; board-id via ioreg
    board_id = _ioreg_field("board-id") or _sh(
        "ioreg -l 2>/dev/null | grep -i 'board-id' | head -1"
    )
    model = _sh("sysctl -n hw.model")
    inv.platform = {
        "vendor": "Apple",
        "model": model or None,
        "arch": platform.machine(),
        "macos": platform.mac_ver()[0],
        "serial_hash": _hash(serial),
        "platform_uuid_hash": _hash(uuid_plat),
        "board_id_hash": _hash(board_id) if board_id else _hash(board),
        "serial_present": bool(serial),
        "uuid_present": bool(uuid_plat),
        "board_present": bool(board_id or board),
    }
    for comp, raw, src in (
        ("serial", serial, "ioreg"),
        ("platform_uuid", uuid_plat, "ioreg"),
        ("board_id", board_id or board, "ioreg/sysctl"),
        ("model", model, "sysctl"),
    ):
        st, conf = STABILITY.get(comp if comp != "platform_uuid" else "platform_uuid", ("medium", "medium"))
        inv.evidence.append(
            asdict(
                HardwareEvidence(
                    component=comp,
                    value_hash=_hash(raw),
                    source=src,
                    stability=st,
                    confidence=conf,
                    present=bool(raw),
                )
            )
        )

    # --- B. Firmware ---
    boot_rom = _sh("system_profiler SPHardwareDataType 2>/dev/null | grep -i 'Boot ROM' | head -1")
    smc = _sh("system_profiler SPHardwareDataType 2>/dev/null | grep -i 'SMC' | head -1")
    inv.firmware = {
        "boot_rom_hash": _hash(boot_rom) if boot_rom else None,
        "smc_hash": _hash(smc) if smc else None,
        "boot_rom_present": bool(boot_rom),
        "smc_present": bool(smc),
    }

    # --- C. CPU ---
    cpu_brand = _sh("sysctl -n machdep.cpu.brand_string")
    inv.cpu = {
        "brand_hash": _hash(cpu_brand),
        "brand_present": bool(cpu_brand),
        "arch": platform.machine(),
        "note": "CPU is characteristic not unique identity",
    }

    # --- D. Memory ---
    mem = _sh("sysctl -n hw.memsize")
    inv.memory = {
        "size_bytes": int(mem) if mem.isdigit() else None,
        "note": "RAM secondary; replacement must not destroy node identity alone",
    }

    # --- E. Storage (hashes only) ---
    disk = _sh("system_profiler SPStorageDataType 2>/dev/null | head -80")
    # Prefer diskutil list for serials when available
    diskutil = _sh("diskutil info disk0 2>/dev/null | egrep -i 'Device / Media Name|Device Identifier|Disk Size|Volume Name' | head -20")
    inv.storage = [
        {
            "index": 0,
            "profile_hash": _hash(diskutil or disk),
            "present": bool(diskutil or disk),
            "note": "storage secondary; SSD replace → revalidation not automatic NEW DEVICE",
        }
    ]

    # --- F. Network ---
    ifconfig = _sh("ifconfig -a 2>/dev/null | egrep '^[a-z]|ether ' | head -60")
    macs = re.findall(r"ether\s+([0-9a-f:]{17})", ifconfig, flags=re.I)
    inv.network = [
        {"type": "iface", "mac_hash": _hash(m), "note": "MAC spoofable complementary signal"}
        for m in macs[:8]
    ]

    # --- G. Topology (USB / Thunderbolt presence — no huge dumps) ---
    usb = _sh("system_profiler SPUSBDataType 2>/dev/null | head -5")
    thunder = _sh("system_profiler SPThunderboltDataType 2>/dev/null | head -5")
    inv.topology = {
        "usb_present": bool(usb),
        "thunderbolt_present": bool(thunder),
        "usb_blob_hash": _hash(usb) if usb else None,
        "thunderbolt_blob_hash": _hash(thunder) if thunder else None,
        "note": "topology descriptive; not RoT",
    }

    # --- H. Security discovery (honest) ---
    apple_silicon = platform.machine() == "arm64"
    spi = _sh("ioreg -l -p IODeviceTree 2>/dev/null | grep -i SPiBridge | head -3")
    t2 = bool(spi) or "T2" in _sh("system_profiler SPiBridgeDataType 2>/dev/null | head -20")
    tpm0 = Path("/dev/tpm0").exists()
    tpmrm = Path("/dev/tpmrm0").exists()
    # Do not invent RoT. Classify kind honestly.
    if tpm0 or tpmrm:
        rot_kind = "TPM"
    elif apple_silicon:
        rot_kind = "APPLE_SE"  # candidate — attestation separate
    elif t2:
        rot_kind = "APPLE_T2"  # not a classic TPM; never recast as TPM
    else:
        rot_kind = "NONE"
    inv.security = {
        "tpm": bool(tpm0 or tpmrm),
        "t2": t2,
        "secure_enclave_native": apple_silicon,  # candidate only on AS — not proven attestation
        "apple_silicon": apple_silicon,
        "tee": False,
        "external_authenticator": False,  # enrollment sets this later
        "native_attestation_proven": False,
        "rot_kind": rot_kind,
        "note": "rot_kind presence ≠ attestation; APPLE_T2 ≠ TPM",
    }

    # Fingerprint v2: only high-stability present hashed fields (order stable)
    parts = [
        inv.platform.get("serial_hash") or "",
        inv.platform.get("platform_uuid_hash") or "",
        inv.platform.get("board_id_hash") or "",
        inv.platform.get("model") or "",
        inv.firmware.get("boot_rom_hash") or "",
        inv.cpu.get("brand_hash") or "",
    ]
    inv.fingerprint_v2 = hashlib.sha256("|".join(parts).encode()).hexdigest()

    # Assurance H
    if inv.security["tpm"] or (inv.security["secure_enclave_native"] and inv.security["native_attestation_proven"]):
        inv.assurance_h = "H3"  # still need crypto path for PASS — mark candidate
        inv.notes.append("native_rot_candidate_attestation_not_proven")
        inv.native_c04 = "NOT_PROVEN"
        inv.assurance_legacy_ae = "A" if inv.security["tpm"] else "E"
    elif t2:
        inv.assurance_h = "H3"  # candidate APPLE_T2 — attestation not proven
        inv.notes.append("t2_candidate_not_attested")
        inv.native_c04 = "NOT_PROVEN"
        inv.assurance_legacy_ae = "E"
    elif inv.platform.get("uuid_present") or inv.platform.get("serial_present"):
        inv.assurance_h = "H1"
        inv.native_c04 = "UNSUPPORTED_HARDWARE"
        inv.assurance_legacy_ae = "E"
        inv.notes.append("software_bound_fingerprint_plus_node_key_eligible")
    else:
        inv.assurance_h = "H0"
        inv.native_c04 = "UNSUPPORTED_HARDWARE"

    # MacBookAir7,1 class: force honesty if no RoT
    if not apple_silicon and not t2 and not (tpm0 or tpmrm):
        if inv.assurance_h.startswith("H3"):
            inv.assurance_h = "H1"
        inv.native_c04 = "UNSUPPORTED_HARDWARE"
        inv.notes.append("no_native_rot_do_not_claim_h3")

    inv.notes.append("missing_identifier_does_not_forbid_enrollment")
    inv.notes.append("100_fingerprints_neq_hardware_attestation")
    return inv


def ensure_node_keypair(path: Path | None = None) -> dict[str, Any]:
    """Ed25519 NodeKey (SSH-like). Private key never returned for network export."""
    dest = path or DEFAULT_NODE_KEY_PATH
    dest.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    created = False
    if dest.is_file():
        seed = dest.read_bytes()[:32]
        sk = SigningKey(seed)
    else:
        sk = SigningKey.generate()
        dest.write_bytes(bytes(sk))
        os.chmod(dest, 0o600)
        created = True
    vk = sk.verify_key
    return {
        "algorithm": "Ed25519",
        "public_key_b64": vk.encode(encoder=Base64Encoder).decode("ascii"),
        "key_path": str(dest),
        "created": created,
        "exportable": True,
        "assurance_if_software": "H1",
        "note": "private key never sent to network; not hardware-bound alone",
    }


def _load_signing_key(path: Path | None = None) -> SigningKey:
    dest = path or DEFAULT_NODE_KEY_PATH
    ensure_node_keypair(dest)
    return SigningKey(dest.read_bytes()[:32])


def sign_node_challenge(challenge: bytes, path: Path | None = None) -> dict[str, Any]:
    """SSH-like challenge-response. Private key never leaves the host."""
    import base64

    keys = ensure_node_keypair(path)
    sk = _load_signing_key(path)
    sig = sk.sign(challenge).signature
    return {
        "algorithm": "Ed25519",
        "public_key_b64": keys["public_key_b64"],
        "challenge_sha256": hashlib.sha256(challenge).hexdigest(),
        "signature_b64": base64.b64encode(sig).decode("ascii"),
        "assurance_ceiling": "H1",
        "proves": "possession_of_node_private_key",
        "does_not_prove": "hardware_root_of_trust",
    }


def build_enrollment_bundle(
    inventory: MacHardwareInventory | None = None,
    *,
    node_key_path: Path | None = None,
) -> dict[str, Any]:
    """Local enrollment package (H1). Does not claim H3 / C04 PASS."""
    inv = inventory or collect_mac_hardware_inventory()
    keys = ensure_node_keypair(node_key_path)
    return {
        "protocol": "r339-node-enrollment-v1",
        "ts_ns": time.time_ns(),
        "hardware": inv.to_public_dict(),
        "node_key": {
            "algorithm": keys["algorithm"],
            "public_key_b64": keys["public_key_b64"],
            "exportable": keys["exportable"],
        },
        "binding": {
            "fingerprint_v2": inv.fingerprint_v2,
            "public_key_b64": keys["public_key_b64"],
            "assurance_h": inv.assurance_h,
            "native_c04": inv.native_c04,
        },
        "policy": {
            "H0": "declared software ids only — limited",
            "H1": "fingerprint + NodeKey + challenge — limited production",
            "H2": "external non-exportable authenticator + Mac binding",
            "H3": "native TPM/T2/SEP attested",
            "H4": "H3 + measured boot / fresh attestation",
            "never": "software_fallback => C04 PASS",
            "ssd_replace": "revalidation_not_automatic_new_device",
            "motherboard_replace": "revalidation_required",
            "reinstall_os": "H1 needs recovery ceremony if software key lost",
        },
        "certified_100": False,
        "c04_pass": False,
    }


def persist_inventory(inv: MacHardwareInventory, path: Path | None = None) -> Path:
    dest = path or DEFAULT_INVENTORY_PATH
    dest.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    dest.write_text(json.dumps(inv.to_public_dict(), indent=2) + "\n", encoding="utf-8")
    os.chmod(dest, 0o600)
    return dest
