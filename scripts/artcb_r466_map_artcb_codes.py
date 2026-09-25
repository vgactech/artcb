#!/usr/bin/env python3
"""R466 — Script de mapping artcb_code sur les lexiques des 16 profils ARTCB.

Usage :
    python scripts/artcb_r466_map_artcb_codes.py [--lang LANG_ID] [--all-16] [--dry-run]

    --lang LANG_ID  : traiter un seul profil (ex: fr, en, es)
    --all-16        : traiter les 16 profils (par défaut si aucun flag)
    --dry-run       : afficher les stats sans écrire les fichiers mappés
    --lexicon-dir   : répertoire des lexiques (défaut: data/lexicons)
    --output-dir    : répertoire de sortie (défaut: data/lexicons_mapped)

Sortie :
    data/lexicons_mapped/{lang_id}_lexicon.json  (format identique + artcb_code mis à jour)
    logs/R466_mapping_stats.json                  (stats globales)

CERTIFIED_100=false — seules les ~360 clés de concept_lexicon.py sont couvertes.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ajouter la racine du projet au path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.artcb.language.lexicon_mapper import LexiconMapper, MapperStats
from src.artcb.language.registry import LanguageRegistry

ALL_16_LANG_IDS = LanguageRegistry.ALL_16_LANG_IDS

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("artcb.r466.script")

DEBUG_MODE = True  # PROTOCOLE ARTCB — mode DEBUG obligatoire

# ── Constantes ──────────────────────────────────────────────────────────────────

DEFAULT_LEXICON_DIR = PROJECT_ROOT / "data" / "lexicons"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "lexicons_mapped"
LOGS_DIR = PROJECT_ROOT / "logs"
STATS_LOG_PATH = LOGS_DIR / "R466_mapping_stats.json"
LEXICON_SUFFIX = "_lexicon.json"


# ── Traitement d'un profil ──────────────────────────────────────────────────────

def process_lang(
    lang_id: str,
    lexicon_dir: Path,
    output_dir: Path,
    mapper: LexiconMapper,
    dry_run: bool,
) -> dict:
    """Traite un profil linguistique : charge, mappe, écrit.

    Returns:
        dict de stats pour ce profil
    """
    src_path = lexicon_dir / f"{lang_id}{LEXICON_SUFFIX}"
    dst_path = output_dir / f"{lang_id}{LEXICON_SUFFIX}"

    if not src_path.exists():
        logger.warning("[R466][WARN] Fichier introuvable : %s — profil ignoré", src_path)
        return {"lang_id": lang_id, "status": "MISSING_FILE", "src_path": str(src_path)}

    logger.info("[R466][INFO] Traitement profil %s — lecture %s", lang_id, src_path)
    t0 = time.monotonic()

    # Lecture
    with open(src_path, encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    logger.info("[R466][INFO] %s : %d entrées à mapper", lang_id, len(entries))

    # Mapping
    updated_entries, stats = mapper.resolve_batch(entries)

    elapsed = time.monotonic() - t0
    logger.info(
        "[R466][INFO] %s : résolu=%d / total=%d (%.4f%%) en %.2fs",
        lang_id,
        stats.resolved,
        stats.total,
        stats.resolution_rate * 100,
        elapsed,
    )
    if DEBUG_MODE:
        logger.debug("[R466][DEBUG] %s stats détaillées: %s", lang_id, stats.summary())

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Réécriture du fichier avec artcb_code mis à jour
        data["entries"] = updated_entries
        data["r466_mapped"] = True
        data["r466_resolved_count"] = stats.resolved
        data["r466_unresolved_count"] = stats.unresolved
        data["r466_resolution_rate_pct"] = round(stats.resolution_rate * 100, 4)
        with open(dst_path, encoding="utf-8", mode="w") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        logger.info("[R466][INFO] %s : écrit → %s", lang_id, dst_path)
    else:
        logger.info("[R466][DRY-RUN] %s : pas d'écriture (dry-run)", lang_id)

    return {
        "lang_id": lang_id,
        "status": "OK",
        "total": stats.total,
        "resolved": stats.resolved,
        "unresolved": stats.unresolved,
        "resolution_rate_pct": round(stats.resolution_rate * 100, 4),
        "elapsed_seconds": round(elapsed, 3),
        "by_code": stats.by_code,
        "by_method": stats.by_method,
        "src_path": str(src_path),
        "dst_path": str(dst_path) if not dry_run else None,
    }


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="R466 — Mapping artcb_code sur les lexiques ARTCB 16 profils"
    )
    parser.add_argument("--lang", type=str, default=None, help="Traiter un seul profil")
    parser.add_argument("--all-16", action="store_true", help="Traiter les 16 profils (défaut)")
    parser.add_argument("--dry-run", action="store_true", help="Stats sans écriture")
    parser.add_argument(
        "--lexicon-dir",
        type=Path,
        default=DEFAULT_LEXICON_DIR,
        help=f"Répertoire source des lexiques (défaut: {DEFAULT_LEXICON_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Répertoire de sortie (défaut: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    # Sélection des langues à traiter
    if args.lang:
        langs = [args.lang]
    else:
        langs = list(ALL_16_LANG_IDS)

    logger.info("[R466][INFO] Lancement mapping — %d profil(s) : %s", len(langs), langs)
    logger.info("[R466][INFO] dry-run=%s | lexicon-dir=%s | output-dir=%s",
                args.dry_run, args.lexicon_dir, args.output_dir)

    mapper = LexiconMapper()
    t_global = time.monotonic()
    results = []

    for lang_id in langs:
        result = process_lang(lang_id, args.lexicon_dir, args.output_dir, mapper, args.dry_run)
        results.append(result)

    elapsed_global = time.monotonic() - t_global

    # Agrégation stats globales
    total_entries = sum(r.get("total", 0) for r in results)
    total_resolved = sum(r.get("resolved", 0) for r in results)
    total_unresolved = sum(r.get("unresolved", 0) for r in results)
    global_rate = (total_resolved / total_entries * 100) if total_entries > 0 else 0.0

    global_stats = {
        "r466_version": "1.0.0",
        "langs_processed": langs,
        "total_entries": total_entries,
        "total_resolved": total_resolved,
        "total_unresolved": total_unresolved,
        "global_resolution_rate_pct": round(global_rate, 4),
        "elapsed_seconds": round(elapsed_global, 3),
        "dry_run": args.dry_run,
        "per_lang": results,
    }

    # Log JSON
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(global_stats, f, ensure_ascii=False, indent=2)
    logger.info("[R466][INFO] Stats écrites → %s", STATS_LOG_PATH)

    # Résumé terminal
    logger.info(
        "[R466][RÉSUMÉ] Total=%d | Résolu=%d | UNK=%d | Taux=%.4f%% | Durée=%.1fs",
        total_entries, total_resolved, total_unresolved, global_rate, elapsed_global,
    )

    ok_count = sum(1 for r in results if r.get("status") == "OK")
    missing_count = sum(1 for r in results if r.get("status") == "MISSING_FILE")
    if missing_count > 0:
        logger.warning("[R466][WARN] %d profil(s) avec fichier manquant", missing_count)

    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
