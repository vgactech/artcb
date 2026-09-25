#!/usr/bin/env python3
"""R466b — Exécution complète --all-16 : mapping artcb_code + écriture lexicons_mapped/ + manifeste.

Usage :
    python scripts/artcb_r466b_all16_write.py [--lang LANG_ID] [--all-16] [--manifest-only]

    --lang LANG_ID   : traiter un seul profil
    --all-16         : traiter les 16 profils (défaut)
    --manifest-only  : recalculer le manifeste sans re-mapper (lecture data/lexicons_mapped/)
    --lexicon-dir    : répertoire source (défaut: data/lexicons)
    --output-dir     : répertoire de sortie (défaut: data/lexicons_mapped)

Sorties :
    data/lexicons_mapped/{lang_id}_lexicon.json  — lexique avec artcb_code résolu
    logs/R466b_manifest.json                     — manifeste cryptographique (SHA-256 par fichier)
    logs/R466b_run_stats.json                    — statistiques détaillées par profil

Format manifeste :
    {
      "git_sha": "...",
      "r466b_version": "1.0.0",
      "per_lang": {
        "fr": {
          "src_sha256": "...",  SHA-256 du fichier source
          "dst_sha256": "...",  SHA-256 du fichier de sortie
          "entries": 784019,
          "resolved": 448,
          "unresolved": 774105,
          "resolution_rate_pct": 0.0571,
          "elapsed_seconds": 1.48
        }, ...
      },
      "global": { ... }
    }

CERTIFIED_100=false
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.artcb.language.lexicon_mapper import LexiconMapper, MODULE_VERSION as MAPPER_VERSION
from src.artcb.language.registry import LanguageRegistry

ALL_16_LANG_IDS = LanguageRegistry.ALL_16_LANG_IDS

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("artcb.r466b")

DEBUG_MODE = True  # PROTOCOLE ARTCB

# ── Constantes ──────────────────────────────────────────────────────────────────

DEFAULT_LEXICON_DIR = PROJECT_ROOT / "data" / "lexicons"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "lexicons_mapped"
LOGS_DIR = PROJECT_ROOT / "logs"
MANIFEST_PATH = LOGS_DIR / "R466b_manifest.json"
STATS_PATH = LOGS_DIR / "R466b_run_stats.json"
LEXICON_SUFFIX = "_lexicon.json"

R466B_VERSION = "1.0.0"


# ── Utilitaires ────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    """Calcule le SHA-256 d'un fichier en streaming (compatible gros fichiers)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):  # chunks 1 MB
            h.update(chunk)
    return h.hexdigest()


def git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "UNKNOWN"


# ── Traitement d'un profil ──────────────────────────────────────────────────────

def process_lang(
    lang_id: str,
    lexicon_dir: Path,
    output_dir: Path,
    mapper: LexiconMapper,
    manifest_only: bool,
) -> dict:
    """Traite un profil : charge, mappe, écrit, calcule SHA-256 src+dst.

    Returns dict de résultats pour ce profil.
    """
    src_path = lexicon_dir / f"{lang_id}{LEXICON_SUFFIX}"
    dst_path = output_dir / f"{lang_id}{LEXICON_SUFFIX}"

    if not src_path.exists():
        logger.warning("[R466b][WARN] %s : fichier source manquant %s", lang_id, src_path)
        return {"lang_id": lang_id, "status": "MISSING_SRC"}

    if manifest_only:
        # Recalcul manifeste seul — lire les stats du fichier de sortie existant
        if not dst_path.exists():
            return {"lang_id": lang_id, "status": "MISSING_DST_MANIFEST_ONLY"}
        logger.info("[R466b][MANIFEST] %s : recalcul SHA-256 src + dst", lang_id)
        src_sha = sha256_file(src_path)
        dst_sha = sha256_file(dst_path)
        with open(dst_path, encoding="utf-8") as f:
            dst_data = json.load(f)
        return {
            "lang_id": lang_id,
            "status": "MANIFEST_ONLY",
            "src_sha256": src_sha,
            "dst_sha256": dst_sha,
            "entries": dst_data.get("entry_count", 0),
            "resolved": dst_data.get("r466_resolved_count", 0),
            "unresolved": dst_data.get("r466_unresolved_count", 0),
            "resolution_rate_pct": dst_data.get("r466_resolution_rate_pct", 0.0),
            "elapsed_seconds": None,
            "src_path": str(src_path),
            "dst_path": str(dst_path),
            "dst_size_bytes": dst_path.stat().st_size,
        }

    logger.info("[R466b][INFO] %s : lecture %s (%.1f MB)", lang_id, src_path, src_path.stat().st_size / 1e6)

    # SHA-256 source avant modification
    t_sha = time.monotonic()
    src_sha = sha256_file(src_path)
    logger.info("[R466b][INFO] %s : SHA-256 src en %.2fs → %s...", lang_id, time.monotonic() - t_sha, src_sha[:12])

    # Chargement
    t_load = time.monotonic()
    with open(src_path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries", [])
    logger.info("[R466b][INFO] %s : %d entrées chargées en %.2fs", lang_id, len(entries), time.monotonic() - t_load)

    # Mapping
    t_map = time.monotonic()
    updated_entries, stats = mapper.resolve_batch(entries)
    elapsed_map = time.monotonic() - t_map
    logger.info(
        "[R466b][INFO] %s : mapping terminé — résolu=%d/%d (%.4f%%) en %.2fs",
        lang_id, stats.resolved, stats.total, stats.resolution_rate * 100, elapsed_map,
    )

    # Écriture
    output_dir.mkdir(parents=True, exist_ok=True)
    data["entries"] = updated_entries
    data["r466_mapped"] = True
    data["r466_mapper_version"] = MAPPER_VERSION
    data["r466_resolved_count"] = stats.resolved
    data["r466_unresolved_count"] = stats.unresolved
    data["r466_resolution_rate_pct"] = round(stats.resolution_rate * 100, 6)
    data["r466_by_method"] = stats.by_method
    data["r466_by_code"] = dict(sorted(stats.by_code.items(), key=lambda x: -x[1]))

    t_write = time.monotonic()
    with open(dst_path, encoding="utf-8", mode="w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    elapsed_write = time.monotonic() - t_write
    logger.info("[R466b][INFO] %s : écrit %s (%.1f MB) en %.2fs", lang_id, dst_path, dst_path.stat().st_size / 1e6, elapsed_write)

    # SHA-256 destination
    t_sha_dst = time.monotonic()
    dst_sha = sha256_file(dst_path)
    logger.info("[R466b][INFO] %s : SHA-256 dst en %.2fs → %s...", lang_id, time.monotonic() - t_sha_dst, dst_sha[:12])

    elapsed_total = elapsed_map + elapsed_write
    return {
        "lang_id": lang_id,
        "status": "OK",
        "src_sha256": src_sha,
        "dst_sha256": dst_sha,
        "entries": stats.total,
        "resolved": stats.resolved,
        "unresolved": stats.unresolved,
        "resolution_rate_pct": round(stats.resolution_rate * 100, 6),
        "elapsed_map_seconds": round(elapsed_map, 4),
        "elapsed_write_seconds": round(elapsed_write, 4),
        "elapsed_total_seconds": round(elapsed_total, 4),
        "by_method": stats.by_method,
        "by_code": dict(sorted(stats.by_code.items(), key=lambda x: -x[1])),
        "src_path": str(src_path),
        "dst_path": str(dst_path),
        "dst_size_bytes": dst_path.stat().st_size,
    }


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="R466b — Mapping all-16 + manifeste hashes")
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--all-16", action="store_true")
    parser.add_argument("--manifest-only", action="store_true", help="Recalcul manifeste sans re-mapper")
    parser.add_argument("--lexicon-dir", type=Path, default=DEFAULT_LEXICON_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    langs = [args.lang] if args.lang else list(ALL_16_LANG_IDS)
    sha = git_head()

    logger.info("[R466b][INFO] Lancement — SHA=%s | %d profil(s) | manifest_only=%s",
                sha[:12], len(langs), args.manifest_only)

    mapper = LexiconMapper()
    t_global = time.monotonic()
    results = []

    for lang_id in langs:
        result = process_lang(lang_id, args.lexicon_dir, args.output_dir, mapper, args.manifest_only)
        results.append(result)

    elapsed_global = time.monotonic() - t_global

    # Agrégation
    ok_results = [r for r in results if r.get("status") in ("OK", "MANIFEST_ONLY")]
    total_entries = sum(r.get("entries", 0) for r in ok_results)
    total_resolved = sum(r.get("resolved", 0) for r in ok_results)
    total_unresolved = sum(r.get("unresolved", 0) for r in ok_results)
    global_rate = (total_resolved / total_entries * 100) if total_entries > 0 else 0.0

    # Manifeste cryptographique
    manifest = {
        "r466b_version": R466B_VERSION,
        "mapper_version": MAPPER_VERSION,
        "git_sha": sha,
        "algorithm": "resolve_batch(): exact_surface O(1) | exact_lemma O(1) | UNK",
        "langs_processed": langs,
        "total_entries": total_entries,
        "total_resolved": total_resolved,
        "total_unresolved": total_unresolved,
        "global_resolution_rate_pct": round(global_rate, 6),
        "elapsed_total_seconds": round(elapsed_global, 3),
        "manifest_only": args.manifest_only,
        "per_lang": {
            r["lang_id"]: {
                "status": r.get("status"),
                "src_sha256": r.get("src_sha256"),
                "dst_sha256": r.get("dst_sha256"),
                "entries": r.get("entries"),
                "resolved": r.get("resolved"),
                "unresolved": r.get("unresolved"),
                "resolution_rate_pct": r.get("resolution_rate_pct"),
                "by_method": r.get("by_method"),
                "dst_size_bytes": r.get("dst_size_bytes"),
            }
            for r in results
        },
    }

    # Stats détaillées
    run_stats = {
        "r466b_version": R466B_VERSION,
        "git_sha": sha,
        "langs": langs,
        "results": results,
        "global": {
            "total_entries": total_entries,
            "total_resolved": total_resolved,
            "total_unresolved": total_unresolved,
            "global_resolution_rate_pct": round(global_rate, 6),
            "elapsed_total_seconds": round(elapsed_global, 3),
        },
    }

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(run_stats, f, ensure_ascii=False, indent=2)

    logger.info("[R466b][INFO] Manifeste → %s", MANIFEST_PATH)
    logger.info("[R466b][INFO] Stats     → %s", STATS_PATH)
    logger.info(
        "[R466b][RÉSUMÉ] %d/%d OK | total=%d | résolu=%d (%.4f%%) | %.1fs",
        len(ok_results), len(langs), total_entries, total_resolved, global_rate, elapsed_global,
    )

    missing = [r for r in results if r.get("status") not in ("OK", "MANIFEST_ONLY")]
    if missing:
        logger.warning("[R466b][WARN] %d profil(s) en erreur : %s", len(missing), [r["lang_id"] for r in missing])

    return 0 if len(ok_results) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
