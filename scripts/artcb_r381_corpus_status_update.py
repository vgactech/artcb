#!/usr/bin/env python3
"""R381 — Mise à jour status DETECTED_NOT_CLASSIFIED → status réel dans rule_corpus_index.json.

Logique de classification du status :
  - RULE  + rt_rule_id non nul      → "REGISTERED_IN_REGISTRY"
  - RULE  + rt_rule_id nul          → "DETECTED_UNREGISTERED"
  - DECISION                        → "DECISION_ACTIVE"
  - LESSON                          → "LESSON_DOCUMENTED"
  - SPEC                            → "SPEC_DOCUMENTED"
  - CHECK                           → "CHECK_DOCUMENTED"
  - CONVENTION                      → "CONVENTION_DOCUMENTED"
  - EVIDENCE                        → "EVIDENCE_DOCUMENTED"
  - QUESTION                        → "QUESTION_OPEN"
  - Tout autre kind                 → "CLASSIFIED" (fallback générique)

Le champ `domain` doit être non nul (déjà classifié par artcb_r393_v2) pour que
le status soit promu — sinon il reste "DETECTED_NOT_CLASSIFIED".

CERTIFIED_100=false | MODE DEBUG | Ne modifie que rule_corpus_index.json.
"""

from __future__ import annotations

MODULE_VERSION = '1.0.0'

import json
import logging
import time
from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("artcb.r381_corpus_status_update")

REPO_ROOT = Path(__file__).parent.parent.resolve()
CORPUS_PATH = REPO_ROOT / "rules" / "rule_corpus_index.json"
BACKUP_PATH = REPO_ROOT / "rules" / "rule_corpus_index.json.bak_r381"

# Mapping kind → status cible
KIND_STATUS_MAP: dict[str, str] = {
    "DECISION":   "DECISION_ACTIVE",
    "LESSON":     "LESSON_DOCUMENTED",
    "SPEC":       "SPEC_DOCUMENTED",
    "CHECK":      "CHECK_DOCUMENTED",
    "CONVENTION": "CONVENTION_DOCUMENTED",
    "EVIDENCE":   "EVIDENCE_DOCUMENTED",
    "QUESTION":   "QUESTION_OPEN",
}

RULE_REGISTERED   = "REGISTERED_IN_REGISTRY"
RULE_UNREGISTERED = "DETECTED_UNREGISTERED"
FALLBACK_STATUS   = "CLASSIFIED"

# Ne jamais écraser un status déjà promu (si déjà mis à jour manuellement)
STATUS_IMMUTABLE = frozenset({
    "VALIDATED",
    "CERTIFIED",
    "DEPRECATED",
    "SUPERSEDED",
    "CONFLICT",
})


def classify_status(entry: dict) -> str:
    """Détermine le nouveau status à partir des champs de l'entrée."""
    kind = (entry.get("kind") or "").upper()
    domain = entry.get("primary_domain") or entry.get("domain") or ""
    rt_rule_id = entry.get("rt_rule_id")

    # Ne pas changer un status déjà promu
    current = entry.get("status", "DETECTED_NOT_CLASSIFIED")
    if current in STATUS_IMMUTABLE:
        return current

    # Le domain doit être classifié pour promouvoir le status
    if not domain:
        return "DETECTED_NOT_CLASSIFIED"

    if kind == "RULE":
        return RULE_REGISTERED if rt_rule_id else RULE_UNREGISTERED

    return KIND_STATUS_MAP.get(kind, FALLBACK_STATUS)


def run() -> None:
    logger.debug("[R381] Démarrage — lecture %s", CORPUS_PATH)

    if not CORPUS_PATH.exists():
        logger.error("[R381] ERREUR — %s introuvable", CORPUS_PATH)
        raise FileNotFoundError(str(CORPUS_PATH))

    with CORPUS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    entries: list[dict] = data if isinstance(data, list) else data.get("entries", [])
    logger.debug("[R381] %d entrées lues", len(entries))

    # Backup avant modification
    BACKUP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("[R381] Backup → %s", BACKUP_PATH.name)

    counters: dict[str, int] = {}
    updated = 0
    unchanged = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        old_status = entry.get("status", "DETECTED_NOT_CLASSIFIED")
        new_status = classify_status(entry)

        counters[new_status] = counters.get(new_status, 0) + 1

        if old_status != new_status:
            logger.debug(
                "[R381] %s : %s → %s (kind=%s, domain=%s)",
                entry.get("corpus_id", "?"),
                old_status,
                new_status,
                entry.get("kind", "?"),
                entry.get("primary_domain", "?"),
            )
            entry["status"] = new_status
            entry["status_updated_by"] = "artcb_r381"
            entry["status_updated_ts"] = time.time_ns()
            updated += 1
        else:
            unchanged += 1

    logger.info("[R381] Résumé : %d mis à jour, %d inchangés", updated, unchanged)
    logger.info("[R381] Répartition status : %s", json.dumps(counters, ensure_ascii=False))

    # Écriture
    out: object = entries if isinstance(data, list) else {**data, "entries": entries}
    CORPUS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[R381] rule_corpus_index.json mis à jour — %d entrées", len(entries))

    # Résultat lisible
    print("\n=== R381 CORPUS STATUS UPDATE ===")
    print(f"  Entrées totales : {len(entries)}")
    print(f"  Mises à jour    : {updated}")
    print(f"  Inchangées      : {unchanged}")
    print(f"  DETECTED_NOT_CLASSIFIED restants : {counters.get('DETECTED_NOT_CLASSIFIED', 0)}")
    print("\n  Répartition finale :")
    for k, v in sorted(counters.items(), key=lambda x: -x[1]):
        print(f"    {k:<35} : {v}")
    print("\n  CERTIFIED_100=false | MODE DEBUG actif")


if __name__ == "__main__":
    run()
