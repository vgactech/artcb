#!/usr/bin/env python3
"""R465/R465-ext — ARTCB Lexicon Builder : téléchargement et extraction des dictionnaires.

Directive R464 : 100% des mots de chacune des 16 langues dans la bibliothèque
du Langage IA ARTCB — sans exception, sans résumé, sans diminution.

Extension R465-ext : +2 profils linguistiques (Latin `la` + Português Brasileiro `pt-BR`).
  - Latin     : kaikki.org/Latin JSONL (DEPRECATED kaikki, accessible et fonctionnel)
  - pt-BR     : GitHub fserb/pt-br wordlist (145 744 mots) — kaikki.org n'a pas de dump pt-BR séparé

Source canonique : kaikki.org (dumps JSONL pré-parsés depuis Wiktionary).
Format de sortie : data/lexicons/{lang_id}_lexicon.json
  {
    "lang_id": "fr",
    "lang_name_en": "French",
    "source": "kaikki.org-wiktionary",
    "source_url": "https://kaikki.org/dictionary/French/...",
    "build_date": "...",
    "entry_count": N,
    "entries": [
      {"surface_form": "...", "lemma": "...", "pos": "...", "artcb_code": ""},
      ...
    ]
  }

artcb_code est laissé vide (""): il sera assigné par l'encodeur IR lors de la
résolution sémantique. Ce fichier est le LEXIQUE pur (surface_form + lemma + pos).

Usage :
    python3 scripts/artcb_r465_lexicon_build.py [--lang fr] [--all] [--test] [--all-16]

Mode --test    : extrait les 5000 premières entrées brutes par langue (validation pipeline).
Mode --all     : télécharge les 14 langues initiales (R465).
Mode --all-16  : télécharge les 16 profils (14 + la + pt-BR).

CERTIFIED_100=false — les données sont authentiques (kaikki.org/Wiktionary)
mais la couverture dépend de Wiktionary, qui n'est pas exhaustif pour toutes
les langues. C'est la meilleure source libre disponible.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Iterator

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s][%(levelname)s][R465] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("artcb.r465.lexicon_build")

# ── Configuration des 16 profils linguistiques ────────────────────────────────
# Source canonique : kaikki.org — pages dictionary par langue
# URL pattern : https://kaikki.org/dictionary/{EnglishName}/kaikki.org-dictionary-{EnglishName}.jsonl
# Source alternative pt-BR : GitHub fserb/pt-br (wordlist texte, pas JSONL)

LANG_CONFIG = {
    "fr": {
        "name_en": "French",
        "script": "Latin",
        "kaikki_name": "French",
        "omw_code": "fra",
    },
    "en": {
        "name_en": "English",
        "script": "Latin",
        "kaikki_name": "English",
        "omw_code": "eng",
    },
    "es": {
        "name_en": "Spanish",
        "script": "Latin",
        "kaikki_name": "Spanish",
        "omw_code": "spa",
    },
    "pt": {
        "name_en": "Portuguese",
        "script": "Latin",
        "kaikki_name": "Portuguese",
        "omw_code": "por",
    },
    "it": {
        "name_en": "Italian",
        "script": "Latin",
        "kaikki_name": "Italian",
        "omw_code": "ita",
    },
    "ru": {
        "name_en": "Russian",
        "script": "Cyrillic",
        "kaikki_name": "Russian",
        "omw_code": "rus",
    },
    "zh": {
        "name_en": "Chinese",
        "script": "CJK",
        "kaikki_name": "Chinese",
        "omw_code": "cmn",
    },
    "ar": {
        "name_en": "Arabic",
        "script": "Arabic",
        "kaikki_name": "Arabic",
        "omw_code": "arb",
    },
    "de": {
        "name_en": "German",
        "script": "Latin",
        "kaikki_name": "German",
        "omw_code": "deu",
    },
    "id": {
        "name_en": "Indonesian",
        "script": "Latin",
        "kaikki_name": "Indonesian",
        "omw_code": "ind",
    },
    "ja": {
        "name_en": "Japanese",
        "script": "CJK+Kana",
        "kaikki_name": "Japanese",
        "omw_code": "jpn",
    },
    "ko": {
        "name_en": "Korean",
        "script": "Hangul",
        "kaikki_name": "Korean",
        "omw_code": "kor",
    },
    "pl": {
        "name_en": "Polish",
        "script": "Latin",
        "kaikki_name": "Polish",
        "omw_code": "pol",
    },
    "tr": {
        "name_en": "Turkish",
        "script": "Latin",
        "kaikki_name": "Turkish",
        "omw_code": "tur",
    },
    # ── Profils étendus R465-ext ───────────────────────────────────────────────
    # Latin : kaikki.org/Latin JSONL — DEPRECATED (annoncé retiré) mais actuellement accessible (1.2 GB)
    # Marqué DEPRECATED sur kaikki.org (issue wiktextract #1178) — à surveiller
    "la": {
        "name_en": "Latin",
        "script": "Latin",
        "kaikki_name": "Latin",
        "omw_code": "lat",
        "deprecated_warning": "kaikki.org/Latin est marqué DEPRECATED — peut être retiré prochainement",
    },
    # Português Brasileiro : pas de dump kaikki.org pt-BR séparé
    # Source : GitHub fserb/pt-br — wordlist open-source (145 744 mots lemmesés)
    # URL : https://raw.githubusercontent.com/fserb/pt-br/master/wordlist.txt (plain text, un mot par ligne)
    # Alternative : LanguageTool portuguese-pos-dict (plus riche mais format différent)
    "pt-BR": {
        "name_en": "Portuguese (Brazil)",
        "script": "Latin",
        "kaikki_name": None,  # pas de dump kaikki.org pt-BR — source alternative
        "omw_code": "por",
        "alt_source": "github_fserb_ptbr",
        "alt_source_url": "https://raw.githubusercontent.com/fserb/pt-br/master/wordlist.txt",
        "alt_source_note": (
            "fserb/pt-br — wordlist plain text 145 744 mots lemmatisés. "
            "Licence : MIT. Pas de POS ni de formes fléchies dans ce corpus. "
            "artcb_code=UNK, pos=unknown pour toutes les entrées."
        ),
    },
}

# IDs des 16 profils complets (ordre de build recommandé)
ALL_16_LANG_IDS = list(LANG_CONFIG.keys())

# IDs des 14 langues initiales R465 (sans la et pt-BR)
INITIAL_14_LANG_IDS = [k for k in LANG_CONFIG if k not in ("la", "pt-BR")]

KAIKKI_BASE = "https://kaikki.org/dictionary/{name}/kaikki.org-dictionary-{name}.jsonl"
OUTPUT_DIR = Path("data/lexicons")

# ── Source alternative pt-BR ───────────────────────────────────────────────────
PTBR_WORDLIST_URL = "https://raw.githubusercontent.com/fserb/pt-br/master/wordlist.txt"

# ── Téléchargement streaming ───────────────────────────────────────────────────

def _build_url(kaikki_name: str) -> str:
    return KAIKKI_BASE.format(name=kaikki_name)


def _stream_jsonl(url: str, max_entries: int = 0) -> Iterator[dict]:
    """Télécharge et parse le JSONL en streaming (sans tout charger en mémoire).

    Args:
        url: URL du fichier JSONL kaikki.org
        max_entries: 0 = toutes les entrées, N = s'arrêter après N entrées
    """
    logger.debug("Connexion à %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "ARTCB-LexiconBuilder/R465"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            count = 0
            buf = b""
            chunk_size = 65536  # 64KB chunks
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                buf += chunk
                lines = buf.split(b"\n")
                buf = lines[-1]  # garder le fragment incomplet
                for line in lines[:-1]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        yield entry
                        count += 1
                        if count % 10000 == 0:
                            logger.debug("  %d entrées lues...", count)
                        if max_entries > 0 and count >= max_entries:
                            return
                    except json.JSONDecodeError:
                        continue
            # Traiter le dernier fragment
            if buf.strip():
                try:
                    yield json.loads(buf)
                except json.JSONDecodeError:
                    pass
    except Exception as exc:
        logger.error("Erreur téléchargement %s : %s", url, exc)
        raise


# ── Téléchargement plain-text (pt-BR wordlist) ────────────────────────────────

def _stream_plaintext_words(url: str, max_entries: int = 0) -> Iterator[str]:
    """Télécharge une wordlist plain-text (un mot par ligne) en streaming.

    Utilisé pour pt-BR (fserb/pt-br) qui n'a pas de format JSONL.
    """
    logger.debug("Connexion wordlist plain-text : %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "ARTCB-LexiconBuilder/R465"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            count = 0
            buf = b""
            chunk_size = 65536
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                buf += chunk
                lines = buf.split(b"\n")
                buf = lines[-1]
                for line in lines[:-1]:
                    word = line.strip().decode("utf-8", errors="replace")
                    if not word or word.startswith("#"):
                        continue
                    yield word
                    count += 1
                    if count % 10000 == 0:
                        logger.debug("  %d mots lus...", count)
                    if max_entries > 0 and count >= max_entries:
                        return
            # Traiter le dernier fragment
            if buf.strip():
                word = buf.strip().decode("utf-8", errors="replace")
                if word and not word.startswith("#"):
                    yield word
    except Exception as exc:
        logger.error("Erreur téléchargement plain-text %s : %s", url, exc)
        raise


# ── Extraction des lemmes ──────────────────────────────────────────────────────

def _extract_lemma(entry: dict) -> str | None:
    """Extrait la forme canonique (lemme) depuis une entrée kaikki."""
    # kaikki.org fournit le champ "word" = forme de surface de l'entrée
    word = entry.get("word", "").strip()
    if not word:
        return None
    # Filtrer les entrées trop courtes ou contenant uniquement des chiffres
    if len(word) < 1:
        return None
    return word


def _extract_pos(entry: dict) -> str:
    """Extrait la partie du discours (POS) depuis une entrée kaikki."""
    return entry.get("pos", "unknown")


def _extract_forms(entry: dict) -> list[str]:
    """Extrait les formes fléchies depuis une entrée kaikki (formes = surface_forms)."""
    forms = []
    for form_entry in entry.get("forms", []):
        form = form_entry.get("form", "").strip()
        if form and form not in forms:
            forms.append(form)
    return forms


# ── Construction du lexique d'une langue ──────────────────────────────────────

def build_lexicon_for_lang(
    lang_id: str,
    config: dict,
    output_dir: Path,
    max_entries: int = 0,
    force: bool = False,
) -> dict:
    """Télécharge et construit le lexique complet d'une langue.

    Returns:
        dict avec les statistiques : entry_count, form_count, output_path
    """
    output_path = output_dir / f"{lang_id}_lexicon.json"

    if output_path.exists() and not force:
        logger.info("[%s] Fichier lexique déjà présent : %s — skip (utiliser --force)", lang_id, output_path)
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        return {
            "lang_id": lang_id,
            "entry_count": existing.get("entry_count", 0),
            "output_path": str(output_path),
            "status": "skipped_existing",
        }

    url = _build_url(config["kaikki_name"])
    logger.info("[%s] Début téléchargement depuis %s", lang_id, url)
    t_start = time.time()

    # Ensemble des lemmes uniques (évite les doublons)
    seen_lemmas: set[str] = set()
    entries_out: list[dict] = []
    raw_entry_count = 0

    try:
        for raw_entry in _stream_jsonl(url, max_entries=max_entries):
            raw_entry_count += 1
            lemma = _extract_lemma(raw_entry)
            if not lemma:
                continue
            pos = _extract_pos(raw_entry)
            forms = _extract_forms(raw_entry)

            # Entrée principale : le lemme lui-même
            key = f"{lemma}|{pos}"
            if key not in seen_lemmas:
                seen_lemmas.add(key)
                entries_out.append({
                    "surface_form": lemma,
                    "lemma": lemma,
                    "pos": pos,
                    "artcb_code": "",  # assigné par l'encodeur IR
                    "source": "kaikki.org-wiktionary",
                    "forms_count": len(forms),
                })

            # Formes fléchies : chaque forme est aussi un surface_form
            for form in forms:
                fkey = f"{form}|{pos}|form"
                if form != lemma and fkey not in seen_lemmas:
                    seen_lemmas.add(fkey)
                    entries_out.append({
                        "surface_form": form,
                        "lemma": lemma,  # pointe vers le lemme canonique
                        "pos": pos,
                        "artcb_code": "",
                        "source": "kaikki.org-wiktionary",
                        "forms_count": 0,
                    })

    except Exception as exc:
        logger.error("[%s] Erreur durant extraction : %s", lang_id, exc)
        raise

    elapsed = time.time() - t_start
    entry_count = len(entries_out)
    logger.info(
        "[%s] Extraction terminée : %d entrées brutes → %d lemmes+formes uniques en %.1fs",
        lang_id, raw_entry_count, entry_count, elapsed,
    )

    # Construction du document final
    build_date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "lang_id": lang_id,
        "lang_name_en": config["name_en"],
        "script": config["script"],
        "source": "kaikki.org-wiktionary",
        "source_url": url,
        "build_date": build_date,
        "build_duration_seconds": round(elapsed, 1),
        "raw_entry_count": raw_entry_count,
        "entry_count": entry_count,
        "max_entries_cap": max_entries if max_entries > 0 else "unlimited",
        "certified_100": False,
        "note": (
            "Données issues de kaikki.org (Wiktionary pré-parsé). "
            "Couverture = couverture Wiktionary de la langue. "
            "artcb_code vide = à assigner par l'encodeur IR ARTCB. "
            "CERTIFIED_100=false."
        ),
        "entries": entries_out,
    }

    # Écriture du fichier (UTF-8, pas d'ASCII escape pour préserver les caractères natifs)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    output_path.chmod(0o644)

    # Hash SHA-256 du fichier produit
    sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
    size_mb = output_path.stat().st_size / (1024 * 1024)

    logger.info(
        "[%s] Fichier écrit : %s (%.1f MB, SHA256=%s...)",
        lang_id, output_path, size_mb, sha256[:16],
    )

    return {
        "lang_id": lang_id,
        "entry_count": entry_count,
        "raw_entry_count": raw_entry_count,
        "output_path": str(output_path),
        "size_mb": round(size_mb, 2),
        "sha256": sha256,
        "build_duration_seconds": round(elapsed, 1),
        "status": "built",
    }


# ── Build pt-BR (source alternative plain-text) ───────────────────────────────

def build_lexicon_ptbr(
    output_dir: Path,
    max_entries: int = 0,
    force: bool = False,
) -> dict:
    """Construit le lexique pt-BR depuis la wordlist fserb/pt-br (plain text).

    Source : https://raw.githubusercontent.com/fserb/pt-br/master/wordlist.txt
    Format : un mot par ligne, UTF-8, sans POS ni formes fléchies.
    Licence : MIT.

    LIMITATION HONNÊTE : pas de POS, pas de formes fléchies, pos=unknown pour tout.
    Pour un lexique pt-BR plus riche : utiliser LanguageTool portuguese-pos-dict.
    """
    lang_id = "pt-BR"
    config = LANG_CONFIG[lang_id]
    output_path = output_dir / f"pt-BR_lexicon.json"

    if output_path.exists() and not force:
        logger.info("[pt-BR] Fichier lexique déjà présent : %s — skip", output_path)
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        return {
            "lang_id": lang_id,
            "entry_count": existing.get("entry_count", 0),
            "output_path": str(output_path),
            "status": "skipped_existing",
        }

    url = config["alt_source_url"]
    logger.info("[pt-BR] Début téléchargement wordlist depuis %s", url)
    t_start = time.time()

    seen_words: set[str] = set()
    entries_out: list[dict] = []
    raw_count = 0

    try:
        for word in _stream_plaintext_words(url, max_entries=max_entries):
            raw_count += 1
            word_clean = word.strip()
            if not word_clean or len(word_clean) < 1:
                continue
            if word_clean.lower() not in seen_words:
                seen_words.add(word_clean.lower())
                entries_out.append({
                    "surface_form": word_clean,
                    "lemma": word_clean,
                    "pos": "unknown",  # wordlist plain-text sans POS
                    "artcb_code": "",
                    "source": "github-fserb-ptbr",
                    "forms_count": 0,
                })
    except Exception as exc:
        logger.error("[pt-BR] Erreur extraction : %s", exc)
        raise

    elapsed = time.time() - t_start
    entry_count = len(entries_out)
    logger.info(
        "[pt-BR] Extraction terminée : %d mots bruts → %d uniques en %.1fs",
        raw_count, entry_count, elapsed,
    )

    build_date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "lang_id": lang_id,
        "lang_name_en": config["name_en"],
        "script": config["script"],
        "source": "github-fserb-ptbr",
        "source_url": url,
        "source_note": config["alt_source_note"],
        "build_date": build_date,
        "build_duration_seconds": round(elapsed, 1),
        "raw_entry_count": raw_count,
        "entry_count": entry_count,
        "max_entries_cap": max_entries if max_entries > 0 else "unlimited",
        "certified_100": False,
        "note": (
            "PT-BR : wordlist fserb/pt-br (MIT). POS=unknown (pas disponible dans cette source). "
            "pt ≠ pt-BR : pt = portugais neutre (kaikki.org), pt-BR = variante brésilienne. "
            "CERTIFIED_100=false."
        ),
        "entries": entries_out,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    output_path.chmod(0o644)

    sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
    size_mb = output_path.stat().st_size / (1024 * 1024)

    logger.info(
        "[pt-BR] Fichier écrit : %s (%.1f MB, SHA256=%s...)",
        output_path, size_mb, sha256[:16],
    )

    return {
        "lang_id": lang_id,
        "entry_count": entry_count,
        "raw_entry_count": raw_count,
        "output_path": str(output_path),
        "size_mb": round(size_mb, 2),
        "sha256": sha256,
        "build_duration_seconds": round(elapsed, 1),
        "status": "built",
    }


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="R465/R465-ext — ARTCB Lexicon Builder — 16 profils linguistiques"
    )
    parser.add_argument("--lang", help="Code ISO langue à builder (ex: fr, en, la, pt-BR)")
    parser.add_argument("--all", action="store_true", help="14 langues initiales R465")
    parser.add_argument("--all-16", action="store_true", help="16 profils complets (14 + la + pt-BR)")
    parser.add_argument("--test", action="store_true", help="Mode test : 5000 entrées par langue")
    parser.add_argument("--force", action="store_true", help="Écraser les fichiers existants")
    parser.add_argument("--output-dir", default="data/lexicons", help="Répertoire de sortie")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    max_entries = 5000 if args.test else 0

    # Sélection des profils à builder
    if args.lang:
        if args.lang not in LANG_CONFIG:
            logger.error("Profil inconnu : %s. Disponibles : %s", args.lang, list(LANG_CONFIG.keys()))
            sys.exit(1)
        lang_ids = [args.lang]
    elif getattr(args, "all_16", False):
        lang_ids = ALL_16_LANG_IDS
    elif args.all:
        lang_ids = INITIAL_14_LANG_IDS
    else:
        lang_ids = INITIAL_14_LANG_IDS

    logger.info(
        "=== R465 ARTCB Lexicon Build === langues=%s mode=%s output=%s",
        lang_ids,
        "TEST(5000)" if args.test else "FULL",
        output_dir,
    )

    results = []
    total_entries = 0

    for lang_id in lang_ids:
        config = LANG_CONFIG[lang_id]
        logger.info("--- [%s] %s ---", lang_id, config["name_en"])

        try:
            # Routing : pt-BR → build_lexicon_ptbr (source plain-text alternative)
            # la → build_lexicon_for_lang standard (kaikki.org Latin DEPRECATED)
            # autres → build_lexicon_for_lang standard (kaikki.org JSONL)
            if lang_id == "pt-BR":
                result = build_lexicon_ptbr(
                    output_dir=output_dir,
                    max_entries=max_entries,
                    force=args.force,
                )
            else:
                if config.get("deprecated_warning"):
                    logger.warning("[%s] ATTENTION : %s", lang_id, config["deprecated_warning"])
                result = build_lexicon_for_lang(
                    lang_id=lang_id,
                    config=config,
                    output_dir=output_dir,
                    max_entries=max_entries,
                    force=args.force,
                )

            results.append(result)
            total_entries += result.get("entry_count", 0)
            logger.info(
                "[%s] ✓ %d entrées — status=%s",
                lang_id, result.get("entry_count", 0), result["status"],
            )
        except Exception as exc:
            logger.error("[%s] ERREUR : %s", lang_id, exc)
            results.append({"lang_id": lang_id, "status": "ERROR", "error": str(exc)})

    # Rapport de build
    build_report = {
        "build_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "TEST(5000)" if args.test else "FULL",
        "languages_built": len([r for r in results if r.get("status") in ("built", "skipped_existing")]),
        "languages_error": len([r for r in results if r.get("status") == "ERROR"]),
        "total_entries": total_entries,
        "certified_100": False,
        "results": results,
    }

    report_path = output_dir / "build_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(build_report, f, ensure_ascii=False, indent=2)

    logger.info("=== BUILD TERMINÉ === %d langues, %d entrées totales", len(lang_ids), total_entries)
    logger.info("Rapport : %s", report_path)

    # Résumé final
    print("\n=== RÉSUMÉ R465 LEXICON BUILD ===")
    for r in results:
        status = r.get("status", "?")
        count = r.get("entry_count", 0)
        lang = r.get("lang_id", "?")
        size = r.get("size_mb", 0)
        print(f"  {lang:4s} : {count:>8d} entrées  {size:6.1f} MB  [{status}]")
    print(f"\n  TOTAL : {total_entries:,} entrées")
    print(f"  Rapport : {report_path}")
    print("  CERTIFIED_100=false")


if __name__ == "__main__":
    main()
