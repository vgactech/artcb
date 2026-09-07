"""KCG — persistance et index (GO-F 2026-09-07).

KCGStore  — écriture append-only JSONL (data/kcg/events.jsonl)
KCGIndex  — index en mémoire : knowledge_id → KnowledgeEntry + stats
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .events import (
    ConsultEvent,
    KnowledgeEntry,
    UseEvent,
    knowledge_id,
)

logger = logging.getLogger("artcb.kcg")

_EVENTS_FILENAME = "events.jsonl"
_KNOWLEDGE_FILENAME = "knowledge.jsonl"


class KCGStore:
    """Persistance append-only des événements KCG.

    Format fichier : une ligne JSON par événement.
    Thread-safe en lecture (load) — écriture séquentielle.
    """

    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir) / "kcg"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._dir / _EVENTS_FILENAME
        self._knowledge_path = self._dir / _KNOWLEDGE_FILENAME

    # ── Connaissance ────────────────────────────────────────────────────────

    def publish_knowledge(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """Publie une entrée dans le KCG (idempotent sur knowledge_id)."""
        existing = self._load_knowledge_by_id(entry.knowledge_id)
        if existing:
            logger.info("KCG: knowledge %s déjà présent — pas de doublon", entry.knowledge_id)
            return existing
        with self._knowledge_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        logger.info(
            "KCG: knowledge publié %s producer=%s pol_score=%.3f",
            entry.knowledge_id, entry.producer_address, entry.pol_score,
        )
        return entry

    def _load_knowledge_by_id(self, kid: str) -> KnowledgeEntry | None:
        if not self._knowledge_path.is_file():
            return None
        for line in self._knowledge_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if d.get("knowledge_id") == kid:
                    return KnowledgeEntry.from_dict(d)
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def all_knowledge(self) -> list[KnowledgeEntry]:
        if not self._knowledge_path.is_file():
            return []
        entries = []
        for line in self._knowledge_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(KnowledgeEntry.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        return entries

    # ── Événements ──────────────────────────────────────────────────────────

    def record_consult(self, event: ConsultEvent) -> ConsultEvent:
        """Enregistre un événement CONSULT."""
        self._append_event(event.to_dict())
        logger.info(
            "KCG: CONSULT %s knowledge=%s consultant=%s fee_pending=%s",
            event.consult_id, event.knowledge_id,
            event.consultant_address[:16] if event.consultant_address else "?",
            event.fee_pending,
        )
        return event

    def record_use(self, event: UseEvent) -> UseEvent:
        """Enregistre un événement USE avec mesure d'utilité."""
        if event.score_before is not None and event.score_after is not None:
            event.delta_utility = event.score_after - event.score_before
            event.utility_measured = True
        self._append_event(event.to_dict())
        logger.info(
            "KCG: USE %s knowledge=%s consumer=%s delta=%.3f measured=%s",
            event.usage_id, event.knowledge_id,
            event.consumer_address[:16] if event.consumer_address else "?",
            event.delta_utility, event.utility_measured,
        )
        return event

    def _append_event(self, d: dict[str, Any]) -> None:
        with self._events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    def all_events(self) -> list[dict[str, Any]]:
        if not self._events_path.is_file():
            return []
        events = []
        for line in self._events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return events

    def events_for_knowledge(self, kid: str) -> list[dict[str, Any]]:
        return [e for e in self.all_events() if e.get("knowledge_id") == kid]


class KCGIndex:
    """Index en mémoire du KCG — stats agrégées par KnowledgeID.

    Chargé au démarrage depuis KCGStore.
    Mise à jour incrémentale à chaque CONSULT/USE.
    """

    def __init__(self, store: KCGStore) -> None:
        self._store = store
        self._entries: dict[str, KnowledgeEntry] = {}
        self._reload()

    def _reload(self) -> None:
        """Charge toutes les entrées de connaissance depuis le store."""
        self._entries = {e.knowledge_id: e for e in self._store.all_knowledge()}
        # Recalcule les stats depuis les événements
        for event in self._store.all_events():
            self._apply_event(event)

    def _apply_event(self, event: dict[str, Any]) -> None:
        kid = event.get("knowledge_id", "")
        entry = self._entries.get(kid)
        if not entry:
            return
        if event.get("event_type") == "CONSULT":
            entry.consult_count += 1
        elif event.get("event_type") == "USE":
            entry.use_count += 1
            entry.total_delta_utility += float(event.get("delta_utility", 0.0))
            # Mise à jour réputation : moyenne pondérée du delta
            if entry.use_count > 0:
                entry.reputation_score = entry.total_delta_utility / entry.use_count

    def publish(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """Publie une nouvelle entrée et met à jour l'index."""
        saved = self._store.publish_knowledge(entry)
        self._entries[saved.knowledge_id] = saved
        return saved

    def consult(self, event: ConsultEvent) -> ConsultEvent:
        """Enregistre un CONSULT et met à jour les stats."""
        saved = self._store.record_consult(event)
        self._apply_event(saved.to_dict())
        return saved

    def use(self, event: UseEvent) -> UseEvent:
        """Enregistre un USE et met à jour les stats."""
        saved = self._store.record_use(event)
        self._apply_event(saved.to_dict())
        return saved

    def get(self, kid: str) -> KnowledgeEntry | None:
        return self._entries.get(kid)

    def all(self) -> list[KnowledgeEntry]:
        return list(self._entries.values())

    def stats(self) -> dict[str, Any]:
        entries = self.all()
        return {
            "knowledge_count": len(entries),
            "total_consults": sum(e.consult_count for e in entries),
            "total_uses": sum(e.use_count for e in entries),
            "total_delta_utility": sum(e.total_delta_utility for e in entries),
            "top_reputation": sorted(
                [{"knowledge_id": e.knowledge_id, "reputation": e.reputation_score}
                 for e in entries],
                key=lambda x: x["reputation"], reverse=True
            )[:5],
        }

    def from_graph(self, graph_id: str) -> KnowledgeEntry | None:
        """Récupère une entrée depuis un graph_id."""
        for entry in self._entries.values():
            if entry.graph_id == graph_id:
                return entry
        return None
