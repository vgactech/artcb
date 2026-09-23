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

  Namespace selection rule (R358 audit §5):
    Le namespace est TOUJOURS déterminé par le paramètre ``wallet_namespace`` fourni
    explicitement par l'appelant. ``is_test_wallet_name()`` est une fonction utilitaire
    d'information uniquement — elle n'influence PLUS le routage de sécurité.
    Raison : un champ de présentation (nom) ne doit jamais sélectionner implicitement
    une politique de sécurité différente.

  Idempotence (R358 audit §6):
    bind(wallet_name, device_fingerprint) appelé plusieurs fois avec les mêmes arguments
    est idempotent : aucun doublon n'est ajouté dans le registre.

  Ce n'est PAS HumanIdentity / UNIQUE_HUMAN. WebAuthn ≠ unicité mondiale.
  Couches : voir ``src/artcb/identity/layers.py`` (R347) — Node ≠ User ≠ DeviceHost ≠ DeviceClient.

Référence : rapport 114 — 2026-08-07 ; R345 client-scope ; R357 TEST namespace ; R358 fixes
"""

from __future__ import annotations
MODULE_VERSION = '1.3.1'  # R433 — verrou transactionnel + élimination DELETE legacy + forensic enchaîné

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("artcb.security.wallet_device_binding")


# ── R431 — État d'un binding ──────────────────────────────────────────────────

class BindingState:
    """Constantes d'état pour un binding wallet ↔ device (R431)."""
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class BindingRevocationError(Exception):
    """Levée quand la révocation d'un binding échoue (ex. déjà révoqué, introuvable)."""


class BindingPurgeError(Exception):
    """Levée quand une purge physique échoue (R432 — chemin distinct de la révocation)."""


class BindingLegacyDeleteError(BindingPurgeError):
    """Levée quand une suppression directe R379 est appelée (R433 — chemin supprimé).

    Les anciens endpoints DELETE /fingerprint, /wallet, /test/wallet ont été éliminés.
    Utiliser POST /revoke puis POST /purge.
    """


class WalletDeviceBindingError(Exception):
    """Levée quand un wallet existe déjà pour cet appareil."""


def is_test_wallet_name(wallet_name: str) -> bool:
    """Informational helper — return True if the name looks like a TEST wallet.

    IMPORTANT (R358): This function is for logging/UI display only.
    It does NOT influence security routing in check_and_bind().
    Namespace selection is always driven by the explicit ``wallet_namespace``
    parameter — never by wallet_name inference.
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

    # ── R433 — Verrou transactionnel (READ→CAS→WRITE sous fcntl.LOCK_EX) ─────

    @staticmethod
    @contextlib.contextmanager
    def _transactional_lock(target: Path):
        """Context manager : verrou exclusif POSIX sur <target>.lock.

        Le verrou est pris sur un fichier .lock DÉDIÉ (distinct du .tmp) afin
        que le READ, la sélection, le CAS et le WRITE soient tous sous le même
        verrou exclusif. Le verrou est relâché à la sortie du bloc.

        Garantie : deux processus concurrents ne peuvent pas exécuter la
        séquence READ→mutate→WRITE simultanément sur le même registre.

        Note : sur Windows fcntl est absent → best-effort (pas de verrou).
        """
        lock_path = target.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fh = lock_path.open("a")
        try:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_EX)
            except (AttributeError, OSError):
                pass  # Non-POSIX — best effort
            yield
        finally:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
            except (AttributeError, OSError):
                pass
            lock_fh.close()

    @staticmethod
    def _write_atomic(target: Path, records: list[dict]) -> None:
        """Écriture atomique : tmp → fsync → rename (R432/R433).

        Doit être appelée DEPUIS l'intérieur d'un bloc _transactional_lock()
        pour que le READ et le WRITE soient sérialisés ensemble.
        """
        tmp = target.with_suffix(".tmp")
        payload = json.dumps(records, indent=2, ensure_ascii=False).encode("utf-8")
        with tmp.open("wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.rename(target)
        try:
            target.chmod(0o600)
        except OSError:
            pass

    # ── Lecture/écriture non-transactionnelle (liste seule, sans mutation) ────

    def _read(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write(self, records: list[dict]) -> None:
        self._write_atomic(self.path, records)

    def _read_test(self) -> list[dict]:
        try:
            return json.loads(self.test_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write_test(self, records: list[dict]) -> None:
        self._write_atomic(self.test_path, records)

    def check_and_bind(
        self,
        *,
        wallet_name: str,
        device_fingerprint: str,
        env_type: str = "unknown",
        wallet_namespace: str = "PRODUCTION",
    ) -> None:
        """Vérifie et enregistre la liaison wallet ↔ fingerprint d'appareil.

        Le namespace est déterminé UNIQUEMENT par ``wallet_namespace`` (R358 §5).
        ``is_test_wallet_name()`` n'influe PAS sur le routage de sécurité.

        Pour le namespace TEST (wallet_namespace="TEST") :
          - Plusieurs wallets TEST peuvent coexister sur le même device.
          - Le binding est enregistré dans test_wallet_device_bindings.json.
          - Idempotent : bind(A,X)+bind(A,X) = un seul enregistrement (R358 §6).
          - LA VALIDATION RESTE ACTIVE (pas de skip_validation).
          - Voir rapport 354 §9, rapport 355 §22–§23.

        Pour PRODUCTION :
          - Comportement inchangé : 1 wallet par fingerprint.
          - Idempotent : bind(A,X) déjà existant → no-op (pas d'erreur, pas de doublon).
          - Exceptions ARTCB_ALLOW_MULTI_WALLET et ARTCB_BOOTSTRAP_NODE conservées.

        Lève WalletDeviceBindingError si la contrainte de sécurité est violée
        (device déjà lié à un autre wallet).
        """
        # R358: routing par paramètre UNIQUEMENT, jamais par wallet_name
        if wallet_namespace == "TEST":
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

        with self._transactional_lock(self.path):
            records = self._read()
            # R431: seuls les bindings ACTIVE bloquent la création (les REVOKED sont ignorés)
            existing = next(
                (r for r in records
                 if r["device_fingerprint"] == device_fingerprint
                 and r.get("state", BindingState.ACTIVE) == BindingState.ACTIVE),
                None,
            )

            if existing:
                if existing["wallet_name"] == wallet_name:
                    # R358 idempotence: same wallet+device already bound → no-op
                    logger.debug(
                        "wallet_device_binding: already bound wallet=%s fingerprint=%s... (idempotent)",
                        wallet_name, device_fingerprint[:16],
                    )
                    return
                raise WalletDeviceBindingError(
                    f"Un wallet '{existing['wallet_name']}' a déjà été créé sur cet appareil "
                    f"(fingerprint: {device_fingerprint[:16]}…). "
                    "Un seul wallet est autorisé par appareil pour prévenir la fraude. "
                    "Si vous avez perdu votre accès, utilisez votre seed_hex pour le récupérer."
                )

            records.append({
                "binding_id": str(uuid.uuid4()),
                "wallet_name": wallet_name,
                "device_fingerprint": device_fingerprint,
                "env_type": env_type,
                "namespace": "PRODUCTION",
                "state": BindingState.ACTIVE,
                "version": 1,
                "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "revoked_at": None,
                "revocation_reason": None,
                "revocation_actor": None,
                "requested_actor": None,
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
        with self._transactional_lock(self.test_path):
            records = self._read_test()
            # Find the most recent binding for this (wallet_name, device_fingerprint) pair
            existing_same_pair = next(
                (r for r in records
                 if r["wallet_name"] == wallet_name and r["device_fingerprint"] == device_fingerprint),
                None,
            )
            if existing_same_pair:
                # R358 idempotence: exact same pair already recorded → no-op, no duplicate
                logger.debug(
                    "wallet_device_binding[TEST]: already bound wallet=%s fingerprint=%s... (idempotent)",
                    wallet_name, device_fingerprint[:16],
                )
                return

            existing_other_device = next(
                (r for r in records
                 if r["wallet_name"] == wallet_name and r["device_fingerprint"] != device_fingerprint),
                None,
            )
            if existing_other_device:
                raise WalletDeviceBindingError(
                    f"TEST wallet '{wallet_name}' est déjà lié à un autre appareil "
                    f"(fingerprint: {existing_other_device['device_fingerprint'][:16]}…). "
                    "Le même nom de wallet TEST ne peut pas être re-lié à un device différent."
                )
            records.append({
                "binding_id": str(uuid.uuid4()),
                "wallet_name": wallet_name,
                "device_fingerprint": device_fingerprint,
                "env_type": env_type,
                "namespace": "TEST",
                "state": BindingState.ACTIVE,
                "version": 1,
                "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "revoked_at": None,
                "revocation_reason": None,
                "revocation_actor": None,
                "requested_actor": None,
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

    # ── R433 — Suppression directe R379 éliminée (BindingLegacyDeleteError) ──

    def admin_revoke_by_fingerprint(self, device_fingerprint: str) -> dict | None:  # noqa: ARG002
        """[R433 — ÉLIMINÉ] Suppression directe R379 non autorisée.

        Utiliser POST /api/v1/admin/device-binding/revoke (R431/R432) puis
        POST /api/v1/admin/device-binding/purge (R432) si une purge physique
        est nécessaire.
        """
        raise BindingLegacyDeleteError(
            "admin_revoke_by_fingerprint() est éliminé (R433). "
            "Utiliser revoke_with_history() + purge_binding() à la place."
        )

    def admin_revoke_by_wallet(self, wallet_name: str) -> dict | None:  # noqa: ARG002
        """[R433 — ÉLIMINÉ] Suppression directe R379 non autorisée.

        Utiliser POST /api/v1/admin/device-binding/revoke (R431/R432) puis
        POST /api/v1/admin/device-binding/purge (R432) si une purge physique
        est nécessaire.
        """
        raise BindingLegacyDeleteError(
            "admin_revoke_by_wallet() est éliminé (R433). "
            "Utiliser revoke_with_history() + purge_binding() à la place."
        )

    def admin_revoke_test_by_wallet(self, wallet_name: str) -> dict | None:  # noqa: ARG002
        """[R433 — ÉLIMINÉ] Suppression directe R379 non autorisée.

        Utiliser POST /api/v1/admin/device-binding/revoke (R431/R432) puis
        POST /api/v1/admin/device-binding/purge (R432) si une purge physique
        est nécessaire.
        """
        raise BindingLegacyDeleteError(
            "admin_revoke_test_by_wallet() est éliminé (R433). "
            "Utiliser revoke_with_history() + purge_binding() à la place."
        )

    # ── R431/R433 — Révocation avec historique conservé (verrou transactionnel)

    def revoke_with_history(
        self,
        *,
        wallet_name: str | None = None,
        device_fingerprint: str | None = None,
        binding_id: str | None = None,
        reason: str = "",
        authenticated_actor: str = "operator",
        requested_actor: str | None = None,
        namespace: str = "PRODUCTION",
        expected_version: int | None = None,
    ) -> dict:
        """Révoque un binding en conservant l'historique (R433 — verrou transactionnel).

        La révocation change l'état de ACTIVE → REVOKED.
        L'enregistrement N'EST PAS supprimé du registre — audit trail permanent.

        R433 : le READ, le CAS et le WRITE sont TOUS sous _transactional_lock(),
        éliminant la fenêtre de lost-update de R432.

        Paramètres :
          - authenticated_actor : identité vérifiée par le mécanisme d'auth serveur.
            Ce champ est la preuve forensic — il ne vient jamais du body client.
          - requested_actor     : valeur fournie par le body client (optionnelle, informative).
          - expected_version    : si fourni, vérifie que le binding est au numéro de version
            attendu avant d'écrire (Compare-And-Swap) — refuse si divergence.
          - binding_id          : sélection prioritaire (UUID).
          - wallet_name         : sélection secondaire.
          - device_fingerprint  : sélection tertiaire.

        Règles :
          - Seuls les bindings ACTIVE peuvent être révoqués.
          - Binding déjà REVOKED → BindingRevocationError (double révocation, HTTP 409).
          - Binding introuvable → BindingRevocationError (HTTP 404).
          - Si expected_version est fourni et ne correspond pas → BindingRevocationError (HTTP 409).
          - READ+CAS+WRITE sous fcntl.LOCK_EX (R433) — protection lost-update.

        Retourne : snapshot avant, enregistrement final, version, revoked_at, binding_id.
        """
        if not any([wallet_name, device_fingerprint, binding_id]):
            raise BindingRevocationError(
                "Au moins un critère est requis : binding_id, wallet_name ou device_fingerprint."
            )

        is_test = namespace == "TEST"
        registry_path = self.test_path if is_test else self.path

        previous_snapshot: dict = {}
        revoked_record: dict = {}
        now_str = ""
        current_version = 1
        resolved_binding_id: str | None = None

        with self._transactional_lock(registry_path):
            records = self._read_test() if is_test else self._read()

            # Sélection du binding cible (binding_id prioritaire, puis wallet_name, puis fp)
            target_idx = None
            for i, r in enumerate(records):
                match = False
                if binding_id and r.get("binding_id") == binding_id:
                    match = True
                elif wallet_name and r.get("wallet_name") == wallet_name:
                    match = True
                elif device_fingerprint and r.get("device_fingerprint") == device_fingerprint:
                    match = True
                if match:
                    target_idx = i
                    break

            if target_idx is None:
                raise BindingRevocationError(
                    f"Binding introuvable (namespace={namespace}, "
                    f"wallet={wallet_name}, fp={device_fingerprint}, id={binding_id})."
                )

            target = records[target_idx]
            current_state = target.get("state", BindingState.ACTIVE)

            if current_state == BindingState.REVOKED:
                raise BindingRevocationError(
                    f"Binding déjà révoqué (binding_id={target.get('binding_id')}, "
                    f"wallet={target.get('wallet_name')}, revoked_at={target.get('revoked_at')})."
                )

            # R432/R433 — Compare-And-Swap sur version
            current_version = target.get("version", 1)
            if expected_version is not None and expected_version != current_version:
                raise BindingRevocationError(
                    f"Conflit de version (CAS) : attendu v{expected_version}, "
                    f"actuel v{current_version} pour binding_id={target.get('binding_id')}."
                )

            # Snapshot avant révocation
            previous_snapshot = dict(target)
            resolved_binding_id = target.get("binding_id")

            # Mutation → REVOKED avec incrément de version
            now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            records[target_idx] = {
                **target,
                "state": BindingState.REVOKED,
                "version": current_version + 1,
                "revoked_at": now_str,
                "revocation_reason": reason or None,
                "revocation_actor": authenticated_actor,   # identité serveur vérifiée
                "requested_actor": requested_actor,         # champ fourni par le client, informatif
            }
            revoked_record = records[target_idx]

            if is_test:
                self._write_test(records)
            else:
                self._write(records)
        # fin du verrou transactionnel

        logger.warning(
            "wallet_device_binding: R433 REVOKE_WITH_HISTORY namespace=%s "
            "binding_id=%s wallet=%s fp=%s... authenticated_actor=%s "
            "requested_actor=%s reason=%s v%s→v%s",
            namespace,
            resolved_binding_id or "?",
            previous_snapshot.get("wallet_name", "?"),
            str(previous_snapshot.get("device_fingerprint", "?"))[:16],
            authenticated_actor,
            requested_actor or "<none>",
            reason or "<none>",
            current_version,
            current_version + 1,
        )

        return {
            "previous_state": previous_snapshot,
            "new_state": revoked_record,
            "revoked_at": now_str,
            "binding_id": resolved_binding_id,
            "version_before": current_version,
            "version_after": current_version + 1,
        }

    def get_binding_by_id(self, binding_id: str, *, namespace: str = "PRODUCTION") -> dict | None:
        """Retourne un binding par son binding_id (R431/R432), ACTIVE ou REVOKED, ou None."""
        records = self._read_test() if namespace == "TEST" else self._read()
        return next((r for r in records if r.get("binding_id") == binding_id), None)

    def list_active_bindings(self, *, namespace: str = "PRODUCTION") -> list[dict]:
        """Liste uniquement les bindings ACTIVE (R431) pour le namespace donné."""
        records = self._read_test() if namespace == "TEST" else self._read()
        return [r for r in records if r.get("state", BindingState.ACTIVE) == BindingState.ACTIVE]

    def list_revoked_bindings(self, *, namespace: str = "PRODUCTION") -> list[dict]:
        """Liste uniquement les bindings REVOKED (R431) pour le namespace donné."""
        records = self._read_test() if namespace == "TEST" else self._read()
        return [r for r in records if r.get("state", BindingState.ACTIVE) == BindingState.REVOKED]

    # ── R432/R433 — Purge physique (verrou transactionnel + journal forensic) ─

    def purge_binding(
        self,
        *,
        binding_id: str,
        authenticated_actor: str,
        purge_reason: str,
        namespace: str = "PRODUCTION",
    ) -> dict:
        """Purge physique d'un binding REVOKED (R433 — verrou transactionnel).

        Règles :
          - Seuls les bindings à l'état REVOKED peuvent être purgés.
          - Un binding ACTIVE ne peut PAS être purgé directement : révoquer d'abord.
          - La purge supprime physiquement l'enregistrement du registre JSON.
          - Un journal forensic enchaîné (hash_prev) est écrit avant la suppression.
          - binding_id est obligatoire pour la purge (identification précise).
          - authenticated_actor et purge_reason sont obligatoires.
          - READ+vérification+WRITE sous _transactional_lock() (R433).

        Lève BindingPurgeError si :
          - binding_id introuvable
          - état != REVOKED (binding encore ACTIVE)
          - actor ou reason manquants
        """
        if not binding_id:
            raise BindingPurgeError("binding_id est obligatoire pour la purge.")
        if not authenticated_actor or not purge_reason:
            raise BindingPurgeError("authenticated_actor et purge_reason sont obligatoires.")

        is_test = namespace == "TEST"
        registry_path = self.test_path if is_test else self.path

        purge_entry: dict = {}

        with self._transactional_lock(registry_path):
            records = self._read_test() if is_test else self._read()

            target = next((r for r in records if r.get("binding_id") == binding_id), None)
            if target is None:
                raise BindingPurgeError(
                    f"Binding introuvable pour purge (binding_id={binding_id}, namespace={namespace})."
                )

            current_state = target.get("state", BindingState.ACTIVE)
            if current_state != BindingState.REVOKED:
                raise BindingPurgeError(
                    f"La purge est réservée aux bindings REVOKED. "
                    f"État actuel : {current_state} (binding_id={binding_id}). "
                    "Révoquer le binding avant de le purger."
                )

            # Journal forensic AVANT la suppression physique (R433 enchaîné)
            now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            purge_entry = {
                "purge_id": str(uuid.uuid4()),
                "binding_id": binding_id,
                "namespace": namespace,
                "purged_at": now_str,
                "authenticated_actor": authenticated_actor,
                "purge_reason": purge_reason,
                "snapshot": dict(target),
            }
            self._append_purge_log(purge_entry)

            # Suppression physique
            updated = [r for r in records if r.get("binding_id") != binding_id]
            if is_test:
                self._write_test(updated)
            else:
                self._write(updated)
        # fin du verrou transactionnel

        logger.warning(
            "wallet_device_binding: R433 PURGE_PHYSICAL binding_id=%s "
            "namespace=%s actor=%s reason=%s purge_id=%s",
            binding_id, namespace, authenticated_actor,
            purge_reason, purge_entry["purge_id"],
        )
        return purge_entry

    def _append_purge_log(self, entry: dict) -> None:
        """Ajoute une entrée au journal forensic enchaîné (R433 — hash_prev).

        Chaque entrée contient :
          - hash_prev : sha256 de l'entrée précédente en JSON compact (ou "genesis")
          - entry_hash : sha256 de cette entrée en JSON compact

        La chaîne hash_prev→entry_hash rend toute altération rétroactive détectable.
        La liste JSON complète est réécrite atomiquement (R432 _write_atomic).
        """
        log_path = self.path.parent / "binding_purge_log.json"

        with self._transactional_lock(log_path):
            try:
                existing = json.loads(log_path.read_text(encoding="utf-8")) if log_path.is_file() else []
            except Exception:
                existing = []

            # R433 — hash_prev = entry_hash de la dernière entrée stockée, ou "genesis"
            # entry_hash d'une entrée = sha256 de cette entrée (sans entry_hash lui-même).
            # hash_prev d'une nouvelle entrée = entry_hash de l'entrée précédente.
            # Ainsi : hash_prev[n] == entry_hash[n-1] est l'invariant de la chaîne.
            if existing:
                hash_prev = existing[-1].get("entry_hash", "genesis")
            else:
                hash_prev = "genesis"

            # Calcul de entry_hash sur l'entrée enrichie (hash_prev inclus, entry_hash absent)
            entry_with_chain = {**entry, "hash_prev": hash_prev}
            entry_raw = json.dumps(entry_with_chain, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            entry_hash = hashlib.sha256(entry_raw.encode("utf-8")).hexdigest()
            entry_with_chain["entry_hash"] = entry_hash

            existing.append(entry_with_chain)
            self._write_atomic(log_path, existing)

    def list_purge_log(self) -> list[dict]:
        """Retourne le journal forensic de toutes les purges physiques (R432)."""
        log_path = self.path.parent / "binding_purge_log.json"
        try:
            return json.loads(log_path.read_text(encoding="utf-8")) if log_path.is_file() else []
        except Exception:
            return []
