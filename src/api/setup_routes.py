"""Routes de bootstrap ARTCB — configurtion initiale du nœud (rapport 118).

Ces routes sont disponibles UNIQUEMENT quand le nœud est en mode bootstrap
(ARTCB_NODE_WALLET_ADDRESS absent et .node_config inexistant).

Elles permettent :
  1. POST /setup/init-node  — crée le wallet de nœud, persiste l'adresse dans
                              .node_config, détecte automatiquement l'URL publique.
  2. GET  /setup/status     — état du bootstrap (toujours accessible).

Workflow attendu (premier déploiement) :
  1. L'opérateur lance le nœud → mode bootstrap activé (log WARNING).
  2. Il appelle POST /setup/init-node avec {node_name, password}.
  3. Le serveur crée le wallet, écrit .node_config, retourne seed_hex + adresse.
  4. L'opérateur SAUVEGARDE la seed_hex (affichée une seule fois).
  5. Il redémarre le nœud — cette fois avec l'adresse dans .node_config.
  6. Le nœud démarre en mode normal, toutes les routes sont accessibles.

Optionnel : l'opérateur peut aussi copier ARTCB_NODE_WALLET_ADDRESS dans les
secrets Replit pour avoir la variable disponible même si .node_config est perdu
(reinstallation, reset de l'hébergeur, etc.).
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.p2p.node_identity import _detect_fresh_public_url, write_node_config

logger = logging.getLogger("artcb.api.setup")
router = APIRouter(prefix="/setup", tags=["setup"])


# ── Schémas Pydantic ──────────────────────────────────────────────────────────

class InitNodeRequest(BaseModel):
    node_name: str = Field(
        default="node_operator",
        min_length=1,
        max_length=64,
        description="Nom du wallet de ce nœud (identifie l'opérateur).",
    )
    password: str = Field(
        min_length=8,
        description=(
            "Mot de passe qui chiffre la clé privée sur le serveur. "
            "À conserver avec la seed_hex."
        ),
    )
    public_url: str = Field(
        default="",
        description=(
            "URL publique de ce nœud (ex: https://n1.artcb.me). "
            "Laissez vide pour détection automatique (Replit)."
        ),
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/status", summary="État du bootstrap du nœud")
def setup_status(request: Request) -> dict:
    """Retourne l'état du bootstrap — toujours accessible, même hors bootstrap."""
    from src.artcb.config import load_settings
    settings = load_settings()

    wallet_addr = os.getenv("ARTCB_NODE_WALLET_ADDRESS", "").strip()
    if not wallet_addr:
        from src.artcb.p2p.node_identity import _read_node_config
        cfg = _read_node_config(settings.data_dir)
        wallet_addr = cfg.get("wallet_address", "")

    bootstrap_active = not bool(wallet_addr)
    # L'URL est re-détectée live — pas lue depuis le .node_config stocké.
    # Cela garantit que /setup/status reflète toujours l'URL de l'hébergeur courant.
    detected_url = _detect_fresh_public_url()

    status = {
        "bootstrap_mode": bootstrap_active,
        "node_configured": not bootstrap_active,
        "wallet_address": wallet_addr or None,
        "detected_public_url": detected_url or None,
        "next_step": (
            "POST /setup/init-node avec {node_name, password} pour configurer ce nœud."
            if bootstrap_active
            else "Nœud configuré — redémarrez pour activer l'identité P2P complète si nécessaire."
        ),
    }
    logger.debug("Setup status: bootstrap=%s wallet=%s", bootstrap_active, wallet_addr or "ABSENT")
    return status


@router.post("/init-node", summary="Initialiser l'identité du nœud (premier déploiement)")
def init_node(body: InitNodeRequest, request: Request) -> dict:
    """Crée le wallet de nœud et persiste l'adresse dans .node_config.

    Comportement :
    - Crée un nouveau wallet Ed25519 + ML-DSA-65 hybride.
    - Retourne seed_hex UNE SEULE FOIS → à sauvegarder immédiatement.
    - Écrit .node_config dans le répertoire data/ du nœud.
    - Détecte automatiquement l'URL publique Replit si non fournie.
    - Le nœud redémarre en mode normal au prochain lancement.

    Sécurité :
    - Refusé si un wallet de nœud est déjà configuré (protection anti-réinitialisation).
    - ARTCB_ALLOW_MULTI_WALLET est ignoré pour ce endpoint (nœud = 1 wallet opérateur).
    """
    from src.artcb.config import load_settings
    from src.artcb.wallet.manager import WalletManager

    settings = load_settings()

    # Protection : si déjà configuré → refuser
    existing_addr = os.getenv("ARTCB_NODE_WALLET_ADDRESS", "").strip()
    if not existing_addr:
        from src.artcb.p2p.node_identity import _read_node_config
        cfg = _read_node_config(settings.data_dir)
        existing_addr = cfg.get("wallet_address", "").strip()

    if existing_addr:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ce nœud est déjà configuré avec l'adresse {existing_addr}. "
                "Réinitialisation refusée. Si vous devez reconfigurer ce nœud, "
                "supprimez manuellement le fichier .node_config dans le répertoire data/."
            ),
        )

    # Détecter l'URL publique (live depuis variables hébergeur)
    public_url = body.public_url.strip() or _detect_fresh_public_url()

    # Créer le wallet de nœud
    wm = WalletManager()
    try:
        wallet = wm.create_wallet(name=body.node_name, user_password=body.password)
    except Exception as exc:
        logger.error("init-node: wallet creation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Création du wallet échouée : {exc}") from exc

    # Persister dans .node_config
    write_node_config(
        data_dir=settings.data_dir,
        wallet_address=wallet.address,
        public_url=public_url,
    )

    seed_hex = wallet.signing_key.encode().hex()

    logger.warning(
        "init-node: wallet created name=%s address=%s public_url=%s — seed returned once",
        body.node_name, wallet.address, public_url,
    )

    response: dict = {
        "status": "configured",
        "node_name": body.node_name,
        "address": wallet.address,
        "public_key_hex": wallet.public_key_hex,
        "seed_hex": seed_hex,
        "public_url": public_url or None,
        "WARNING": (
            "SAUVEGARDEZ votre seed_hex MAINTENANT — c'est votre clé privée, "
            "elle ne sera plus jamais affichée. Sans elle, ce compte est inaccessible."
        ),
        "next_step": (
            "Redémarrez le nœud. Il démarrera en mode normal avec cette identité. "
            "Optionnel : ajoutez ARTCB_NODE_WALLET_ADDRESS dans vos secrets Replit "
            f"avec la valeur : {wallet.address}"
        ),
        "hybrid": wallet.is_hybrid,
    }
    if wallet.address_v2:
        response["address_v2"] = wallet.address_v2

    return response
