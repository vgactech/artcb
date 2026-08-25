#!/usr/bin/env python3
"""Réinitialisation complète de la blockchain ARTCB — nouveau genesis avec droits créateur.

Ce script :
  1. Efface la chaîne existante (blocks.jsonl + chain.key)
  2. Lit l'adresse créateur depuis data/founders/founders_wallets_v2.json
  3. Crée un nouveau genesis block avec les droits créateur gravés
  4. Crée le fichier data/founders/creator_rights.json (référence publique)

Usage :
    python3 scripts/create_founders_wallets_v2.py   # Créer les wallets d'abord
    python3 scripts/init_genesis.py                  # Puis ce script

ATTENTION : Cette opération est irréversible.
  Assurer que le snapshot est dans confidentiel/ avant de lancer.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# ── Chemins ────────────────────────────────────────────────────────────────
CHAIN_DIR       = Path("data/chain")
BLOCKS_FILE     = CHAIN_DIR / "blocks.jsonl"
CHAIN_KEY_FILE  = CHAIN_DIR.parent / "chain.key"
CHAIN_PQC_FILE  = CHAIN_DIR.parent / "chain.key.pqc"
WALLETS_V2_FILE = Path("data/founders/founders_wallets_v2.json")
CREATOR_REF     = Path("data/founders/.creator_wallet_address")
RIGHTS_FILE     = Path("data/founders/creator_rights.json")

MISSION = (
    "ARTCB : Construire la nouvelle internet, blockchain et facon de communiquer "
    "adaptee a l'IA. Supply max 21 000 000 ARTCB. "
    "Proof-of-Learning collectif (PoL). Post-quantique natif ML-DSA-65 FIPS204."
)


def load_creator_address() -> tuple[str, str]:
    """Charge l'adresse créateur et l'adresse dev depuis founders_wallets_v2.json."""
    if WALLETS_V2_FILE.exists():
        data = json.loads(WALLETS_V2_FILE.read_text(encoding="utf-8"))
        wallets = data["wallets"]
        creator_addr = wallets[0]["address"]
        dev_addr     = wallets[1]["address"]
        print(f"  Createur    : {creator_addr[:40]}...")
        print(f"  Developpement : {dev_addr[:40]}...")
        return creator_addr, dev_addr
    if CREATOR_REF.exists():
        creator_addr = CREATOR_REF.read_text().strip()
        print(f"  Createur (ref) : {creator_addr[:40]}...")
        return creator_addr, ""
    print("ERREUR : Lancer d'abord scripts/create_founders_wallets_v2.py")
    sys.exit(1)


def reset_chain_files() -> None:
    """Efface les fichiers de chaîne existants."""
    for f in [BLOCKS_FILE, CHAIN_KEY_FILE, CHAIN_PQC_FILE]:
        if f.exists():
            f.unlink()
            print(f"  Effacé : {f}")


def create_genesis(creator_addr: str, dev_addr: str) -> dict:
    """Crée le genesis block avec les droits créateur gravés."""
    now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    creator_allocation = 1_000_000
    dev_allocation     = 1_000_000

    genesis = {
        "index":       0,
        "timestamp":   now_str,
        "prev_hash":   "0" * 64,
        "graph_root":  "genesis",
        "merkle_root": "genesis",
        "pol_score":   1.0,
        "hash":        "genesis-artcb-v2",
        "hash_sha3":   "genesis-artcb-v2-sha3",
        "signature":   "genesis",
        "graph_id":    "genesis",
        "visibility":  "public",
        "block_reward": 0,
        "contributors": [],

        # ═══════════════════════════════════════════════════════════
        # DROITS CRÉATEUR — IMMUABLES — GRAVÉS AU GENESIS
        # Ces champs ne peuvent jamais être modifiés par aucun vote.
        # ═══════════════════════════════════════════════════════════
        "creator_rights": {
            "creator_wallet":           creator_addr,
            "creator_veto_enabled":     True,
            "creator_vote_weight":      999_999,
            "creator_rights_immutable": True,
            "creator_rights_version":   "1.0",
            "established_at":           now_str,
            "note": (
                "Droits permanents du createur ARTCB. "
                "Aucun vote communautaire ne peut les modifier. "
                "Garantie de l'objectif long terme : nouvelle internet + blockchain IA."
            ),
        },

        # ═══════════════════════════════════════════════════════════
        # ALLOCATION INITIALE
        # ═══════════════════════════════════════════════════════════
        "initial_allocation": {
            creator_addr: {
                "artcb":        creator_allocation,
                "satoshi":      creator_allocation * 100_000_000,
                "role":         "creator",
                "description":  "Compte créateur ARTCB — droits absolus de gouvernance",
            },
            **(
                {
                    dev_addr: {
                        "artcb":        dev_allocation,
                        "satoshi":      dev_allocation * 100_000_000,
                        "role":         "development",
                        "description":  "Compte dédié au développement ARTCB",
                    },
                }
                if dev_addr else {}
            ),
        },

        # ═══════════════════════════════════════════════════════════
        # RÈGLES IMMUABLES DU PROTOCOLE
        # ═══════════════════════════════════════════════════════════
        "protocol_constants": {
            "max_supply_artcb":    21_000_000,
            "satoshi_per_artcb":   100_000_000,
            "initial_block_reward": 50.0,
            "halving_interval":    210_000,
            "pol_threshold":       0.6,
            "pqc_algorithm":       "ML-DSA-65 FIPS204",
            "signature_scheme":    "Ed25519 + ML-DSA-65 hybrid",
            "immutable":           True,
        },

        "mission_statement": MISSION,
        "network_id":        "artcb-mainnet-1",
        "genesis_version":   "3.0",
    }

    return genesis


def write_creator_rights_public(creator_addr: str, genesis_hash: str, now_str: str) -> None:
    """Écrit le fichier public de référence des droits créateur."""
    rights = {
        "schema":               "artcb-creator-rights-v1",
        "creator_wallet":       creator_addr,
        "creator_veto_enabled": True,
        "creator_vote_weight":  999_999,
        "immutable":            True,
        "genesis_block_hash":   genesis_hash,
        "established_at":       now_str,
        "description": (
            "L'adresse ci-dessus est le compte créateur permanent de la blockchain ARTCB. "
            "Son vote a un poids de 999 999 voix. "
            "Son vote NON invalide toute proposition de gouvernance. "
            "Ces droits sont gravés dans le genesis block et ne peuvent pas etre modifies."
        ),
    }
    RIGHTS_FILE.write_text(json.dumps(rights, indent=2, ensure_ascii=False))
    print(f"  Fichier droits créateur : {RIGHTS_FILE}")


def main() -> None:
    print("=" * 60)
    print("RÉINITIALISATION BLOCKCHAIN ARTCB — GENESIS v2")
    print("=" * 60)

    # Vérification snapshot
    snap_dirs = list(Path("confidentiel").glob("snapshot_blockchain_*"))
    if not snap_dirs:
        print("ATTENTION : Aucun snapshot trouvé dans confidentiel/")
        print("  Lancer d'abord une sauvegarde avant de réinitialiser.")
        confirm = input("Continuer quand même ? (tapez OUI) : ")
        if confirm.strip() != "OUI":
            print("Annulé.")
            sys.exit(0)
    else:
        print(f"  Snapshot trouvé : {snap_dirs[-1].name}")

    # Charger les adresses
    print("\nChargement des adresses...")
    creator_addr, dev_addr = load_creator_address()

    # Effacer l'ancienne chaîne
    print("\nEffacement de l'ancienne chaîne...")
    reset_chain_files()

    # Créer le genesis block
    print("\nCréation du genesis block v2...")
    now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    genesis = create_genesis(creator_addr, dev_addr)

    # Écrire blocks.jsonl
    CHAIN_DIR.mkdir(parents=True, exist_ok=True)
    BLOCKS_FILE.write_text(
        json.dumps(genesis, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"  Genesis écrit dans {BLOCKS_FILE}")

    # Fichier droits créateur public
    write_creator_rights_public(creator_addr, "genesis-artcb-v2", now_str)

    print()
    print("=" * 60)
    print("GENESIS v2 CRÉÉ AVEC SUCCÈS")
    print("=" * 60)
    print(f"  Créateur  : {creator_addr[:40]}...")
    print(f"  Droits    : veto=True, vote_weight=999999")
    print(f"  Allocation: 1 000 000 ARTCB créateur + 1 000 000 ARTCB dev")
    print(f"  Protocole : supply max 21M, PoL >= 0.6, ML-DSA-65")
    print()
    print("  Prochaine étape : démarrer l'API")
    print("  python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000")
    print("=" * 60)


if __name__ == "__main__":
    main()
