"""KnowledgeStore — Persistance JSON des KnowledgeRecords et UsageRecords (R434).

Persistance atomique (R433-style : tmp → fsync → rename + fcntl.LOCK_EX).

Structure des fichiers :
  <data_dir>/knowledge_records.json   — KnowledgeRecords
  <data_dir>/usage_records.json       — UsageRecords

Fonctions principales :
  - save(record)          : ajoute ou met à jour un KnowledgeRecord
  - get(knowledge_id)     : retourne un KnowledgeRecord par ID ou None
  - list_active()         : liste les KnowledgeRecords ACTIVE
  - search_by_reasoning(reasoning_id) : recherche par ReasoningID
  - save_usage(usage)     : ajoute un UsageRecord
  - list_usages(knowledge_id) : UsageRecords pour un KnowledgeID
  - pol_eligible_usages() : UsageRecords avec pol_eligible=True

PROTOCOLE ARTCB — mode DEBUG actif.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.1'  # R434 — Knowledge Layer

import contextlib
import fcntl
import json
import logging
import os
from pathlib import Path
from typing import Any

from src.artcb.knowledge.knowledge import KnowledgeRecord, KnowledgeStatus
from src.artcb.knowledge.usage import UsageRecord

logger = logging.getLogger("artcb.knowledge.store")


class KnowledgeStore:
    """Registre JSON atomique des KnowledgeRecords et UsageRecords (R434).

    Thread/process-safe grâce à _transactional_lock() (fcntl.LOCK_EX sur .lock).
    Écriture atomique via tmp → fsync → rename (R432/R433 pattern).
    """

    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._records_path = self._dir / "knowledge_records.json"
        self._usage_path = self._dir / "usage_records.json"
        if not self._records_path.is_file():
            self._write_atomic(self._records_path, [])
        if not self._usage_path.is_file():
            self._write_atomic(self._usage_path, [])

    # ── Verrou transactionnel (R433 pattern) ─────────────────────────────────

    @staticmethod
    @contextlib.contextmanager
    def _transactional_lock(target: Path):
        """Verrou exclusif POSIX sur <target>.lock (identique à R433)."""
        lock_path = target.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fh = lock_path.open("a")
        try:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_EX)
            except (AttributeError, OSError):
                pass
            yield
        finally:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
            except (AttributeError, OSError):
                pass
            lock_fh.close()

    @staticmethod
    def _write_atomic(target: Path, records: list[dict]) -> None:
        """Écriture atomique tmp → fsync → rename (R433 pattern)."""
        tmp = target.with_suffix(".tmp")
        payload = json.dumps(records, indent=2, ensure_ascii=False).encode("utf-8")
        with tmp.open("wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.rename(target)
        try:
            target.chmod(0o600)
        except OSError:
            pass

    def _read_records(self) -> list[dict]:
        try:
            return json.loads(self._records_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _read_usages(self) -> list[dict]:
        try:
            return json.loads(self._usage_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    # ── KnowledgeRecord — lecture/écriture ───────────────────────────────────

    def save(self, record: KnowledgeRecord) -> None:
        """Ajoute ou met à jour un KnowledgeRecord (upsert par knowledge_id)."""
        with self._transactional_lock(self._records_path):
            records = self._read_records()
            idx = next(
                (i for i, r in enumerate(records) if r.get("knowledge_id") == record.knowledge_id),
                None,
            )
            if idx is None:
                records.append(record.to_dict())
            else:
                records[idx] = record.to_dict()
            self._write_atomic(self._records_path, records)
        logger.debug(
            "knowledge.store: saved knowledge_id=%s type=%s status=%s",
            record.knowledge_id, record.knowledge_type.value, record.status.value,
        )

    def get(self, knowledge_id: str) -> KnowledgeRecord | None:
        """Retourne un KnowledgeRecord par son knowledge_id, ou None."""
        records = self._read_records()
        d = next((r for r in records if r.get("knowledge_id") == knowledge_id), None)
        return KnowledgeRecord.from_dict(d) if d else None

    def list_all(self) -> list[KnowledgeRecord]:
        """Retourne tous les KnowledgeRecords."""
        return [KnowledgeRecord.from_dict(r) for r in self._read_records()]

    def list_active(self) -> list[KnowledgeRecord]:
        """Retourne les KnowledgeRecords dont le statut est ACTIVE."""
        return [
            KnowledgeRecord.from_dict(r)
            for r in self._read_records()
            if r.get("status") == KnowledgeStatus.ACTIVE.value
        ]

    def search_by_reasoning(self, reasoning_id: str) -> list[KnowledgeRecord]:
        """Retourne les KnowledgeRecords associés à ce ReasoningID."""
        return [
            KnowledgeRecord.from_dict(r)
            for r in self._read_records()
            if r.get("reasoning_id") == reasoning_id
        ]

    def search_by_producer(self, producer_id: str) -> list[KnowledgeRecord]:
        """Retourne les KnowledgeRecords produits par cet agent."""
        return [
            KnowledgeRecord.from_dict(r)
            for r in self._read_records()
            if r.get("producer_id") == producer_id
        ]

    # ── UsageRecord — lecture/écriture ───────────────────────────────────────

    def save_usage(self, usage: UsageRecord) -> None:
        """Ajoute un UsageRecord (upsert par usage_id)."""
        with self._transactional_lock(self._usage_path):
            usages = self._read_usages()
            idx = next(
                (i for i, u in enumerate(usages) if u.get("usage_id") == usage.usage_id),
                None,
            )
            if idx is None:
                usages.append(usage.to_dict())
            else:
                usages[idx] = usage.to_dict()
            self._write_atomic(self._usage_path, usages)
        logger.debug(
            "knowledge.store: usage_id=%s knowledge_id=%s purpose=%s pol_eligible=%s",
            usage.usage_id, usage.knowledge_id, usage.purpose.value, usage.pol_eligible,
        )

    def list_usages(self, knowledge_id: str) -> list[UsageRecord]:
        """Retourne tous les UsageRecords pour ce knowledge_id."""
        return [
            UsageRecord.from_dict(u)
            for u in self._read_usages()
            if u.get("knowledge_id") == knowledge_id
        ]

    def pol_eligible_usages(self) -> list[UsageRecord]:
        """Retourne les UsageRecords éligibles PoL (pol_eligible=True)."""
        return [
            UsageRecord.from_dict(u)
            for u in self._read_usages()
            if u.get("pol_eligible") is True
        ]

    def usages_by_consumer(self, consumer_id: str) -> list[UsageRecord]:
        """Retourne les UsageRecords pour ce consumer_id."""
        return [
            UsageRecord.from_dict(u)
            for u in self._read_usages()
            if u.get("consumer_id") == consumer_id
        ]
