"""Hardware identity — empreinte machine unique pour anti-fraude (1 wallet / appareil).

Architecture :
  NIVEAU 1 — machine-id Linux / Windows / macOS (sans TPM, universel)
  NIVEAU 2 — TPM 2.0 EK Certificate (si disponible — preuve constructeur)
  NIVEAU 3 — Android SIM ICCID / iOS DeviceCheck (mobile, futur)

Objectif : empêcher un utilisateur de créer plusieurs wallets sur un même appareil
en identifiant de façon unique chaque machine hôte, sans exposer de données personnelles.

L'empreinte matérielle (device_fingerprint) est :
  - un hash SHA-256 des identifiants stables de la machine
  - non réversible (on ne peut pas retrouver les données source depuis le hash)
  - différent selon l'environnement (local, Replit, VPS, Android)
  - stocké dans data/node_device.json à la première utilisation

Référence : rapport 114 — 2026-08-07
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.security.hardware_identity")


# ---------------------------------------------------------------------------
# Dataclass de résultat
# ---------------------------------------------------------------------------

@dataclass
class DeviceIdentity:
    """Identité unique d'un appareil/nœud."""

    device_fingerprint: str       # SHA-256(identifiants stables) — 64 hex chars
    machine_id: str | None        # /etc/machine-id ou équivalent OS
    hostname: str                 # hostname machine
    platform_system: str          # Linux / Windows / macOS / Android
    tpm_available: bool           # True si TPM 2.0 accessible
    tpm_ek_cert_hash: str | None  # SHA-256 du certificat EK TPM (si dispo)
    tpm_manufacturer: str | None  # Nuvoton / Infineon / STM / etc.
    env_type: str                 # local | replit | docker | vps | unknown
    created_at: str               # ISO timestamp
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_fingerprint": self.device_fingerprint,
            "machine_id": self.machine_id,
            "hostname": self.hostname,
            "platform_system": self.platform_system,
            "tpm_available": self.tpm_available,
            "tpm_ek_cert_hash": self.tpm_ek_cert_hash,
            "tpm_manufacturer": self.tpm_manufacturer,
            "env_type": self.env_type,
            "created_at": self.created_at,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeviceIdentity:
        return cls(
            device_fingerprint=data["device_fingerprint"],
            machine_id=data.get("machine_id"),
            hostname=data.get("hostname", ""),
            platform_system=data.get("platform_system", ""),
            tpm_available=data.get("tpm_available", False),
            tpm_ek_cert_hash=data.get("tpm_ek_cert_hash"),
            tpm_manufacturer=data.get("tpm_manufacturer"),
            env_type=data.get("env_type", "unknown"),
            created_at=data.get("created_at", ""),
            extra=data.get("extra", {}),
        )


# ---------------------------------------------------------------------------
# Lecture machine-id (multi-OS)
# ---------------------------------------------------------------------------

def _read_machine_id() -> str | None:
    """Lit l'identifiant machine stable selon l'OS."""
    # Linux
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            val = Path(path).read_text().strip()
            if val:
                return val
        except OSError:
            pass
    # macOS
    try:
        out = subprocess.check_output(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            timeout=3, stderr=subprocess.DEVNULL,
        ).decode()
        for line in out.splitlines():
            if "IOPlatformUUID" in line:
                return line.split('"')[-2]
    except Exception:
        pass
    # Windows
    try:
        out = subprocess.check_output(
            ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
            timeout=3, stderr=subprocess.DEVNULL,
        ).decode()
        return out.strip().split()[-1]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Détection environnement
# ---------------------------------------------------------------------------

def _read_sys_text(path: str) -> str | None:
    try:
        val = Path(path).read_text(encoding="utf-8", errors="replace").strip()
        return val or None
    except OSError:
        return None


# Expert levels A–E. Never invent a chip, vTPM, TEE or HSM that is not there.
# A = physical TPM on a real machine (bare metal). B = virtual TPM on a VM.
# C = TEE (SEV/SGX/TDX) without a TPM. D = external HSM. E = software hash only.
HARDWARE_ASSURANCE_LEVELS: dict[str, dict[str, str]] = {
    "A": {
        "kind": "physical_tpm",
        "fr": "TPM physique sur serveur/PC réel (pas une VM).",
    },
    "B": {
        "kind": "virtual_tpm",
        "fr": "TPM émulé par l’hyperviseur (vTPM / NitroTPM) : /dev/tpm0 existe ET la machine est virtuelle.",
    },
    "C": {
        "kind": "tee",
        "fr": "Enclave TEE (SEV / SGX / TDX) détectée, sans TPM.",
    },
    "D": {
        "kind": "hsm",
        "fr": "HSM externe/cloud (OKMS, CloudHSM) — pas de TPM local.",
    },
    "E": {
        "kind": "software",
        "fr": "Empreinte logicielle (machine-id + instance cloud hashés). Pas de puce.",
    },
}

_VIRT_VENDORS = (
    "qemu",
    "kvm",
    "xen",
    "vmware",
    "virtualbox",
    "bochs",
    "bhyve",
    "amazon",
    "amazon ec2",
    "microsoft corporation",
    "google",
    "openstack",
    "digitalocean",
)
_VIRT_PRODUCTS = (
    "openstack",
    "nova",
    "droplet",
    "hvm domu",
    "virtual machine",
    "kvm",
    "t3.",
    "t2.",
    "m6i.",
    "c6i.",
    "c5.",
    "t3a.",
)


def tpm_sysfs_facts() -> dict[str, Any]:
    """Honest TPM presence. Never reports a chip that is not there."""
    present = Path("/dev/tpm0").exists() or Path("/sys/class/tpm/tpm0").is_dir()
    rm = Path("/dev/tpmrm0").exists()
    version = _read_sys_text("/sys/class/tpm/tpm0/tpm_version_major")
    return {
        "tpm_device_present": present,
        "tpm_resource_manager": rm,
        "tpm_version_major": version,
    }


def virtualization_facts() -> dict[str, Any]:
    """Is this a VM? systemd-detect-virt + DMI. Never upgrades a VM to bare metal."""
    vendor = (_read_sys_text("/sys/class/dmi/id/sys_vendor") or "").strip()
    product = (_read_sys_text("/sys/class/dmi/id/product_name") or "").strip()
    chassis = _read_sys_text("/sys/class/dmi/id/chassis_type")
    virt_tech: str | None = None
    try:
        out = subprocess.check_output(
            ["systemd-detect-virt"],
            timeout=2,
            stderr=subprocess.DEVNULL,
        ).decode().strip().lower()
        if out and out not in {"none"}:
            virt_tech = out
    except Exception:
        virt_tech = None
    vl = vendor.lower()
    pl = product.lower()
    dmi_virtual = any(token in vl for token in _VIRT_VENDORS) or any(
        token in pl for token in _VIRT_PRODUCTS
    )
    # OpenStack / Amazon EC2 are VMs even if vendor string is "OVH" on some images.
    if "openstack" in pl or "nova" in pl or "amazon ec2" in vl:
        dmi_virtual = True
    chassis_virtual = bool(virt_tech) or dmi_virtual
    return {
        "chassis_virtual": chassis_virtual,
        "virt_tech": virt_tech,
        "sys_vendor": vendor or None,
        "product_name": product or None,
        "chassis_type": chassis,
    }


def tee_facts() -> dict[str, Any]:
    """TEE devices only if the file exists. Never invent SEV / SGX / Nitro."""
    sev = Path("/dev/sev").exists() or Path("/dev/sev-guest").exists()
    sgx = Path("/dev/sgx_enclave").exists()
    tdx = Path("/dev/tdx_guest").exists()
    nitro = Path("/dev/nitro_enclaves").exists()
    kind = None
    if sev:
        kind = "sev"
    elif tdx:
        kind = "tdx"
    elif sgx:
        kind = "sgx"
    elif nitro:
        kind = "nitro_enclaves"
    return {
        "tee_detected": kind is not None,
        "tee_kind": kind,
        "sev_dev": sev,
        "sgx_dev": sgx,
        "tdx_dev": tdx,
        "nitro_enclaves_dev": nitro,
    }


def hsm_binding_facts() -> dict[str, Any]:
    """External HSM only if the operator bound one. Env flag, not a guess."""
    raw = (os.getenv("ARTCB_HSM_BINDING") or "").strip()
    bound = raw.lower() in {"1", "true", "yes", "on"} or bool(raw and raw.lower() not in {"0", "false", "no", "off"})
    kind = None
    if bound:
        kind = raw if raw.lower() not in {"1", "true", "yes", "on"} else "configured"
    return {"hsm_bound": bound, "hsm_kind": kind}


def probe_tpm2_tools() -> dict[str, Any]:
    """tpm2-tools + PCR0 only when /dev/tpm0 exists. Never fake a PCR."""
    tpm = tpm_sysfs_facts()
    pcrread = _which("tpm2_pcrread")
    getek = _which("tpm2_getekcertificate")
    getcap = _which("tpm2_getcap")
    out: dict[str, Any] = {
        "tpm2_pcrread": pcrread,
        "tpm2_getekcertificate": getek,
        "tpm2_getcap": getcap,
        "pcr0_sha256": None,
        "pcr_probed": False,
    }
    if not tpm["tpm_device_present"]:
        out["note"] = "no /dev/tpm0 — PCR not probed"
        return out
    if not pcrread:
        out["note"] = "tpm2_pcrread absent"
        return out
    try:
        result = subprocess.run(
            [pcrread, "sha256:0"],
            timeout=5,
            capture_output=True,
            text=True,
        )
        out["pcr_probed"] = True
        if result.returncode == 0:
            for line in (result.stdout or "").splitlines():
                hexpart = "".join(ch for ch in line.strip() if ch in "0123456789abcdefABCDEF")
                if len(hexpart) == 64:
                    out["pcr0_sha256"] = hexpart.lower()
                    break
    except Exception as exc:
        out["note"] = f"pcr_read_failed:{type(exc).__name__}"
    return out


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


def classify_hardware_assurance(
    *,
    tpm_device_present: bool,
    chassis_virtual: bool,
    tee_kind: str | None = None,
    hsm_bound: bool = False,
) -> dict[str, Any]:
    """Map measured facts to A–E. Absent chip ⇒ not A/B. VM + no TPM ⇒ E."""
    if tpm_device_present and not chassis_virtual:
        level = "A"
    elif tpm_device_present and chassis_virtual:
        level = "B"
    elif tee_kind:
        level = "C"
    elif hsm_bound:
        level = "D"
    else:
        level = "E"
    meta = HARDWARE_ASSURANCE_LEVELS[level]
    tpm_kind = "absent"
    if tpm_device_present:
        tpm_kind = "virtual" if chassis_virtual else "physical"
    return {
        "hardware_assurance_level": level,
        "hardware_kind": meta["kind"],
        "hardware_assurance_fr": meta["fr"],
        "tpm_kind": tpm_kind,
        "invented": False,
    }


def _hash_id(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_imds_instance_id() -> str | None:
    """Local cloud metadata only (this machine). Never from register-public."""
    if os.getenv("ARTCB_SKIP_CLOUD_METADATA", "").lower() in {"1", "true", "yes", "on"}:
        return None
    try:
        req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=0.4) as resp:
            val = resp.read().decode("utf-8", errors="replace").strip()
            return val or None
    except Exception:
        return None


def cloud_instance_binding() -> dict[str, Any]:
    """Bind the VM without faking a TPM. Hashes only — no raw UUIDs on the wire."""
    instance_id = _read_sys_text("/var/lib/cloud/data/instance-id")
    dmi_uuid = None
    for path in (
        "/sys/class/dmi/id/product_uuid",
        "/sys/devices/virtual/dmi/id/product_uuid",
    ):
        dmi_uuid = _read_sys_text(path)
        if dmi_uuid:
            break
    asset = _read_sys_text("/sys/class/dmi/id/board_asset_tag")
    product = (_read_sys_text("/sys/class/dmi/id/product_name") or "").lower()
    bios = (_read_sys_text("/sys/class/dmi/id/sys_vendor") or "").lower()
    if not instance_id:
        instance_id = _read_imds_instance_id()
    provider = "unknown"
    if "amazon" in bios or "ec2" in product or (instance_id or "").startswith("i-"):
        provider = "aws"
    elif "ovh" in bios or "openstack" in product or "ovh" in (asset or "").lower():
        provider = "ovh"
    elif os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL"):
        provider = "replit"
    binding_raw = "|".join(
        part for part in (provider, instance_id or "", dmi_uuid or "", asset or "") if part
    )
    return {
        "provider": provider,
        "instance_id_hash": _hash_id(instance_id),
        "dmi_product_uuid_hash": _hash_id(dmi_uuid),
        "board_asset_tag_hash": _hash_id(asset),
        "binding_hash": _hash_id(binding_raw) if binding_raw else None,
    }


def _detect_env_type() -> str:
    """Détecte l'environnement d'exécution."""
    # Replit : variable d'environnement REPL_ID ou REPLIT_DB_URL
    if os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL") or os.getenv("REPL_SLUG"):
        return "replit"
    # Docker : présence de /.dockerenv
    if Path("/.dockerenv").exists():
        return "docker"
    # GitHub Actions
    if os.getenv("GITHUB_ACTIONS") == "true":
        return "github_actions"
    # Indicateur VPS : pas d'écran, pas de bureau
    if not os.getenv("DISPLAY") and platform.system() == "Linux":
        # Peut être un VPS — on ne peut pas être certain
        return "linux_headless"
    return "local"


# ---------------------------------------------------------------------------
# Lecture TPM EK Certificate (Niveau 2)
# ---------------------------------------------------------------------------

def _read_tpm_ek_cert() -> tuple[str | None, str | None]:
    """
    Tente de lire le certificat EK du TPM 2.0.
    Retourne (cert_hash_sha256, manufacturer_string) ou (None, None).

    Nécessite : tpm2-tools installé, accès /dev/tpmrm0 (groupe tss).
    """
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".der", delete=False) as tf:
            tmp_path = tf.name

        result = subprocess.run(
            ["tpm2_getekcertificate", "-o", tmp_path],
            timeout=5,
            capture_output=True,
        )
        if result.returncode != 0:
            logger.debug("tpm2_getekcertificate failed: %s", result.stderr.decode()[:200])
            return None, None

        cert_bytes = Path(tmp_path).read_bytes()
        Path(tmp_path).unlink(missing_ok=True)

        cert_hash = hashlib.sha256(cert_bytes).hexdigest()

        # Extraire le fabricant via openssl
        manufacturer = None
        try:
            openssl_out = subprocess.check_output(
                ["openssl", "x509", "-inform", "DER", "-in", tmp_path, "-subject", "-noout"],
                timeout=3, stderr=subprocess.DEVNULL,
            ).decode()
            # Chercher O=Nuvoton / O=Infineon / O=STMicroelectronics
            for part in openssl_out.split(","):
                if "O=" in part and ("Nuvoton" in part or "Infineon" in part or "STM" in part
                                      or "AMD" in part or "Intel" in part):
                    manufacturer = part.strip().replace("O=", "")
                    break
        except Exception:
            pass

        logger.info("TPM EK cert found, hash=%s..., manufacturer=%s", cert_hash[:16], manufacturer)
        return cert_hash, manufacturer

    except FileNotFoundError:
        logger.debug("tpm2_getekcertificate not found — TPM tools not installed")
    except Exception as exc:
        logger.debug("TPM EK cert read failed: %s", exc)

    return None, None


# ---------------------------------------------------------------------------
# Calcul du fingerprint
# ---------------------------------------------------------------------------

def compute_device_fingerprint(
    *,
    machine_id: str | None,
    hostname: str,
    platform_system: str,
    tpm_ek_cert_hash: str | None,
    env_type: str,
    extra_entropy: str = "",
) -> str:
    """
    Calcule le fingerprint SHA-256 de l'appareil.

    Basé sur des identifiants stables, non réversibles.
    Ordre de priorité :
      1. TPM EK cert hash (le plus fort — lié au hardware)
      2. machine-id OS (stable mais copiable)
      3. hostname + platform + MAC address hash
    """
    parts: list[str] = []

    # Priorité 1 : TPM (non copiable)
    if tpm_ek_cert_hash:
        parts.append(f"tpm:{tpm_ek_cert_hash}")

    # Priorité 2 : machine-id OS
    if machine_id:
        parts.append(f"mid:{machine_id}")

    # Priorité 3 : hostname + platform
    parts.append(f"host:{hostname}")
    parts.append(f"sys:{platform_system}")

    # MAC address (stable sur réseau fixe)
    try:
        mac = hex(uuid.getnode())
        parts.append(f"mac:{mac}")
    except Exception:
        pass

    # Entropie additionnelle optionnelle (ex: REPL_ID sur Replit)
    if extra_entropy:
        parts.append(f"extra:{extra_entropy}")

    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Collecte complète
# ---------------------------------------------------------------------------

def collect_device_identity() -> DeviceIdentity:
    """Collecte l'identité complète de l'appareil courant."""
    machine_id = _read_machine_id()
    hostname = platform.node()
    platform_system = platform.system()
    env_type = _detect_env_type()

    extra_entropy = ""
    if env_type == "replit":
        extra_entropy = os.getenv("REPL_ID", "") + os.getenv("REPL_SLUG", "")
    cloud = cloud_instance_binding()
    if cloud.get("binding_hash"):
        extra_entropy = (extra_entropy + "|" + str(cloud["binding_hash"])).strip("|")

    tpm_facts = tpm_sysfs_facts()
    tpm_ek_cert_hash, tpm_manufacturer = _read_tpm_ek_cert()
    tpm_available = tpm_ek_cert_hash is not None

    fingerprint = compute_device_fingerprint(
        machine_id=machine_id,
        hostname=hostname,
        platform_system=platform_system,
        tpm_ek_cert_hash=tpm_ek_cert_hash,
        env_type=env_type,
        extra_entropy=extra_entropy,
    )

    virt = virtualization_facts()
    tee = tee_facts()
    hsm = hsm_binding_facts()
    grade = classify_hardware_assurance(
        tpm_device_present=bool(tpm_facts["tpm_device_present"]),
        chassis_virtual=bool(virt["chassis_virtual"]),
        tee_kind=tee.get("tee_kind"),
        hsm_bound=bool(hsm["hsm_bound"]),
    )
    extra: dict[str, Any] = {
        "tpm_device_present": tpm_facts["tpm_device_present"],
        "tpm_resource_manager": tpm_facts["tpm_resource_manager"],
        "tpm_version_major": tpm_facts["tpm_version_major"],
        "tpm_attestation": (
            "ek_cert"
            if tpm_ek_cert_hash
            else ("device_present_no_ek" if tpm_facts["tpm_device_present"] else "absent")
        ),
        "cloud_provider": cloud.get("provider"),
        "instance_id_hash": cloud.get("instance_id_hash"),
        "dmi_product_uuid_hash": cloud.get("dmi_product_uuid_hash"),
        "binding_hash": cloud.get("binding_hash"),
        "machine_id_hash": _hash_id(machine_id),
        "hardware_assurance_level": grade["hardware_assurance_level"],
        "hardware_kind": grade["hardware_kind"],
        "tpm_kind": grade["tpm_kind"],
        "chassis_virtual": virt["chassis_virtual"],
        "virt_tech": virt.get("virt_tech"),
        "tee_detected": tee["tee_detected"],
        "tee_kind": tee.get("tee_kind"),
        "hsm_bound": hsm["hsm_bound"],
    }
    if env_type == "replit":
        extra["repl_id"] = os.getenv("REPL_ID", "")
        extra["repl_slug"] = os.getenv("REPL_SLUG", "")
    if env_type == "github_actions":
        extra["github_repo"] = os.getenv("GITHUB_REPOSITORY", "")
        extra["github_run_id"] = os.getenv("GITHUB_RUN_ID", "")

    return DeviceIdentity(
        device_fingerprint=fingerprint,
        machine_id=machine_id,
        hostname=hostname,
        platform_system=platform_system,
        tpm_available=tpm_available,
        tpm_ek_cert_hash=tpm_ek_cert_hash,
        tpm_manufacturer=tpm_manufacturer,
        env_type=env_type,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        extra=extra,
    )


# ---------------------------------------------------------------------------
# Stockage persistant
# ---------------------------------------------------------------------------

class DeviceIdentityStore:
    """Persiste l'identité de l'appareil dans data/node_device.json."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "node_device.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_or_create(self) -> DeviceIdentity:
        """Charge l'identité si elle existe, sinon la crée et la persiste."""
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                identity = DeviceIdentity.from_dict(data)
                logger.debug("Loaded device identity fingerprint=%s...", identity.device_fingerprint[:16])
                return identity
            except Exception as exc:
                logger.warning("Corrupted device identity file, regenerating: %s", exc)

        identity = collect_device_identity()
        self._save(identity)
        logger.info(
            "Created device identity fingerprint=%s... env=%s tpm=%s",
            identity.device_fingerprint[:16],
            identity.env_type,
            identity.tpm_available,
        )
        return identity

    def _save(self, identity: DeviceIdentity) -> None:
        self.path.write_text(
            json.dumps(identity.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.path.chmod(0o600)

    def get_fingerprint(self) -> str:
        return self.load_or_create().device_fingerprint


def public_machine_view(identity: DeviceIdentity | None = None) -> dict[str, Any]:
    """Public health block. Live TPM sysfs; stored fingerprint; no raw machine-id."""
    facts = tpm_sysfs_facts()
    extra = dict(identity.extra) if identity is not None else {}
    tpm_present = bool(facts["tpm_device_present"])
    ek = identity.tpm_ek_cert_hash if identity is not None else None
    attestation = (
        "ek_cert"
        if ek
        else ("device_present_no_ek" if tpm_present else "absent")
    )
    prefix = (identity.device_fingerprint[:16] if identity else "")
    live_cloud = extra.get("binding_hash") and extra.get("cloud_provider")
    if not live_cloud:
        live_cloud = cloud_instance_binding()
    else:
        live_cloud = {
            "provider": extra.get("cloud_provider"),
            "binding_hash": extra.get("binding_hash"),
        }
    virt = virtualization_facts()
    tee = tee_facts()
    hsm = hsm_binding_facts()
    grade = classify_hardware_assurance(
        tpm_device_present=tpm_present,
        chassis_virtual=bool(virt["chassis_virtual"]),
        tee_kind=tee.get("tee_kind"),
        hsm_bound=bool(hsm["hsm_bound"]),
    )
    tools = probe_tpm2_tools()
    note = (
        "Niveaux A–E : A TPM physique, B vTPM, C TEE, D HSM, E logiciel. "
        "On n’invente pas NitroTPM/SEV si /dev/tpm0 est absent. "
        f"Niveau mesuré ici : {grade['hardware_assurance_level']} ({grade['hardware_kind']})."
    )
    return {
        "tpm_device_present": tpm_present,
        "tpm_resource_manager": bool(facts["tpm_resource_manager"]),
        "tpm_version_major": facts["tpm_version_major"],
        "tpm_attestation": attestation,
        "tpm_available": bool(identity.tpm_available) if identity else False,
        "tpm_kind": grade["tpm_kind"],
        "hardware_assurance_level": grade["hardware_assurance_level"],
        "hardware_kind": grade["hardware_kind"],
        "hardware_assurance_fr": grade["hardware_assurance_fr"],
        "chassis_virtual": virt["chassis_virtual"],
        "virt_tech": virt.get("virt_tech"),
        "tee_detected": tee["tee_detected"],
        "tee_kind": tee.get("tee_kind"),
        "hsm_bound": hsm["hsm_bound"],
        "tpm2_tools_present": bool(tools.get("tpm2_pcrread") or tools.get("tpm2_getekcertificate")),
        "pcr0_sha256": tools.get("pcr0_sha256"),
        "env_type": identity.env_type if identity else _detect_env_type(),
        "platform_system": identity.platform_system if identity else platform.system(),
        "cloud_provider": extra.get("cloud_provider") or live_cloud.get("provider"),
        "binding_hash": extra.get("binding_hash") or live_cloud.get("binding_hash"),
        "machine_id_hash": extra.get("machine_id_hash") or _hash_id(identity.machine_id if identity else None),
        "device_fingerprint_prefix": prefix,
        "note": note,
    }
