"""Liaison wallet ↔ appareil client — un seul wallet par empreinte navigateur (anti-fraude).

Protocole :
  À la création d'un wallet (POST /wallet/create ou biométrie), l'empreinte
  **client** est enregistrée dans data/wallet_device_bindings.json :
    sha256(User-Agent | X-ARTCB-Device-Id)[:32]

  R345 (2026-09-14T17:20:00Z): ~~machine hôte serveur (DeviceIdentity)~~ barré pour
  le multi-utilisateur public — un seul wallet `cursor-cloud-agent` sur ovh-node-1
  bloquait TOUTES les créations classiques sur artcb.me.

  Si une deuxième tentative de création de wallet provient du même fingerprint
  client, elle est rejetée avec HTTP 409 ``device_wallet_limit``.

  Exceptions :
    - ARTCB_ALLOW_MULTI_WALLET=true  : désactive le check (dev/tests uniquement)
    - wallet_name == "default"        : toujours autorisé (migration)
    - Le nœud bootstrap (N1/N2)       : exemption par ARTCB_BOOTSTRAP_NODE=true

  Ce n'est PAS HumanIdentity / UNIQUE_HUMAN. WebAuthn ≠ unicité mondiale.
  Couches : voir ``src/artcb/identity/layers.py`` (R347) — Node ≠ User ≠ DeviceHost ≠ DeviceClient.

Référence : rapport 114 — 2026-08-07 ; R345 client-scope
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("artcb.security.wallet_device_binding")


class WalletDeviceBindingError(Exception):
    """Levée quand un wallet existe déjà pour cet appareil."""


class WalletDeviceBindingStore:
    """Registre des liaisons wallet ↔ fingerprint d'appareil."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "wallet_device_bindings.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write(self, records: list[dict]) -> None:
        self.path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.path.chmod(0o600)

    def check_and_bind(
        self,
        *,
        wallet_name: str,
        device_fingerprint: str,
        env_type: str = "unknown",
    ) -> None:
        """
        Vérifie qu'aucun wallet n'existe déjà pour ce fingerprint d'appareil.
        Si OK, enregistre la liaison.

        Lève WalletDeviceBindingError si déjà enregistré.
        Ne fait rien si ARTCB_ALLOW_MULTI_WALLET=true (mode dev/tests).
        """
        # Mode dev/tests : désactiver le check
        if os.getenv("ARTCB_ALLOW_MULTI_WALLET", "").lower() in ("true", "1", "yes"):
            logger.debug("wallet_device_binding: check skipped (ARTCB_ALLOW_MULTI_WALLET=true)")
            return

        # Nœud bootstrap : exemption
        if os.getenv("ARTCB_BOOTSTRAP_NODE", "").lower() in ("true", "1", "yes"):
            logger.debug("wallet_device_binding: check skipped (ARTCB_BOOTSTRAP_NODE=true)")
            return

        records = self._read()
        existing = next((r for r in records if r["device_fingerprint"] == device_fingerprint), None)

        if existing:
            raise WalletDeviceBindingError(
                f"Un wallet '{existing['wallet_name']}' a déjà été créé sur cet appareil "
                f"(fingerprint: {device_fingerprint[:16]}…). "
                "Un seul wallet est autorisé par appareil pour prévenir la fraude. "
                "Si vous avez perdu votre accès, utilisez votre seed_hex pour le récupérer."
            )

        # Enregistrer la liaison
        records.append({
            "wallet_name": wallet_name,
            "device_fingerprint": device_fingerprint,
            "env_type": env_type,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        self._write(records)
        logger.info(
            "wallet_device_binding: bound wallet=%s fingerprint=%s... env=%s",
            wallet_name, device_fingerprint[:16], env_type,
        )

    def get_binding(self, device_fingerprint: str) -> dict | None:
        """Retourne la liaison existante pour ce fingerprint, ou None."""
        records = self._read()
        return next((r for r in records if r["device_fingerprint"] == device_fingerprint), None)

    def list_bindings(self) -> list[dict]:
        """Liste toutes les liaisons enregistrées."""
        return self._read()
