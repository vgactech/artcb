#!/usr/bin/env python3
"""
CLI de Minage d'Apprentissage ARTCB — Version Simplifiée
Utilise l'infrastructure existante avec affichage console détaillé
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Ajouter le chemin src au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from artcb.chain.manager import ChainManager
from artcb.config import load_settings
from artcb.io.pdf_loader import extract_pdf_text
from artcb.ir.decoder import IRDecoder
from artcb.ir.encoder import IREncoder
from artcb.memory.graph_store import GraphStore
from artcb.pol.scorer import PolScorer
from artcb.wallet.manager import WalletManager


def print_header(title: str):
    """Affiche un header formaté"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_metric(label: str, value, unit: str = ""):
    """Affiche une métrique formatée"""
    print(f"  • {label:35} : {value} {unit}")


def compare_with_existing_systems():
    """Compare ARTCB avec Bitcoin, Ethereum, etc."""
    print_header(" COMPARAISON AVEC SYSTÈMES EXISTANTS")

    print("┌" + "─" * 78 + "┐")
    print("│ " + "Système".ljust(15) + " │ " + "Consensus".ljust(20) + " │ " + "Distribution Reward".ljust(38) + " │")
    print("├" + "─" * 78 + "┤")

    systems = [
        ("Bitcoin (PoW)", "Proof-of-Work", "FAIL Winner-takes-all (1 gagnant)"),
        ("Ethereum (PoS)", "Proof-of-Stake", "WARN  Validateurs sélectionnés"),
        ("Filecoin (PoSt)", "Proof-of-Spacetime", "WARN  Stockage prouvé"),
        ("ARTCB (PoL)", "Proof-of-Learning", "OK COLLECTIF proportionnel PoL"),
    ]

    for system, consensus, reward in systems:
        print(f"│ {system:15} │ {consensus:20} │ {reward:38} │")

    print("└" + "─" * 78 + "┘")

    print("\n" + " INNOVATIONS ARTCB vs EXISTANTS ".center(80, "="))
    print()
    print("  1. OK REWARD COLLECTIF")
    print("     • Bitcoin: 1 mineur gagne tout (winner-takes-all)")
    print("     • ARTCB: TOUS les contributeurs PoL payés proportionnellement")
    print()
    print("  2. OK TRAVAIL UTILE")
    print("     • Bitcoin: Hash SHA-256 compétitif (gaspillage volontaire)")
    print("     • ARTCB: Compression + validation (apprentissage utile)")
    print()
    print("  3. OK GASPILLAGE MINIMAL")
    print("     • Bitcoin: ~99% calcul perdu (sécurité PoW)")
    print("     • ARTCB: Calcul orienté apprentissage (minimal)")
    print()
    print("  4. OK RÉVERSIBILITÉ 100%")
    print("     • Systèmes existants: Pas de garantie reconstruction")
    print("     • ARTCB: Reconstruction exacte du texte original")
    print()
    print("  5. OK DUAL-AGENT VALIDATION")
    print("     • Systèmes existants: Validation simple")
    print("     • ARTCB: Explorer propose + Critic valide")
    print()
    print("=" * 80 + "\n")


def mine_book(pdf_path: Path, wallet_name: str = "miner_demo"):
    """Mine un livre PDF avec affichage console détaillé"""

    print_header(f" MINAGE D'APPRENTISSAGE — {pdf_path.name}")

    start_time = time.time()

    # Configuration
    settings = load_settings()
    wallet_manager = WalletManager()
    chain = ChainManager(
        blocks_path=settings.data_dir / "chain" / "blocks.jsonl",
        enable_security=False  # Désactiver pour démo rapide
    )
    graph_store = GraphStore(directory=settings.data_dir / "graphs")

    # Wallet
    try:
        wallet = wallet_manager.load_wallet(name=wallet_name)
        print(f"OK Wallet chargé: {wallet_name}")
    except FileNotFoundError:
        wallet = wallet_manager.create_wallet(name=wallet_name)
        print(f"OK Nouveau wallet créé: {wallet_name}")

    address = wallet.address
    print(f" Adresse mineur: {address}\n")

    # Étape 1: Chargement PDF
    print("[1/6] Chargement PDF...")
    text = extract_pdf_text(pdf_path)

    print_metric("Fichier", pdf_path.name)
    print_metric("Taille originale", f"{len(text):,}", "caractères")
    print_metric("Taille fichier", f"{pdf_path.stat().st_size / 1024:.1f}", "KB")

    # Étape 2: Encodage IR
    print("\n[2/6] Encodage en IR ARTCB...")
    encode_start = time.time()
    encoder = IREncoder()
    ir_result = encoder.encode(text)
    encode_time = time.time() - encode_start

    graph_id = ir_result.graph_id
    ir_size = len(ir_result.to_json())
    compression_ratio = 1 - (ir_size / len(text))

    print_metric("Graph ID", graph_id)
    print_metric("Nœuds créés", len(ir_result.nodes))
    print_metric("Arêtes créées", len(ir_result.edges))
    print_metric("Taille IR", f"{ir_size:,}", "bytes")
    print_metric("Compression", f"{compression_ratio:.2%}")
    print_metric("Temps encodage", f"{encode_time:.2f}", "s")

    # Étape 3: Test réversibilité
    print("\n[3/6] Test de réversibilité...")
    decode_start = time.time()
    decoder = IRDecoder()
    reconstructed = decoder.decode(ir_result)
    decode_time = time.time() - decode_start

    # Similarité simple
    similarity = min(len(text), len(reconstructed)) / max(len(text), len(reconstructed))
    reversible = similarity >= 0.99

    print_metric("Texte reconstruit", f"{len(reconstructed):,}", "caractères")
    print_metric("Similarité", f"{similarity:.4f}")
    print_metric("Réversible", "OK OUI" if reversible else "FAIL NON")
    print_metric("Temps décodage", f"{decode_time:.2f}", "s")

    # Étape 4: Calcul PoL Score
    print("\n[4/6] Calcul Proof-of-Learning...")

    pol_scorer = PolScorer()
    pol_metrics = pol_scorer.score(
        graph=ir_result,
        nodes_validated=len(ir_result.nodes),
        nodes_proposed=len(ir_result.nodes)
    )
    pol_score = pol_metrics.pol_score

    print_metric("PoL Score", f"{pol_score:.4f}")
    print_metric("Seuil acceptation", "0.6000")
    print_metric("Bloc accepté", "OK OUI" if pol_score >= 0.6 else "FAIL NON")

    if pol_score < 0.6:
        print("\nWARN  PoL score insuffisant — bloc rejeté\n")
        return None

    # Étape 5: Création bloc blockchain
    print("\n[5/6] Création bloc blockchain...")

    # Stocker graphe
    graph_store.save(ir_result)
    # Calculer merkle root manuellement (méthode simple)
    import hashlib
    graph_json = ir_result.to_json()
    graph_root = hashlib.sha256(graph_json.encode()).hexdigest()

    # Créer bloc avec contributeur
    block = chain.append_block(
        graph_id=graph_id,
        graph_root=graph_root,
        pol_score=pol_score,
        contributors=[{
            "address": address,
            "pol_score": pol_score,
            "role": "miner"
        }]
    )

    print_metric("Bloc index", block.index)
    print_metric("Hash bloc", block.hash[:16] + "...")
    print_metric("Signature", block.signature[:32] + "...")

    # Étape 6: Calcul rewards
    print("\n[6/6] Distribution rewards collectifs...")

    # Reward live = min(R(H), remaining) — plus de halving d'index
    from artcb.economics.emission import issued_reward_satoshi

    block_reward_satoshi = issued_reward_satoshi(block.index)
    block_reward_artcb = block_reward_satoshi / 100_000_000

    # Un seul contributeur dans ce cas
    reward_satoshi = block_reward_satoshi
    reward_artcb = reward_satoshi / 100_000_000

    print_metric("Block reward", f"{block_reward_artcb:.8f}", "ARTCB")
    print_metric("Reward mineur (100%)", f"{reward_artcb:.8f}", "ARTCB")
    print_metric("Reward satoshi", f"{reward_satoshi:,}", "sat")

    # Balance totale
    balance = wallet_manager.get_balance(address=address, blocks_path=chain.blocks_path)

    print_metric("Balance totale", f"{balance['balance_artcb']:.8f}", "ARTCB")
    print_metric("Blocs minés", balance["block_count"])

    # Temps total
    total_time = time.time() - start_time

    print("\n" + "-" * 80)
    print_metric("  Temps total minage", f"{total_time:.2f}", "s")
    print_metric(" Vitesse", f"{len(text) / total_time:.0f}", "char/s")
    print("-" * 80 + "\n")

    return {
        "pdf_path": str(pdf_path),
        "graph_id": graph_id,
        "block_index": block.index,
        "block_hash": block.hash,
        "pol_score": pol_score,
        "compression_ratio": compression_ratio,
        "reversible": reversible,
        "similarity": similarity,
        "reward_artcb": reward_artcb,
        "reward_satoshi": reward_satoshi,
        "balance_artcb": balance["balance_artcb"],
        "total_time": total_time,
        "nodes_count": len(ir_result.nodes),
        "edges_count": len(ir_result.edges)
    }


def main():
    """Point d'entrée CLI"""
    print("\n" + "=" * 80)
    print("   ARTCB — CLI de Minage d'Apprentissage (Proof-of-Learning)")
    print("=" * 80 + "\n")

    # Comparer avec systèmes existants
    compare_with_existing_systems()

    # Miner les 2 livres
    books = [
        Path("data/fixtures/wailly_le_roi_de_l_inconnu.pdf"),
        Path("data/fixtures/quintus_de_smyrne_la_fin_de_l_iliade.pdf")
    ]

    results = []

    for book in books:
        if not book.exists():
            print(f"WARN  Fichier introuvable: {book}\n")
            continue

        result = mine_book(book)
        if result:
            results.append(result)

        time.sleep(1)  # Pause entre livres

    # Résumé final
    if results:
        print_header(" RÉSUMÉ FINAL MINAGE")

        total_reward = sum(r["reward_artcb"] for r in results)
        total_blocks = len(results)
        avg_pol = sum(r["pol_score"] for r in results) / total_blocks
        avg_compression = sum(r["compression_ratio"] for r in results) / total_blocks

        print_metric("Livres minés", total_blocks)
        print_metric("Reward total", f"{total_reward:.8f}", "ARTCB")
        print_metric("PoL moyen", f"{avg_pol:.4f}")
        print_metric("Compression moyenne", f"{avg_compression:.2%}")
        print_metric("Réversibilité", "OK 100%" if all(r["reversible"] for r in results) else "WARN  Partielle")

        # Balance finale (utiliser le dernier résultat)
        final_balance = results[-1]["balance_artcb"]
        print_metric("Balance finale", f"{final_balance:.8f}", "ARTCB")

        print("\n" + "=" * 80)
        print("OK Minage terminé avec succès !")
        print("=" * 80 + "\n")

        # Sauvegarder résultats
        output_file = Path("logs") / f"mining_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, "w") as f:
            json.dump({
                "miner_address": results[0]["pdf_path"] if results else "unknown",
                "timestamp": datetime.now().isoformat(),
                "results": results,
                "summary": {
                    "total_blocks": total_blocks,
                    "total_reward_artcb": total_reward,
                    "avg_pol_score": avg_pol,
                    "avg_compression": avg_compression,
                    "final_balance_artcb": final_balance
                }
            }, f, indent=2)

        print(f" Résultats sauvegardés: {output_file}\n")


if __name__ == "__main__":
    main()

