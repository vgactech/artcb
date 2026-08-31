"""P2P node identity — ML-KEM keypair persistant.

Option 3 — Identifiant de nœud = adresse wallet ARTCB (rapport 115)
============================================================================
L'identifiant unique du nœud est l'adresse wallet de l'opérateur (artcb1xxx).
Cette adresse est dérivée de la clé publique Ed25519 du wallet (Bech32).

Mode BOOTSTRAP (rapport 118) :
  Si ARTCB_NODE_WALLET_ADDRESS est absent ET qu'aucun node_identity.json
  n'existe encore, le nœud démarre en mode bootstrap avec un node_id temporaire.
  Il expose uniquement les routes /setup/* pour permettre la création du wallet
  de nœud. Une fois POST /setup/init-node appelé, l'adresse est persistée dans
  .node_config et le nœud redémarre avec l'identité définitive.

  bootstrap_node_id = "bootstrap_<hostname_slug>" — JAMAIS propagé au réseau P2P.

Standard post-quantique hybride :
  - Wallet : Ed25519 + ML-DSA-65 (signature hybride)
  - Transport P2P : ML-KEM-768 (chiffrement de transport)
  - Adresse : SHA-256(RIPEMD-160(Ed25519_pubkey + ML-DSA_pubkey)) Bech32
"""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.artcb.crypto.kem import (
    KEMError,
    MLKEM768_PUBLIC_BYTES,
    generate_kem_keypair,
)
from src.artcb.crypto.liboqs_runtime import native_liboqs_available

logger = logging.getLogger("artcb.p2p.node_identity")

NETWORK_ID = "artcb-devnet-1"
DEFAULT_P2P_PORT = int(os.getenv("ARTCB_P2P_PORT", "18444"))

# Fichier local (non committé) où l'adresse wallet est persistée après
# POST /setup/init-node. Lu au démarrage avant les variables d'env.
_NODE_CONFIG_FILENAME = ".node_config"


@dataclass
class NodeIdentity:
    network_id: str
    node_id: str            # Format v3 : adresse wallet artcb1xxx / "bootstrap_<slug>" en mode bootstrap
    kem_public_key_hex: str
    kem_secret_key_hex: str
    api_port: int
    p2p_port: int
    wallet_address: str | None = None  # Adresse wallet liée (Option 3)
    node_public_url: str | None = None  # URL publique déclarée (Option 2/3)
    bootstrap_mode: bool = False       # True = wallet pas encore configuré

    def public_dict(self) -> dict[str, Any]:
        d = {
            "network_id": self.network_id,
            "node_id": self.node_id,
            "kem_public_key_hex": self.kem_public_key_hex,
            "api_port": self.api_port,
            "p2p_port": self.p2p_port,
        }
        if self.wallet_address:
            d["wallet_address"] = self.wallet_address
        if self.node_public_url:
            d["node_public_url"] = self.node_public_url
        return d


def _detect_fresh_public_url() -> str:
    """Détecte l'URL publique du nœud depuis les variables d'environnement de l'hébergeur.

    Re-appelée à chaque démarrage — pas stockée statiquement — pour couvrir :
      - Replit : REPLIT_DOMAINS injecté automatiquement par l'hébergeur
      - Replit (ancien format) : REPL_OWNER + REPL_SLUG
      - Render / Railway : RENDER_EXTERNAL_URL / RAILWAY_PUBLIC_DOMAIN
      - VPS / Hostinger : ARTCB_NODE_PUBLIC_URL défini manuellement
      - Dev local : http://localhost:PORT (si aucune variable hébergeur présente)

    Ordre de priorité :
      1. ARTCB_NODE_PUBLIC_URL   (toujours prioritaire — saisie manuelle opérateur)
      2. REPLIT_DOMAINS          (Replit moderne — injecté automatiquement)
      3. REPL_OWNER + REPL_SLUG  (Replit ancien format)
      4. RENDER_EXTERNAL_URL     (Render.com)
      5. RAILWAY_PUBLIC_DOMAIN   (Railway.app)
      6. http://localhost:PORT   (dev local — pas de variable hébergeur)
    """
    # Priorité 1 : manuel (toujours respecté)
    manual = os.getenv("ARTCB_NODE_PUBLIC_URL", "").strip()
    if manual:
        return manual

    # Priorité 2 : Replit — REPLIT_DOMAINS (format moderne, injecté auto)
    replit_domains = os.getenv("REPLIT_DOMAINS", "").strip()
    if replit_domains:
        first = replit_domains.split(",")[0].strip()
        if first:
            return f"https://{first}"

    # Priorité 3 : Replit ancien format
    slug = os.getenv("REPL_SLUG", "").strip()
    owner = os.getenv("REPL_OWNER", "").strip()
    if slug and owner:
        return f"https://{owner}--{slug}.repl.co"

    # Priorité 4 : Render
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if render_url:
        return render_url

    # Priorité 5 : Railway
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if railway_domain:
        return f"https://{railway_domain}"

    # Priorité 6 : Dev local — retourner localhost avec le port configuré
    port = os.getenv("ARTCB_PORT", "8000").strip()
    return f"http://localhost:{port}"


def node_id_from_wallet_address(wallet_address: str) -> str:
    """Option 3 : node_id = adresse wallet (artcb1xxx).

    L'adresse wallet EST l'identifiant unique du nœud.
    Cela garantit qu'un seul nœud peut opérer avec chaque wallet.
    """
    return wallet_address


def _read_node_config(data_dir: Path) -> dict:
    """Lit le fichier .node_config local (non committé) s'il existe.

    Ce fichier est écrit par POST /setup/init-node après la première
    création du wallet de nœud. Il évite de devoir ajouter la variable
    dans les secrets Replit manuellement lors du premier déploiement.
    Format JSON minimal : {"wallet_address": "artcb1...", "public_url": "https://..."}
    """
    cfg_path = Path(data_dir) / _NODE_CONFIG_FILENAME
    if cfg_path.is_file():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def write_node_config(data_dir: Path, wallet_address: str, public_url: str = "") -> None:
    """Persiste l'adresse wallet dans .node_config après POST /setup/init-node."""
    cfg_path = Path(data_dir) / _NODE_CONFIG_FILENAME
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"wallet_address": wallet_address}
    if public_url:
        payload["public_url"] = public_url
    cfg_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    cfg_path.chmod(0o600)
    logger.info("Node config written: wallet_address=%s public_url=%s", wallet_address, public_url)


class NodeIdentityStore:
    """Persiste l'identité P2P du nœud (clé ML-KEM).

    Résolution de ARTCB_NODE_WALLET_ADDRESS dans cet ordre de priorité :
      1. Variable d'environnement ARTCB_NODE_WALLET_ADDRESS
      2. Fichier .node_config dans data_dir (écrit par /setup/init-node)
      3. MODE BOOTSTRAP — node_id temporaire, API limitée aux routes /setup/*

    En mode bootstrap, aucune clé ML-KEM n'est générée et aucun fichier
    node_identity.json n'est créé. Le nœud ne participe pas au réseau P2P.
    """

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "p2p" / "node_identity.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data_dir = Path(data_dir)

    def load_or_create(self, *, api_port: int = 8000) -> NodeIdentity:
        # L'URL publique est re-détectée à chaque démarrage et mise à jour
        # dans .node_config si elle a changé. Cela couvre :
        #   - Replit : REPLIT_DOMAINS change selon le compte/projet
        #   - Dev local : localhost detecté si pas de variable hébergeur
        #   - Migration d'hébergeur : nouvelle URL prise en compte automatiquement
        fresh_url = _detect_fresh_public_url()

        if self.path.is_file():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Mettre à jour l'URL dans node_identity.json si elle a changé
            stored_url = data.get("node_public_url") or ""
            if fresh_url and fresh_url != stored_url:
                data["node_public_url"] = fresh_url
                self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                logger.info("node_identity: public_url updated %r → %r", stored_url, fresh_url)
            # AWS3-class leftover: identity created under X25519 fallback (32 bytes)
            # while liboqs is now present. Upgrade in place so we advertise a real
            # ML-KEM-768 key instead of lying with kem_algorithm=ML-KEM-768.
            try:
                stored_pub = bytes.fromhex(str(data.get("kem_public_key_hex") or ""))
            except ValueError:
                stored_pub = b""
            if native_liboqs_available() and len(stored_pub) != MLKEM768_PUBLIC_BYTES:
                secret, public = generate_kem_keypair()
                data["kem_public_key_hex"] = public.hex()
                data["kem_secret_key_hex"] = secret.hex()
                self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                self.path.chmod(0o600)
                logger.warning(
                    "Upgraded stale P2P KEM identity from %d-byte public key to ML-KEM-768 (%d bytes)",
                    len(stored_pub),
                    MLKEM768_PUBLIC_BYTES,
                )
            return NodeIdentity(
                network_id=data.get("network_id", NETWORK_ID),
                node_id=data["node_id"],
                kem_public_key_hex=data["kem_public_key_hex"],
                kem_secret_key_hex=data["kem_secret_key_hex"],
                api_port=int(data.get("api_port", api_port)),
                p2p_port=int(data.get("p2p_port", DEFAULT_P2P_PORT)),
                wallet_address=data.get("wallet_address"),
                node_public_url=fresh_url or data.get("node_public_url"),
                bootstrap_mode=False,
            )

        # Résolution de l'adresse : env var > .node_config > mode bootstrap
        wallet_address = os.getenv("ARTCB_NODE_WALLET_ADDRESS", "").strip() or None
        if not wallet_address:
            node_cfg = _read_node_config(self._data_dir)
            wallet_address = node_cfg.get("wallet_address", "").strip() or None
            # Mettre à jour l'URL dans .node_config si elle a changé depuis la création
            if wallet_address and fresh_url:
                stored_cfg_url = node_cfg.get("public_url", "")
                if fresh_url != stored_cfg_url:
                    write_node_config(self._data_dir, wallet_address, fresh_url)
                    logger.info("node_config: public_url updated %r → %r", stored_cfg_url, fresh_url)

        if not wallet_address:
            # MODE BOOTSTRAP — démarrage sans identité configurée.
            # L'API démarre avec les routes /setup/* uniquement.
            hostname = socket.gethostname()
            bootstrap_id = f"bootstrap_{hostname[:20]}"
            logger.warning(
                "BOOTSTRAP MODE: ARTCB_NODE_WALLET_ADDRESS absent. "
                "Node ID temporaire: %s — appeler POST /setup/init-node pour configurer.",
                bootstrap_id,
            )
            return NodeIdentity(
                network_id=NETWORK_ID,
                node_id=bootstrap_id,
                kem_public_key_hex="",
                kem_secret_key_hex="",
                api_port=api_port,
                p2p_port=DEFAULT_P2P_PORT,
                wallet_address=None,
                node_public_url=fresh_url or None,  # URL connue même en bootstrap
                bootstrap_mode=True,
            )

        try:
            secret, public = generate_kem_keypair()
        except KEMError as exc:
            raise KEMError(f"Cannot init P2P node identity: {exc}") from exc

        # Récupérer l'URL publique : env var > .node_config
        node_cfg = _read_node_config(self._data_dir)
        public_url = (
            os.getenv("ARTCB_NODE_PUBLIC_URL", "").strip()
            or node_cfg.get("public_url", "")
            or None
        )
        node_id = node_id_from_wallet_address(wallet_address)

        identity = NodeIdentity(
            network_id=NETWORK_ID,
            node_id=node_id,
            kem_public_key_hex=public.hex(),
            kem_secret_key_hex=secret.hex(),
            api_port=api_port,
            p2p_port=DEFAULT_P2P_PORT,
            wallet_address=wallet_address,
            node_public_url=public_url,
            bootstrap_mode=False,
        )
        self._save(identity)
        logger.info(
            "Created P2P node identity %s (option3_wallet=%s)",
            identity.node_id, bool(wallet_address),
        )
        return identity

    def _save(self, identity: NodeIdentity) -> None:
        payload = {
            "network_id": identity.network_id,
            "node_id": identity.node_id,
            "kem_public_key_hex": identity.kem_public_key_hex,
            "kem_secret_key_hex": identity.kem_secret_key_hex,
            "api_port": identity.api_port,
            "p2p_port": identity.p2p_port,
        }
        if identity.wallet_address:
            payload["wallet_address"] = identity.wallet_address
        if identity.node_public_url:
            payload["node_public_url"] = identity.node_public_url
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.path.chmod(0o600)


def advertised_base_url(public_url: str | None, api_port: int) -> str:
    """URL this node tells peers to use. Never http://replit.host:443."""
    from urllib.parse import urlparse

    raw = (public_url or "").strip()
    if raw:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = parsed.hostname or ""
        scheme = (parsed.scheme or "").lower()
        if host.endswith((".replit.app", ".repl.co")):
            scheme = "https"
        if scheme not in {"http", "https"}:
            scheme = "https" if (parsed.port or 0) == 443 else "http"
        port = parsed.port or (443 if scheme == "https" else api_port)
        return f"{scheme}://{host}:{port}"
    return f"http://127.0.0.1:{api_port}"
