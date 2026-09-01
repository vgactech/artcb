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
    return {
        "tpm_device_present": tpm_present,
        "tpm_resource_manager": bool(facts["tpm_resource_manager"]),
        "tpm_version_major": facts["tpm_version_major"],
        "tpm_attestation": attestation,
        "tpm_available": bool(identity.tpm_available) if identity else False,
        "env_type": identity.env_type if identity else _detect_env_type(),
        "platform_system": identity.platform_system if identity else platform.system(),
        "cloud_provider": extra.get("cloud_provider") or cloud_instance_binding().get("provider"),
        "binding_hash": extra.get("binding_hash"),
        "machine_id_hash": extra.get("machine_id_hash"),
        "device_fingerprint_prefix": prefix,
        "note": (
            "TPM is a physical chip. Cloud VMs here have none — that is reported "
            "honestly. Binding is hashed machine-id + cloud instance, not a fake TPM."
        ),
    }
