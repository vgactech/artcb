#!/usr/bin/env python3
"""
R393 v2 — Classification multi-domaines + confidence score des règles ARTCB.
R394-E : chaque entrée reçoit `domains` (liste), `primary_domain`, `confidence` (0-1),
         `classification_basis` (liste des champs ayant contribué).

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

MODULE_VERSION = '1.1.0'  # R394-E — classification multi-domaines + confidence

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


KIND_FALLBACK: dict[str, str] = {
    "DECISION": "GOVERNANCE",
    "LESSON": "LESSONS",
    "CHECK": "TESTING",
    "CONVENTION": "PROTOCOL",
    "RULE": "PROTOCOL",
    "SPEC": "PROTOCOL",
    "QUESTION": "PROTOCOL",
    "EVIDENCE": "TESTING",
}


def classify_entry(entry: dict) -> dict:
    """Attribue des domaines multiples + confidence à une entrée du corpus.

    Retourne un dict avec :
      primary_domain : str
      domains        : list[str]  — tous les domaines avec score > 0
      confidence     : float [0, 1]
      classification_basis : list[str] — champs ayant contribué
    """
    # Champs à analyser
    fields: dict[str, str] = {
        "ref": str(entry.get("ref", "")),
        "source_path": str(entry.get("source_path", "")),
        "canonical_text": str(entry.get("canonical_text", "")),
        "kind": str(entry.get("kind", "")),
        "authority": str(entry.get("authority", "")),
        "corpus_id": str(entry.get("corpus_id", "")),
    }
    # Champs non-vides (pour classification_basis)
    non_empty = [k for k, v in fields.items() if v and v not in ("", "None")]
    text = " ".join(fields.values()).lower()

    scores: dict[str, int] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[domain] = score

    # Fallback kind si aucun score
    if not scores:
        kind = fields["kind"].upper()
        fallback_domain = KIND_FALLBACK.get(kind, "OTHER")
        return {
            "primary_domain": fallback_domain,
            "domains": [fallback_domain],
            "confidence": 0.4,  # confiance faible — fallback sur kind uniquement
            "classification_basis": ["kind"],
        }

    # Trier par score décroissant
    sorted_domains = sorted(scores.items(), key=lambda x: -x[1])
    top_score = sorted_domains[0][1]
    total_score = sum(s for _, s in sorted_domains)

    # Domaines avec score ≥ 50% du top
    threshold = max(1, top_score * 0.5)
    active_domains = [d for d, s in sorted_domains if s >= threshold]

    # Confidence = top_score / total_score (plus c'est concentré, plus c'est sûr)
    confidence = round(top_score / max(total_score, 1), 3)

    # Bonus confidence si canonical_text non vide
    if fields["canonical_text"] and len(fields["canonical_text"]) > 5:
        confidence = min(1.0, confidence + 0.15)

    # Pénalité si un seul champ a contribué
    if len(non_empty) <= 2:
        confidence = max(0.0, confidence - 0.1)

    return {
        "primary_domain": sorted_domains[0][0],
        "domains": active_domains,
        "confidence": confidence,
        "classification_basis": [k for k in non_empty if k != "kind"],
    }


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
    reclassified = 0
    confidence_sum = 0.0
    multi_domain_count = 0

    updated_entries = []
    for entry in entries:
        result = classify_entry(entry)
        entry_copy = dict(entry)

        # Toujours reclassifier (R394-E — on écrase même les entrées précédemment classifiées)
        prev_domain = entry.get("primary_domain") or entry.get("domain")
        if prev_domain and prev_domain == result["primary_domain"]:
            pass  # inchangé
        elif prev_domain:
            reclassified += 1

        # Champs multi-domaines R394-E
        entry_copy["primary_domain"] = result["primary_domain"]
        entry_copy["domains"] = result["domains"]
        entry_copy["confidence"] = result["confidence"]
        entry_copy["classification_basis"] = result["classification_basis"]
        entry_copy["domain_classified_by"] = "artcb_r393_v2"
        entry_copy["domain_classified_ts"] = time.time_ns()
        # Garder "domain" pour rétrocompatibilité
        entry_copy["domain"] = result["primary_domain"]

        updated_entries.append(entry_copy)
        domain_counts[result["primary_domain"]] = domain_counts.get(result["primary_domain"], 0) + 1
        classified += 1
        confidence_sum += result["confidence"]
        if len(result["domains"]) > 1:
            multi_domain_count += 1

    avg_confidence = round(confidence_sum / max(classified, 1), 3)

    summary = {
        "ts_ns": time.time_ns(),
        "version": "R393-v2-R394E",
        "total": len(entries),
        "classified": classified,
        "reclassified": reclassified,
        "multi_domain_count": multi_domain_count,
        "avg_confidence": avg_confidence,
        "domain_distribution": dict(sorted(domain_counts.items(), key=lambda x: -x[1])),
        "update_written": args.update,
    }

    # Rapport JSON
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    report_path = log_dir / "R393_rule_classification.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("[R393] Classification multi-domaines v2 (R394-E):")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"  {domain:15s}: {count:3d}")
    print(f"[R393] Total: {classified} | Multi-domaines: {multi_domain_count} | Confidence avg: {avg_confidence}")
    print(f"[R393] Rapport: {report_path}")

    if args.update:
        corpus["entries"] = updated_entries
        corpus["domain_classification_version"] = "R393-v2-R394E"
        corpus["domain_classification_ts"] = time.time_ns()
        with open(corpus_path, "w", encoding="utf-8") as f:
            json.dump(corpus, f, indent=2, ensure_ascii=False)
        print(f"[R393] rule_corpus_index.json mis à jour ({len(updated_entries)} entrées)")
    else:
        print("[R393] Mode dry-run — passer --update pour écrire dans rule_corpus_index.json")


if __name__ == "__main__":
    main()
