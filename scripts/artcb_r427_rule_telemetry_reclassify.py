#!/usr/bin/env python3
"""R427 — Rule Telemetry : reclassification fine du corpus ARTCB par domaine.

Problème actuel (de1d6bd) :
  - 96/230 entrées = PROTOCOL (trop large, perd de la précision)
  - IDENTITY = 1 (sous-représenté, toute la biométrie/WebAuthn est dans PROTOCOL)
  - ROADMAP = 1, TESTING = 1 (quasi absents)

Solution : règles de reclassification basées sur les mots-clés de canonical_text + ref + source_id.

Mapping vers 10 domaines précis (superset des 7 actuels) :
  PROTOCOL_CRYPTO   — PQC, ML-DSA, Ed25519, hybride, KEM, SEAL, FHE
  PROTOCOL_NETWORK  — P2P, bootstrap, libp2p, nœuds, DV, BFT, PBFT
  PROTOCOL_CHAIN    — blockchain, bloc, ledger, hash, fork, genèse
  IDENTITY          — biométrie, WebAuthn, fingerprint, wallet binding, human_id
  TOKENOMICS        — pARTCB, pubARTCB, PoL, reward, supply, HBP, halving
  GOVERNANCE        — décisions, DV, certif, mainnet, opérateur
  TESTING           — tests, PASS, FAR, FRR, pytest, validation
  LESSONS           — leçons, L-0xx, erreur, correction
  INFRASTRUCTURE    — nœuds live, OVH, AWS, Replit, SSH, systemd
  ROADMAP           — phases, MVP, planning, jalon

Usage :
  python3 scripts/artcb_r427_rule_telemetry_reclassify.py
  python3 scripts/artcb_r427_rule_telemetry_reclassify.py --dry-run

Produit :
  rules/rule_corpus_index.json   ← mis à jour (backup automatique avant écriture)
  logs/R427_reclassify_result.json
  rapports/R427_rule_telemetry_reclassify_<date>.md

PROTOCOLE ARTCB — mode DEBUG — jamais de hardcoding.
CERTIFIED_100=false
"""
from __future__ import annotations
MODULE_VERSION = '1.0.1'  # R427

import argparse
import json
import logging
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("artcb.r427.reclassify")

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "rules" / "rule_corpus_index.json"
LOGS_DIR = ROOT / "logs"
RAPPORTS_DIR = ROOT / "rapports"

# ─── Règles de reclassification (ordre de priorité — premier match gagne) ─────
# Chaque règle : (domaine_cible, [mots_clés_positifs], [mots_clés_négatifs])
RECLASSIFY_RULES: list[tuple[str, list[str], list[str]]] = [
    # --- IDENTITY (biométrie, WebAuthn, device binding) ---
    ("IDENTITY", [
        "biométr", "biometric", "webauthn", "fido", "fingerprint", "empreinte",
        "template", "bch", "fuzzy", "hamming", "human_identity", "unique_human",
        "uv=true", "user_verification", "wallet_per_human", "device_binding",
        "wallet binding", "device fingerprint", "human_id", "check_uniqueness",
        "fhe", "seal", "openfhe", "concrete", "far", "frr", "eer", "liveness",
        "pad ", "anti-spoofing",
    ], []),

    # --- TOKENOMICS ---
    ("TOKENOMICS", [
        "partcb", "pubartcb", "tartcb", "pol ", "proof-of-learning", "reward",
        "supply", "21m", "21 m", "tokenomics", "hbp", "halving", "géopopulation",
        "demography", "demographic", "universal dividend", "vault", "frais",
        "block_reward", "epoch", "owner_decay",
    ], []),

    # --- INFRASTRUCTURE (nœuds, déploiement, ops) ---
    ("INFRASTRUCTURE", [
        "ovh", "aws", "replit", "ssh", "systemd", "uvicorn", "pip install",
        "requirements.txt", "doppler", "docker", "start_node", "deploy",
        "hotfix", "redémarrage", "crash", "502", "nœud live", "node live",
        "install.sh", "railway", "render", "vps",
    ], []),

    # --- PROTOCOL_CRYPTO (cryptographie, PQC, signatures) ---
    ("PROTOCOL_CRYPTO", [
        "ml-dsa", "mldsa", "ed25519", "liboqs", "pqc", "post-quantum",
        "hybride", "ml-kem", "kem", "signature", "sign ", "verify",
        "privkey", "public key", "keypair", "crypto", "chiffrement",
        "blake2", "sha-256", "hkdf", "salt", "pepper",
    ], []),

    # --- PROTOCOL_NETWORK (P2P, réseau, pairs) ---
    ("PROTOCOL_NETWORK", [
        "p2p", "bootstrap", "libp2p", "peer", "gossip", "fanout",
        "network", "réseau", "nœud", "announce", "broadcast",
        "register-public", "ssrf", "allowlist", "bearer",
        "dv-04", "dv-05", "dv-06", "dv-02",
    ], []),

    # --- PROTOCOL_CHAIN (blockchain, blocs, consensus) ---
    ("PROTOCOL_CHAIN", [
        "blockchain", "bloc", "block", "ledger", "chain", "genesis",
        "genèse", "hash", "fork", "pbft", "bft", "consensus",
        "append", "finality", "tip", "last_hash", "height",
        "prepare/commit", "certification_gate",
    ], []),

    # --- TESTING ---
    ("TESTING", [
        "pytest", "test_", " test ", "pass ", "fail ", "assert",
        "coverage", "fixture", "mock", "parametrize",
        "dv-0", "pre-dv", "v-pqc", "v-r0",
    ], []),

    # --- LESSONS (leçons apprises) ---
    ("LESSONS", [
        "leçon", "lesson", "l-0", "l-04", "l-05", "contexte :", "action :",
        "root cause", "bug corrigé", "hotfix", "divergence", "retrosp",
    ], []),

    # --- GOVERNANCE (décisions, certif, mainnet) ---
    ("GOVERNANCE", [
        "d-0", "décision", "decision", "certif", "mainnet", "opérateur",
        "go utilisateur", "gate", "certified_distributed",
    ], []),

    # --- ROADMAP ---
    ("ROADMAP", [
        "roadmap", "phase ", "jalon", "mvp", "planning", "milestone",
        "task-", "prochaine étape", "chantier ouvert",
    ], []),
]


def _score_entry(text: str, keywords: list[str]) -> int:
    """Compte combien de mots-clés se trouvent dans text (insensible à la casse)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def reclassify_entry(entry: dict) -> str:
    """Retourne le domaine reclassifié pour une entrée du corpus."""
    # Texte complet à analyser : canonical_text + ref + source_id + source_path
    text = " ".join([
        str(entry.get("canonical_text") or ""),
        str(entry.get("ref") or ""),
        str(entry.get("source_id") or ""),
        str(entry.get("source_path") or ""),
        str(entry.get("kind") or ""),
        str(entry.get("status") or ""),
    ])

    # LESSON → toujours LESSONS
    if entry.get("kind") == "LESSON":
        return "LESSONS"

    # DECISION → priorité GOVERNANCE sauf si très clairement autre domaine
    if entry.get("kind") == "DECISION":
        # Vérifier si clairement identity, tokenomics, infra d'abord
        for domain, pos_kw, neg_kw in RECLASSIFY_RULES:
            if domain in ("IDENTITY", "TOKENOMICS", "INFRASTRUCTURE"):
                if _score_entry(text, pos_kw) >= 2:
                    return domain
        return "GOVERNANCE"

    # Règles générales par score
    best_domain = entry.get("primary_domain", "PROTOCOL")
    best_score = 0

    for domain, pos_kw, _neg_kw in RECLASSIFY_RULES:
        score = _score_entry(text, pos_kw)
        if score > best_score:
            best_score = score
            best_domain = domain

    # Si score 0 → garder domaine actuel
    if best_score == 0:
        return entry.get("primary_domain") or "PROTOCOL"

    return best_domain


def main(dry_run: bool = False) -> int:
    logger.info("[R427] Démarrage reclassification rule corpus — dry_run=%s", dry_run)

    if not CORPUS_PATH.exists():
        logger.error("Fichier corpus introuvable : %s", CORPUS_PATH)
        return 1

    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    entries_raw = data.get("entries") or data
    entries_list: list[dict]
    if isinstance(entries_raw, dict):
        entries_list = list(entries_raw.values())
    else:
        entries_list = list(entries_raw)

    total = len(entries_list)
    logger.info("[R427] %d entrées chargées", total)

    before_domains: Counter = Counter(e.get("primary_domain", "?") for e in entries_list)
    changes: list[dict] = []

    for entry in entries_list:
        old_domain = entry.get("primary_domain", "?")
        new_domain = reclassify_entry(entry)

        if old_domain != new_domain:
            changes.append({
                "corpus_id": entry.get("corpus_id"),
                "ref": entry.get("ref"),
                "kind": entry.get("kind"),
                "old_domain": old_domain,
                "new_domain": new_domain,
            })
            if not dry_run:
                entry["primary_domain"] = new_domain
                entry["domains"] = [new_domain]
                entry["domain_classified_by"] = "artcb_r427_v1"
                entry["domain_classified_ts"] = datetime.now(timezone.utc).isoformat()

    after_domains: Counter = Counter(e.get("primary_domain", "?") for e in entries_list)

    logger.info("[R427] Modifications : %d / %d entrées", len(changes), total)
    logger.info("[R427] Avant : %s", dict(sorted(before_domains.items())))
    logger.info("[R427] Après : %s", dict(sorted(after_domains.items())))

    # ── Sauvegarde ────────────────────────────────────────────────────────────
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": "artcb_r427_rule_telemetry_reclassify.py",
        "dry_run": dry_run,
        "total_entries": total,
        "changes_count": len(changes),
        "before_domains": dict(sorted(before_domains.items())),
        "after_domains": dict(sorted(after_domains.items())),
        "changes_sample": changes[:30],  # premiers 30
    }
    log_path = LOGS_DIR / "R427_reclassify_result.json"
    log_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[R427] Log écrit → %s", log_path)

    if not dry_run and changes:
        # Backup avant écriture
        backup_path = CORPUS_PATH.with_suffix(".json.bak_r427")
        shutil.copy2(CORPUS_PATH, backup_path)
        logger.info("[R427] Backup → %s", backup_path)

        # Mise à jour du corpus
        if isinstance(data.get("entries"), list):
            data["entries"] = entries_list
        elif isinstance(data.get("entries"), dict):
            # Reconstruit le dict avec les mêmes clés
            keys = list(data["entries"].keys())
            data["entries"] = {k: entries_list[i] for i, k in enumerate(keys)}
        else:
            data = entries_list  # type: ignore[assignment]

        if isinstance(data, dict):
            data["domain_classification_version"] = "R427-v1"
            data["domain_classification_updated_at"] = datetime.now(timezone.utc).isoformat()

        CORPUS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[R427] Corpus mis à jour → %s", CORPUS_PATH)

    # ── Rapport markdown ──────────────────────────────────────────────────────
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rapport_path = RAPPORTS_DIR / f"R427_rule_telemetry_reclassify_{date_str}.md"

    md_lines = [
        f"# R427 — Rule Telemetry : Reclassification par domaine",
        f"",
        f"**Date :** {date_str}  ",
        f"**SHA HEAD :** `de1d6bd`  ",
        f"**Mode :** DEBUG ACTIF  ",
        f"**dry_run :** {dry_run}  ",
        f"**CERTIFIED_100 :** false",
        f"",
        f"---",
        f"",
        f"## Résumé",
        f"",
        f"| Métrique | Valeur |",
        f"|----------|--------|",
        f"| Total entrées | {total} |",
        f"| Modifications | {len(changes)} |",
        f"| Conservées | {total - len(changes)} |",
        f"",
        f"---",
        f"",
        f"## AVANT — Distribution par domaine",
        f"",
        f"| Domaine | Count |",
        f"|---------|-------|",
    ]
    for dom, cnt in sorted(before_domains.items()):
        md_lines.append(f"| {dom} | {cnt} |")

    md_lines += [
        f"",
        f"---",
        f"",
        f"## APRÈS — Distribution par domaine",
        f"",
        f"| Domaine | Count |",
        f"|---------|-------|",
    ]
    for dom, cnt in sorted(after_domains.items()):
        md_lines += [f"| {dom} | {cnt} |"]

    md_lines += [
        f"",
        f"---",
        f"",
        f"## Échantillon des modifications (30 premières)",
        f"",
        f"| corpus_id | ref | kind | Avant | Après |",
        f"|-----------|-----|------|-------|-------|",
    ]
    for c in changes[:30]:
        md_lines.append(
            f"| {c.get('corpus_id','?')} | {c.get('ref','?')[:40]} | {c.get('kind','?')} "
            f"| {c.get('old_domain','?')} | {c.get('new_domain','?')} |"
        )

    md_lines += [
        f"",
        f"---",
        f"",
        f"## Fichiers modifiés",
        f"",
        f"| Fichier | Action |",
        f"|---------|--------|",
        f"| `rules/rule_corpus_index.json` | Reclassifié (backup `.bak_r427`) |",
        f"| `logs/R427_reclassify_result.json` | Log complet des modifications |",
        f"",
        f"---",
        f"",
        f"## Limites",
        f"",
        f"- Classification basée sur mots-clés (heuristique) — pas de ML",
        f"- Domaines qui se chevauchent (ex: GOVERNANCE ↔ PROTOCOL_CHAIN) = premier match gagne",
        f"- `CERTIFIED_100=false` — validation manuelle recommandée sur les 30 changements ci-dessus",
    ]

    rapport_path.write_text("\n".join(md_lines), encoding="utf-8")
    logger.info("[R427] Rapport → %s", rapport_path)

    print(f"\n[R427] RÉSULTAT :")
    print(f"  Total entrées   : {total}")
    print(f"  Modifications   : {len(changes)}")
    print(f"  Avant PROTOCOL  : {before_domains.get('PROTOCOL', 0)}")
    print(f"  Après PROTOCOL* : {after_domains.get('PROTOCOL', 0) + after_domains.get('PROTOCOL_CRYPTO', 0) + after_domains.get('PROTOCOL_NETWORK', 0) + after_domains.get('PROTOCOL_CHAIN', 0)}")
    print(f"  Log             : {log_path}")
    print(f"  Rapport         : {rapport_path}")
    if dry_run:
        print(f"\n  [DRY RUN] — aucun fichier modifié. Relancer sans --dry-run pour appliquer.")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="R427 Rule Telemetry Reclassify")
    parser.add_argument("--dry-run", action="store_true", help="Simuler sans écriture")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
