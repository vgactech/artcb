#!/usr/bin/env python3
"""
R393 — Classification automatique des 230 entrées rule_corpus_index.json par domaine.

Domaines définis :
  IDENTITY     — biométrie, WebAuthn, wallet, identité humaine
  CRYPTO       — PQC, ML-DSA, Ed25519, FHE, BCH, HKDF, signatures
  CONSENSUS    — PBFT, BFT, view-change, quorum, replica
  TOKENOMICS   — pARTCB, pubARTCB, PoL, supply, halving, HBP, géopop
  NETWORK      — P2P, gossip, bootstrap, nœuds, OVH, AWS, fanout
  GOVERNANCE   — DECISIONS_UTILISATEUR, D-xxx, opérateur
  TESTING      — tests, validation, DV-xx, certif, FAR/FRR
  PROTOCOL     — PROTOCOLE_ARTCB, règles, conventions, STANDARD_NAMES
  LESSONS      — LEÇONS_APPRISES, L-xxx, incidents, hotfix
  ROADMAP      — ROADMAP, tâches, TASK-xxx, jalons
  SECURITY     — anti-Sybil, fraude, device binding, rate limit
  OTHER        — non classifiable

Usage:
    python3 scripts/artcb_r393_classify_rules.py [--update]

  --update : écrit les modifications dans rule_corpus_index.json (sinon dry-run)

Rapport : logs/R393_rule_classification.json

CERTIFIED_100=false | DEBUG MODE
"""

from __future__ import annotations

MODULE_VERSION = '1.0.0'  # R393 — classification règles

import argparse
import json
import time
from pathlib import Path

# ── Domaines et leurs mots-clés ──────────────────────────────────────────────

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "IDENTITY": [
        "biometr", "webauthn", "wallet", "identit", "human", "uv=", "fingerprint",
        "enroll", "credential", "device", "fido", "face", "touchid", "unique_human",
        "user_verif", "biometric_onchain", "fuzzy", "template", "human_identity",
        "wallet_device", "add_device",
    ],
    "CRYPTO": [
        "pqc", "ml-dsa", "mldsa", "ed25519", "fhe", "seal", "openfhe", "concrete",
        "bch", "hkdf", "liboqs", "kem", "signature", "hybrid", "post-quantum",
        "homomorphic", "pedersen", "commitment", "sha-256", "sha256", "hamming",
        "sketch", "ecc", "bchlib",
    ],
    "CONSENSUS": [
        "pbft", "bft", "view-change", "view_change", "quorum", "replica", "primary",
        "prepare", "commit", "propose", "equivocation", "n=4", "n=5", "q=3", "f=1",
        "liveness", "pbft_finality", "consensus",
    ],
    "TOKENOMICS": [
        "partcb", "pubartcb", "tartcb", "pol", "supply", "halving", "hbp",
        "geopop", "epoch", "reward", "tokenomics", "supply_max", "21m",
        "dividend", "vault", "owner_decay", "demographic",
    ],
    "NETWORK": [
        "p2p", "gossip", "bootstrap", "noeud", "node", "ovh", "aws", "replit",
        "fanout", "broadcast", "sync", "ip", "mainnet", "devnet", "testnet",
        "artcb.me", "arbre", "seeds", "peer", "libp2p",
    ],
    "GOVERNANCE": [
        "d-0", "d-1", "d-2", "d-3", "d-4", "decision", "operator", "go ",
        "decisions_utilisateur", "vote", "gouvernance",
    ],
    "TESTING": [
        "test", "dv-0", "dv-1", "v-pqc", "certif", "far", "frr", "eer",
        "benchmark", "valida", "pytest", "pass", "fail", "assertion",
    ],
    "PROTOCOL": [
        "protocole", "standard_names", "convention", "rule", "regle",
        "protocol", "checklist", "pre_dev", "spec",
    ],
    "LESSONS": [
        "lecon", "lesson", "l-0", "l-1", "l-2", "l-3", "l-4", "l-5",
        "hotfix", "incident", "diagnostic", "erreur", "bug",
    ],
    "ROADMAP": [
        "roadmap", "task-0", "task-1", "r3", "r4", "r5", "jalon",
        "avancement", "todo", "open", "done",
    ],
    "SECURITY": [
        "sybil", "anti-sybil", "fraude", "fraud", "rate_limit", "binding",
        "bearer", "token", "api_key", "authz", "allowlist", "ssrf",
    ],
}


def classify_entry(entry: dict) -> str:
    """Attribue un domaine à une entrée du corpus."""
    # Texte à analyser : ref + source_path + canonical_text + kind
    text = " ".join([
        str(entry.get("ref", "")),
        str(entry.get("source_path", "")),
        str(entry.get("canonical_text", "")),
        str(entry.get("kind", "")),
        str(entry.get("authority", "")),
        str(entry.get("corpus_id", "")),
    ]).lower()

    scores: dict[str, int] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[domain] = score

    if not scores:
        # Fallback sur le kind
        kind = entry.get("kind", "").upper()
        kind_map = {
            "DECISION": "GOVERNANCE",
            "LESSON": "LESSONS",
            "CHECK": "TESTING",
            "CONVENTION": "PROTOCOL",
            "RULE": "PROTOCOL",
            "SPEC": "PROTOCOL",
            "QUESTION": "PROTOCOL",
            "EVIDENCE": "TESTING",
        }
        return kind_map.get(kind, "OTHER")

    return max(scores, key=lambda d: scores[d])


def main():
    parser = argparse.ArgumentParser(description="R393 — Classification des règles par domaine")
    parser.add_argument("--update", action="store_true", help="Écrire dans rule_corpus_index.json")
    args = parser.parse_args()

    corpus_path = Path("rules/rule_corpus_index.json")
    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)

    entries = corpus.get("entries", [])
    domain_counts: dict[str, int] = {}
    classified = 0
    already_classified = 0

    updated_entries = []
    for entry in entries:
        current_domain = entry.get("domain")
        if current_domain and current_domain != "?" and current_domain != "OTHER":
            already_classified += 1
            updated_entries.append(entry)
            domain_counts[current_domain] = domain_counts.get(current_domain, 0) + 1
            continue

        domain = classify_entry(entry)
        entry_copy = dict(entry)
        entry_copy["domain"] = domain
        entry_copy["domain_classified_by"] = "artcb_r393_auto"
        entry_copy["domain_classified_ts"] = time.time_ns()
        updated_entries.append(entry_copy)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        classified += 1

    summary = {
        "ts_ns": time.time_ns(),
        "total": len(entries),
        "classified": classified,
        "already_classified": already_classified,
        "domain_distribution": dict(sorted(domain_counts.items(), key=lambda x: -x[1])),
        "update_written": args.update,
    }

    # Rapport JSON
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    report_path = log_dir / "R393_rule_classification.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("[R393] Classification terminée:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"  {domain:15s}: {count:3d}")
    print(f"[R393] Total classifiés: {classified} / {len(entries)}")
    print(f"[R393] Rapport: {report_path}")

    if args.update:
        corpus["entries"] = updated_entries
        corpus["domain_classification_version"] = "R393"
        corpus["domain_classification_ts"] = time.time_ns()
        with open(corpus_path, "w", encoding="utf-8") as f:
            json.dump(corpus, f, indent=2, ensure_ascii=False)
        print(f"[R393] rule_corpus_index.json mis à jour ({len(updated_entries)} entrées)")
    else:
        print("[R393] Mode dry-run — passer --update pour écrire dans rule_corpus_index.json")


if __name__ == "__main__":
    main()
