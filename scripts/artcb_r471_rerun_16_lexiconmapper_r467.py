#!/usr/bin/env python3
"""R471 — Re-run complet 16 corpus avec LexiconMapper R467 (CORR-01/02/A-03).

Objectif : valider en conditions réelles que les corrections R467 s'appliquent
correctement sur les 21.5M entrées et produire un manifeste SHA-256 cohérent
avec HEAD git actuel.

Audit expert post-R467 a identifié les points à vérifier :
  (1) by_method complet par langue (exact_surface / exact_lemma / pos_filtered / collision)
  (2) pos_filtered = entrées grammaticales exclues — à quantifier par langue
  (3) Fermeture mathématique : entries = resolved + unresolved (toutes causes)
  (4) 18 clés collision tracées — N occurrences publiées (pas seulement nb clés)
  (5) Manifeste git_sha = HEAD actuel (L-053)

Usage :
    python scripts/artcb_r471_rerun_16_lexiconmapper_r467.py [--dry-run] [--lang LANG_ID]

    --dry-run     : stats sans réécriture des fichiers mappés
    --lang        : traiter un seul profil

Sorties :
    data/lexicons_mapped/{lang}_lexicon.json  (fichiers remappés — mise à jour sur place)
    logs/R471_mapping_stats.json              (stats détaillées + manifeste)

CERTIFIED_100=false — seules les ~360 clés concept_lexicon.py sont couvertes.
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

from src.artcb.language.lexicon_mapper import (
    LexiconMapper,
    MapperStats,
    MODULE_VERSION as MAPPER_VERSION,
    _COLLISION_OBJECT_OVER_MODIFIER,
)
from src.artcb.language.registry import LanguageRegistry

# ── Constantes ─────────────────────────────────────────────────────────────────

ALL_16 = list(LanguageRegistry.ALL_16_LANG_IDS)
LEXICON_DIR = PROJECT_ROOT / "data" / "lexicons"
OUTPUT_DIR = PROJECT_ROOT / "data" / "lexicons_mapped"
LOGS_DIR = PROJECT_ROOT / "logs"
STATS_PATH = LOGS_DIR / "R471_mapping_stats.json"
LEXICON_SUFFIX = "_lexicon.json"

R471_VERSION = "1.0.0"
DEBUG_MODE = True  # PROTOCOLE ARTCB — mode DEBUG obligatoire

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("artcb.r471")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    """Calcule SHA-256 d'un fichier (streaming 64 KB)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> str:
    """Retourne le SHA complet de HEAD (40 hex) ou 'UNKNOWN' en cas d'erreur."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


# ── Traitement d'un profil ──────────────────────────────────────────────────────

def process_lang(
    lang_id: str,
    mapper: LexiconMapper,
    dry_run: bool,
) -> dict:
    """Charge, re-mappe et écrit un profil linguistique.

    Audit expert R467 — données exposées :
      - by_method        : répartition des RÉSOLUS par méthode
      - by_method_unresolved : répartition des UNK par cause (incl. pos_filtered)
      - pos_filtered_count   : raccourci pour les exclusions CORR-01
      - collision_count      : occurrences (pas seulement nb clés) CORR-02
      - fermeture            : assert entries == resolved + unresolved

    Returns:
        dict de stats pour ce profil
    """
    src_path = LEXICON_DIR / f"{lang_id}{LEXICON_SUFFIX}"
    dst_path = OUTPUT_DIR / f"{lang_id}{LEXICON_SUFFIX}"

    if not src_path.exists():
        logger.warning("[R471][WARN] Fichier absent : %s — profil ignoré", src_path)
        return {"lang_id": lang_id, "status": "MISSING_FILE"}

    logger.info("[R471][INFO] ── Profil %s — lecture %s", lang_id, src_path)
    t0 = time.monotonic()
    src_sha = _sha256_file(src_path)

    with open(src_path, encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    n_entries = len(entries)
    logger.info("[R471][INFO] %s : %d entrées chargées", lang_id, n_entries)

    # Re-mapping avec LexiconMapper R467 (CORR-01/02/A-03)
    updated_entries, stats = mapper.resolve_batch(entries)

    elapsed = time.monotonic() - t0

    # ── Fermeture mathématique (audit expert) ──────────────────────────────────
    # entries = resolved + unresolved (toutes causes confondues)
    closure_ok = (stats.resolved + stats.unresolved) == stats.total == n_entries
    if not closure_ok:
        logger.error(
            "[R471][ERROR] %s — Fermeture KO : entries=%d resolved=%d unresolved=%d "
            "(resolved+unresolved=%d)",
            lang_id, n_entries, stats.resolved, stats.unresolved,
            stats.resolved + stats.unresolved,
        )
    else:
        logger.debug(
            "[R471][DEBUG] %s — Fermeture OK : %d = %d + %d",
            lang_id, n_entries, stats.resolved, stats.unresolved,
        )

    # ── Stats complètes (audit expert) ────────────────────────────────────────
    summary = stats.summary()
    pos_filtered = summary["pos_filtered_count"]
    collision_occurrences = summary["collision_count"]

    logger.info(
        "[R471][INFO] %s : résolu=%d UNK=%d pos_filtered=%d collisions=%d "
        "(rate=%.4f%%) en %.2fs",
        lang_id,
        stats.resolved, stats.unresolved,
        pos_filtered, collision_occurrences,
        stats.resolution_rate * 100,
        elapsed,
    )
    if DEBUG_MODE:
        logger.debug("[R471][DEBUG] %s by_method=%s", lang_id, summary["by_method"])
        logger.debug("[R471][DEBUG] %s by_method_unresolved=%s", lang_id, summary["by_method_unresolved"])

    dst_sha = None
    if not dry_run:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # Mise à jour du fichier avec métadonnées R471
        data["entries"] = updated_entries
        data["r466_mapped"] = True  # compat ascendante
        data["r467_remapped"] = True  # R471 : re-run avec corrections R467
        data["r471_resolved_count"] = stats.resolved
        data["r471_unresolved_count"] = stats.unresolved
        data["r471_pos_filtered_count"] = pos_filtered
        data["r471_collision_count"] = collision_occurrences
        data["r471_resolution_rate_pct"] = round(stats.resolution_rate * 100, 6)
        data["r471_mapper_version"] = MAPPER_VERSION
        with open(dst_path, encoding="utf-8", mode="w") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        dst_sha = _sha256_file(dst_path)
        dst_size = dst_path.stat().st_size
        logger.info("[R471][INFO] %s : écrit → %s (SHA=%s…)", lang_id, dst_path, dst_sha[:16])
    else:
        logger.info("[R471][DRY-RUN] %s : pas d'écriture (dry-run)", lang_id)
        dst_size = 0

    return {
        "lang_id": lang_id,
        "status": "OK" if closure_ok else "CLOSURE_ERROR",
        "closure_ok": closure_ok,
        "entries": n_entries,
        "resolved": stats.resolved,
        "unresolved": stats.unresolved,
        "pos_filtered_count": pos_filtered,
        "collision_occurrences": collision_occurrences,
        "resolution_rate_pct": round(stats.resolution_rate * 100, 6),
        "by_method": summary["by_method"],
        "by_method_unresolved": summary["by_method_unresolved"],
        "by_code": summary["by_code"],
        "elapsed_seconds": round(elapsed, 3),
        "src_sha256": src_sha,
        "dst_sha256": dst_sha,
        "dst_size_bytes": dst_size,
    }


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="R471 — Re-run 16 corpus LexiconMapper R467"
    )
    parser.add_argument("--dry-run", action="store_true", help="Stats sans écriture")
    parser.add_argument("--lang", type=str, default=None, help="Traiter un seul profil")
    args = parser.parse_args()

    langs = [args.lang] if args.lang else ALL_16

    logger.info("[R471][INFO] ══════════════════════════════════════════════")
    logger.info("[R471][INFO] R471 — Re-run %d profil(s) avec LexiconMapper %s",
                len(langs), MAPPER_VERSION)
    logger.info("[R471][INFO] CORR-01: filtre POS | CORR-02: collisions tracées | A-03: no-prefix-batch")
    logger.info("[R471][INFO] dry-run=%s | nb_collision_keys=%d", args.dry_run, len(_COLLISION_OBJECT_OVER_MODIFIER))

    git_sha = _git_head()
    logger.info("[R471][INFO] git HEAD = %s", git_sha)

    mapper = LexiconMapper()
    t_global = time.monotonic()
    per_lang = []

    for i, lang_id in enumerate(langs, 1):
        logger.info("[R471][INFO] ── [%d/%d] %s ──────────────────────────────", i, len(langs), lang_id)
        result = process_lang(lang_id, mapper, args.dry_run)
        per_lang.append(result)

    elapsed_global = time.monotonic() - t_global

    # ── Agrégation globale ─────────────────────────────────────────────────────
    total_entries = sum(r.get("entries", 0) for r in per_lang)
    total_resolved = sum(r.get("resolved", 0) for r in per_lang)
    total_unresolved = sum(r.get("unresolved", 0) for r in per_lang)
    total_pos_filtered = sum(r.get("pos_filtered_count", 0) for r in per_lang)
    total_collisions = sum(r.get("collision_occurrences", 0) for r in per_lang)
    global_rate = (total_resolved / total_entries * 100) if total_entries else 0.0
    closure_all_ok = all(r.get("closure_ok", False) for r in per_lang if r.get("status") != "MISSING_FILE")

    # Agrégation by_method globale
    global_by_method: dict[str, int] = {}
    global_by_method_unk: dict[str, int] = {}
    global_by_code: dict[str, int] = {}
    for r in per_lang:
        for k, v in r.get("by_method", {}).items():
            global_by_method[k] = global_by_method.get(k, 0) + v
        for k, v in r.get("by_method_unresolved", {}).items():
            global_by_method_unk[k] = global_by_method_unk.get(k, 0) + v
        for k, v in r.get("by_code", {}).items():
            global_by_code[k] = global_by_code.get(k, 0) + v

    # ── Manifeste JSON (résout R469b A-04 : git_sha = HEAD actuel) ─────────────
    manifest = {
        "r471_version": R471_VERSION,
        "mapper_version": MAPPER_VERSION,
        "git_sha": git_sha,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dry_run": args.dry_run,
        "algorithm": "resolve_batch(): exact_surface O(1) | exact_lemma O(1) | UNK (no prefix in batch)",
        "corr01_pos_filter": True,
        "corr02_collision_trace": True,
        "a03_no_prefix_batch": True,
        "collision_keys_count": len(_COLLISION_OBJECT_OVER_MODIFIER),
        "langs_processed": langs,
        "total_entries": total_entries,
        "total_resolved": total_resolved,
        "total_unresolved": total_unresolved,
        "total_pos_filtered": total_pos_filtered,
        "total_collision_occurrences": total_collisions,
        "global_resolution_rate_pct": round(global_rate, 6),
        "global_by_method": dict(sorted(global_by_method.items(), key=lambda x: -x[1])),
        "global_by_method_unresolved": dict(sorted(global_by_method_unk.items(), key=lambda x: -x[1])),
        "global_by_code": dict(sorted(global_by_code.items(), key=lambda x: -x[1])),
        "closure_all_ok": closure_all_ok,
        "elapsed_total_seconds": round(elapsed_global, 3),
        "per_lang": {r["lang_id"]: r for r in per_lang},
    }

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info("[R471][INFO] Stats écrites → %s", STATS_PATH)

    # ── Résumé terminal ────────────────────────────────────────────────────────
    logger.info("[R471][INFO] ══════════════════════════════════════════════")
    logger.info("[R471][INFO] R471 TERMINÉ — %d profils | %d entrées total",
                len(langs), total_entries)
    logger.info("[R471][INFO]   résolu=%d  UNK=%d  pos_filtered=%d  collisions=%d",
                total_resolved, total_unresolved, total_pos_filtered, total_collisions)
    logger.info("[R471][INFO]   rate=%.6f%%  closure=%s  durée=%.1fs",
                global_rate, "OK" if closure_all_ok else "ERROR", elapsed_global)
    logger.info("[R471][INFO]   git_sha=%s", git_sha)

    # Erreurs éventuelles
    errors = [r for r in per_lang if not r.get("closure_ok", True)]
    if errors:
        logger.error("[R471][ERROR] %d profil(s) avec erreur de fermeture : %s",
                     len(errors), [r["lang_id"] for r in errors])
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
