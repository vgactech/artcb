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
    - wallet_namespace == "TEST"      : un device TEST peut porter plusieurs wallets TEST
      (rapport 354 §9 + rapport 355 §22–§23). La VALIDATION reste active ;
      seul le binding « 1 wallet par device » est relaxé dans le namespace TEST.
      Les wallets TEST sont stockés dans test_wallet_device_bindings.json (registre séparé).

  Ce n'est PAS HumanIdentity / UNIQUE_HUMAN. WebAuthn ≠ unicité mondiale.
  Couches : voir ``src/artcb/identity/layers.py`` (R347) — Node ≠ User ≠ DeviceHost ≠ DeviceClient.

Référence : rapport 114 — 2026-08-07 ; R345 client-scope ; R357 TEST namespace
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


def is_test_wallet_name(wallet_name: str) -> bool:
    """Return True if the wallet name belongs to the TEST namespace.

    TEST wallets are identified by the artcbdev prefix in their address,
    or by a name starting with 'test_' / 'artcbdev' (convention).
    """
    return (
        wallet_name.startswith("artcbdev")
        or wallet_name.startswith("test_")
        or wallet_name.startswith("TEST-WALLET")
    )


class WalletDeviceBindingStore:
    """Registre des liaisons wallet ↔ fingerprint d'appareil.

    Two separate registries are maintained:
      - wallet_device_bindings.json      → PRODUCTION wallets (1 per device enforced)
      - test_wallet_device_bindings.json → TEST wallets (multiple per device allowed)

    Both use the SAME validation logic; the TEST registry relaxes only the
    "1 wallet per fingerprint" constraint (rapport 354 §9, rapport 355 §22).
    """

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "wallet_device_bindings.json"
        self.test_path = Path(data_dir) / "test_wallet_device_bindings.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])
        if not self.test_path.is_file():
            self._write_test([])

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

    def _read_test(self) -> list[dict]:
        try:
            return json.loads(self.test_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write_test(self, records: list[dict]) -> None:
        self.test_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.test_path.chmod(0o600)

    def check_and_bind(
        self,
        *,
        wallet_name: str,
        device_fingerprint: str,
        env_type: str = "unknown",
        wallet_namespace: str = "PRODUCTION",
    ) -> None:
        """Vérifie et enregistre la liaison wallet ↔ fingerprint d'appareil.

        Pour le namespace TEST (wallet_namespace="TEST") :
          - Plusieurs wallets TEST peuvent coexister sur le même device.
          - Le binding est enregistré dans test_wallet_device_bindings.json.
          - LA VALIDATION RESTE ACTIVE (pas de skip_validation).
          - Voir rapport 354 §9, rapport 355 §22–§23.

        Pour PRODUCTION :
          - Comportement inchangé : 1 wallet par fingerprint.
          - Exceptions ARTCB_ALLOW_MULTI_WALLET et ARTCB_BOOTSTRAP_NODE conservées.

        Lève WalletDeviceBindingError si la contrainte est violée.
        """
        # Routing vers le registre TEST
        if wallet_namespace == "TEST" or is_test_wallet_name(wallet_name):
            self._check_and_bind_test(
                wallet_name=wallet_name,
                device_fingerprint=device_fingerprint,
                env_type=env_type,
            )
            return

        # ── PRODUCTION path (comportement original) ──────────────────────────
        if os.getenv("ARTCB_ALLOW_MULTI_WALLET", "").lower() in ("true", "1", "yes"):
            logger.debug("wallet_device_binding: check skipped (ARTCB_ALLOW_MULTI_WALLET=true)")
            return

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

        records.append({
            "wallet_name": wallet_name,
            "device_fingerprint": device_fingerprint,
            "env_type": env_type,
            "namespace": "PRODUCTION",
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        self._write(records)
        logger.info(
            "wallet_device_binding: bound wallet=%s fingerprint=%s... env=%s",
            wallet_name, device_fingerprint[:16], env_type,
        )

    def _check_and_bind_test(
        self,
        *,
        wallet_name: str,
        device_fingerprint: str,
        env_type: str = "unknown",
    ) -> None:
        """Register a TEST wallet binding (multiple per device allowed).

        Validation engine is NOT bypassed — this only relaxes the 1-per-device limit.
        Records are stored in test_wallet_device_bindings.json (separate from PROD).
        """
        records = self._read_test()
        # In TEST namespace: same wallet_name must not be re-bound to a different device
        existing = next((r for r in records if r["wallet_name"] == wallet_name), None)
        if existing and existing["device_fingerprint"] != device_fingerprint:
            raise WalletDeviceBindingError(
                f"TEST wallet '{wallet_name}' est déjà lié à un autre appareil "
                f"(fingerprint: {existing['device_fingerprint'][:16]}…). "
                "Le même nom de wallet TEST ne peut pas être re-lié à un device différent."
            )
        records.append({
            "wallet_name": wallet_name,
            "device_fingerprint": device_fingerprint,
            "env_type": env_type,
            "namespace": "TEST",
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        self._write_test(records)
        logger.info(
            "wallet_device_binding[TEST]: bound wallet=%s fingerprint=%s... env=%s",
            wallet_name, device_fingerprint[:16], env_type,
        )

    def get_binding(self, device_fingerprint: str) -> dict | None:
        """Retourne la liaison PRODUCTION existante pour ce fingerprint, ou None."""
        records = self._read()
        return next((r for r in records if r["device_fingerprint"] == device_fingerprint), None)

    def get_test_binding(self, wallet_name: str) -> dict | None:
        """Retourne la liaison TEST existante pour ce wallet_name, ou None."""
        records = self._read_test()
        return next((r for r in records if r["wallet_name"] == wallet_name), None)

    def list_bindings(self) -> list[dict]:
        """Liste toutes les liaisons PRODUCTION enregistrées."""
        return self._read()

    def list_test_bindings(self) -> list[dict]:
        """Liste toutes les liaisons TEST enregistrées."""
        return self._read_test()
