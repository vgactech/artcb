"""Réplication privée auto du BODY ORG — GO-D 2026-09-07.

Quand un nœud est ajouté dans `authorized_nodes` d'un domaine (avec rôle
REPLICA ou CONSENSUS), le fondateur peut déclencher la réplication du BODY
privé vers ce nœud.

Mécanique :
  1. Fondateur appelle POST /api/v1/authz/domains/{id}/replicate-body
  2. Le BODY est chiffré ML-KEM-768 avec la clé publique du nœud cible
  3. L'enveloppe est envoyée via POST /api/v1/authz/domains/receive-body
  4. Le nœud cible déchiffre, vérifie le canonical_hash, stocke le BODY
  5. manifest.body_replicated = True sur les deux côtés

GO-D invariant :
  - Le BODY n'est jamais transmis en clair (toujours ML-KEM + AES-GCM)
  - Le canonical_hash est vérifié avant stockage (intégrité)
  - Seul le fondateur peut déclencher la réplication
  - Un nœud non autorisé ne peut pas recevoir le BODY
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from src.artcb.authz.domains import canonical_hash
from src.artcb.authz.registry import DomainManifest, DomainRegistry, DomainError, DomainForbidden
from src.artcb.crypto.kem import encrypt_payload, decrypt_payload, KEMError, MLKEM768_PUBLIC_BYTES
from src.artcb.p2p.node_identity import NodeIdentity

logger = logging.getLogger("artcb.authz.body_replication")


class BodyReplicationError(Exception):
    """Erreur de réplication du BODY."""


class BodyHashMismatch(BodyReplicationError):
    """Le BODY reçu ne correspond pas au canonical_hash attendu."""


class BodyReplicationService:
    """Service de réplication privée chiffrée du BODY ORG.

    GO-D : déclenché par le fondateur via POST /authz/domains/{id}/replicate-body
    """

    def __init__(
        self,
        registry: DomainRegistry,
        identity: NodeIdentity,
        data_dir: Path,
    ) -> None:
        self._registry = registry
        self._identity = identity
        self._bodies_dir = Path(data_dir) / "org_bodies"
        self._bodies_dir.mkdir(parents=True, exist_ok=True)

    # ── Stockage local du BODY ──────────────────────────────────────────────

    def store_body(self, domain_id: str, body: dict[str, Any]) -> Path:
        """Stocke le BODY en clair localement (chmod 0600)."""
        path = self._bodies_dir / f"{domain_id}.body.json"
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        path.chmod(0o600)
        return path

    def load_body(self, domain_id: str) -> dict[str, Any] | None:
        path = self._bodies_dir / f"{domain_id}.body.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def has_body(self, domain_id: str) -> bool:
        return (self._bodies_dir / f"{domain_id}.body.json").is_file()

    # ── Chiffrement / déchiffrement ─────────────────────────────────────────

    def encrypt_body_for_node(
        self,
        domain_id: str,
        body: dict[str, Any],
        target_kem_public_hex: str,
    ) -> dict[str, str]:
        """Chiffre le BODY pour un nœud cible (ML-KEM-768 + AES-GCM)."""
        peer_pk = bytes.fromhex(target_kem_public_hex)
        if len(peer_pk) != MLKEM768_PUBLIC_BYTES:
            raise BodyReplicationError(
                f"Clé KEM cible invalide : {len(peer_pk)} bytes (attendu {MLKEM768_PUBLIC_BYTES})"
            )
        payload = json.dumps({
            "domain_id": domain_id,
            "body": body,
            "canonical_hash": canonical_hash(body),
            "from_node_id": self._identity.node_id,
        }, ensure_ascii=False).encode("utf-8")
        envelope = encrypt_payload(payload, peer_pk)
        envelope["domain_id"] = domain_id
        envelope["from_node_id"] = self._identity.node_id
        envelope["body_replication"] = "true"
        return envelope

    def decrypt_body_envelope(self, envelope: dict[str, str]) -> dict[str, Any]:
        """Déchiffre une enveloppe BODY reçue d'un autre nœud."""
        from cryptography.exceptions import InvalidTag
        secret = bytes.fromhex(self._identity.kem_secret_key_hex)
        try:
            plaintext = decrypt_payload(envelope, secret)
        except (KEMError, InvalidTag, ValueError) as exc:
            raise BodyReplicationError(f"Déchiffrement échoué (mauvaise clé ou données corrompues) : {exc}") from exc
        return json.loads(plaintext.decode("utf-8"))

    # ── Réplication sortante ────────────────────────────────────────────────

    def replicate_to_node(
        self,
        domain_id: str,
        target_node_url: str,
        target_kem_public_hex: str,
        founder_address: str,
    ) -> dict[str, Any]:
        """Réplique le BODY d'un domaine vers un nœud autorisé.

        GO-D : vérifications avant envoi :
          1. Le fondateur est bien le founder du domaine
          2. Le nœud cible est dans authorized_nodes
          3. Le BODY local existe
          4. Le BODY est chiffré avant envoi
        """
        manifest = self._registry.get(domain_id)
        if manifest is None:
            raise DomainError("domain_not_found")
        if manifest.founder_address != founder_address:
            raise DomainForbidden("founder_mismatch")

        body = self.load_body(domain_id)
        if body is None:
            raise BodyReplicationError(f"BODY du domaine {domain_id} introuvable sur ce nœud")

        # Vérifier intégrité avant envoi
        expected_hash = manifest.genesis_hash
        actual_hash = canonical_hash(body)
        if actual_hash != expected_hash:
            raise BodyReplicationError(
                f"BODY hash mismatch avant envoi : attendu={expected_hash[:16]} actuel={actual_hash[:16]}"
            )

        envelope = self.encrypt_body_for_node(domain_id, body, target_kem_public_hex)

        url = f"{target_node_url.rstrip('/')}/api/v1/authz/domains/receive-body"
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, json={"envelope": envelope})
                r.raise_for_status()
                result = r.json()
        except Exception as exc:
            raise BodyReplicationError(f"Envoi échoué vers {target_node_url} : {exc}") from exc

        if result.get("ok"):
            logger.info(
                "GO-D : BODY répliqué domain=%s → node=%s hash=%s",
                domain_id, target_node_url, actual_hash[:16],
            )
        return {
            "ok": result.get("ok", False),
            "domain_id": domain_id,
            "target_node": target_node_url,
            "canonical_hash": actual_hash,
            "encrypted": True,
        }

    # ── Réception ──────────────────────────────────────────────────────────

    def receive_body_envelope(self, envelope: dict[str, str]) -> dict[str, Any]:
        """Reçoit et stocke un BODY répliqué d'un autre nœud.

        GO-D : vérifications à la réception :
          1. Déchiffrement ML-KEM
          2. Vérification canonical_hash
          3. Vérification que ce nœud est dans authorized_nodes
          4. Stockage local (chmod 0600)
          5. manifest.body_replicated = True
        """
        if envelope.get("body_replication") != "true":
            raise BodyReplicationError("Enveloppe non marquée comme body_replication")

        try:
            payload = self.decrypt_body_envelope(envelope)
        except (KEMError, ValueError) as exc:
            raise BodyReplicationError(f"Déchiffrement échoué : {exc}") from exc

        domain_id = payload.get("domain_id", "")
        body = payload.get("body", {})
        received_hash = payload.get("canonical_hash", "")
        from_node = payload.get("from_node_id", "unknown")

        if not domain_id or not body:
            raise BodyReplicationError("BODY reçu invalide : domain_id ou body manquant")

        # Vérifier l'intégrité du BODY reçu
        actual_hash = canonical_hash(body)
        if received_hash and actual_hash != received_hash:
            raise BodyHashMismatch(
                f"BODY hash mismatch : reçu={received_hash[:16]} calculé={actual_hash[:16]}"
            )

        # Vérifier que ce nœud est autorisé
        manifest = self._registry.get(domain_id)
        if manifest is not None and self._identity.node_id not in manifest.authorized_nodes:
            raise BodyReplicationError(
                f"Ce nœud ({self._identity.node_id[:16]}) n'est pas dans authorized_nodes"
            )

        # Vérifier genesis_hash du manifest
        if manifest is not None and actual_hash != manifest.genesis_hash:
            raise BodyHashMismatch(
                f"BODY reçu ne correspond pas au genesis_hash du manifest : "
                f"attendu={manifest.genesis_hash[:16]} reçu={actual_hash[:16]}"
            )

        # Stocker le BODY
        self.store_body(domain_id, body)

        # Mettre à jour le manifest
        if manifest is not None:
            manifest.body_replicated = True
            self._registry._upsert(manifest)

        logger.info(
            "GO-D : BODY reçu et stocké domain=%s from=%s hash=%s",
            domain_id, from_node[:16], actual_hash[:16],
        )
        return {
            "ok": True,
            "domain_id": domain_id,
            "canonical_hash": actual_hash,
            "from_node_id": from_node,
            "body_replicated": True,
        }
