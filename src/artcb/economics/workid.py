"""WorkID lifecycle — unique settlement (rapport 162)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger("artcb.economics.workid")


class WorkStatus(str, Enum):
    UNASSIGNED = "UNASSIGNED"
    ASSIGNED = "ASSIGNED"
    EXECUTING = "EXECUTING"
    SUBMITTED = "SUBMITTED"
    VALIDATED = "VALIDATED"
    SETTLED = "SETTLED"
    REJECTED = "REJECTED"
    REQUEUED = "REQUEUED"


class WorkIDError(ValueError):
    pass


@dataclass
class WorkRecord:
    work_id: str
    job_id: str
    status: str
    created_at: str
    settlement_count: int = 0
    useful_work_score: float = 0.0
    llm_token_count: int = 0  # cost, never a PoL proof

    def to_dict(self) -> dict:
        return asdict(self)


class WorkRegistry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("work registry unreadable %s %s", self.path, exc)
            return []
        return data if isinstance(data, list) else []

    def _write(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, work_id: str) -> WorkRecord | None:
        for row in self._read():
            if row.get("work_id") == work_id:
                return WorkRecord(**row)
        return None

    def create(self, *, work_id: str, job_id: str) -> WorkRecord:
        if self.get(work_id) is not None:
            raise WorkIDError(f"WorkID already exists: {work_id}")
        rec = WorkRecord(
            work_id=work_id,
            job_id=job_id,
            status=WorkStatus.UNASSIGNED.value,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        rows = self._read()
        rows.append(rec.to_dict())
        self._write(rows)
        return rec

    def _save(self, rec: WorkRecord) -> None:
        rows = self._read()
        for i, row in enumerate(rows):
            if row.get("work_id") == rec.work_id:
                rows[i] = rec.to_dict()
                self._write(rows)
                return
        raise WorkIDError(f"unknown WorkID {rec.work_id}")

    def transition(self, work_id: str, new_status: WorkStatus, *, useful_work_score: float | None = None) -> WorkRecord:
        rec = self.get(work_id)
        if rec is None:
            raise WorkIDError(f"unknown WorkID {work_id}")
        if rec.status == WorkStatus.SETTLED.value and new_status == WorkStatus.SETTLED:
            raise WorkIDError(f"SettlementCount(WorkID) already 1: {work_id}")
        rec.status = new_status.value
        if useful_work_score is not None:
            rec.useful_work_score = float(useful_work_score)
        if new_status == WorkStatus.SETTLED:
            rec.settlement_count += 1
            if rec.settlement_count > 1:
                raise WorkIDError(f"SettlementCount(WorkID)>1: {work_id}")
        if new_status == WorkStatus.REJECTED:
            rec.useful_work_score = 0.0
        self._save(rec)
        logger.debug("WorkID %s -> %s score=%s", work_id, new_status.value, rec.useful_work_score)
        return rec

    def requeue_missing_preblock(self, work_ids: list[str]) -> list[WorkRecord]:
        out = []
        for wid in work_ids:
            out.append(self.transition(wid, WorkStatus.REQUEUED))
        return out

    @staticmethod
    def pol_from_useful_work(*, compression: float, validation: float, retrieval: float, llm_tokens: int = 0) -> float:
        """LLM token count is a cost, never sufficient proof (user GO 162)."""
        del llm_tokens  # explicitly unused as PoL
        score = 0.4 * compression + 0.3 * validation + 0.3 * retrieval
        logger.debug("useful-work PoL=%.6f (tokens ignored)", score)
        return max(0.0, min(1.0, score))
