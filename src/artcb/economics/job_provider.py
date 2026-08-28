"""Job Provider accounting + capacity-based dynamic partitioning."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.artcb.economics.preblocks import PreBlockShare, partition_block_reward

logger = logging.getLogger("artcb.economics.job_provider")


class JobProviderError(ValueError):
    """Invalid job-provider state transition."""


@dataclass
class JobRecord:
    job_id: str
    provider_address: str
    payload: str
    status: str
    created_at: str
    worker_capacities: list[float] = field(default_factory=list)
    preblocks: list[dict] = field(default_factory=list)
    r_block_satoshi: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class JobProvider:
    """Submit jobs, measure capacity, partition into pre-blocks, settle."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("job provider unreadable path=%s err=%s", self.path, exc)
            return []
        if not isinstance(data, list):
            return []
        return data

    def _write(self, records: list[dict]) -> None:
        self.path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _save(self, job: JobRecord) -> JobRecord:
        rows = self._read()
        updated = False
        for i, row in enumerate(rows):
            if row.get("job_id") == job.job_id:
                rows[i] = job.to_dict()
                updated = True
                break
        if not updated:
            rows.append(job.to_dict())
        self._write(rows)
        return job

    def get(self, job_id: str) -> JobRecord | None:
        for row in self._read():
            if row.get("job_id") == job_id:
                return JobRecord(**row)
        return None

    def submit(self, *, provider_address: str, payload: str) -> JobRecord:
        provider = provider_address.strip()
        if not provider:
            raise JobProviderError("provider_address is required")
        if not payload.strip():
            raise JobProviderError("payload is required")
        job = JobRecord(
            job_id=f"job_{uuid.uuid4().hex[:16]}",
            provider_address=provider,
            payload=payload,
            status="submitted",
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        logger.debug("job submitted id=%s provider=%s", job.job_id, provider)
        return self._save(job)

    @staticmethod
    def measure_capacity(worker_capacities: list[float]) -> float:
        if not worker_capacities:
            raise JobProviderError("worker_capacities must be non-empty")
        if any(c < 0 for c in worker_capacities):
            raise JobProviderError("capacity cannot be negative")
        total = float(sum(worker_capacities))
        if total <= 0:
            raise JobProviderError("total capacity must be positive")
        return total

    def partition(
        self,
        job_id: str,
        *,
        worker_capacities: list[float],
        r_block_satoshi: int,
    ) -> list[PreBlockShare]:
        job = self.get(job_id)
        if job is None:
            raise JobProviderError(f"unknown job {job_id}")
        self.measure_capacity(worker_capacities)
        shares = partition_block_reward(r_block_satoshi, worker_capacities)
        job.worker_capacities = list(worker_capacities)
        job.r_block_satoshi = r_block_satoshi
        job.preblocks = [
            {
                "preblock_id": s.preblock_id,
                "weight": s.weight,
                "reward_satoshi": s.reward_satoshi,
            }
            for s in shares
        ]
        job.status = "partitioned"
        self._save(job)
        logger.debug(
            "job %s partitioned n=%s R_block=%s",
            job_id,
            len(shares),
            r_block_satoshi,
        )
        return shares

    def cancel(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job is None:
            raise JobProviderError(f"unknown job {job_id}")
        if job.status in {"settled", "cancelled"}:
            raise JobProviderError(f"job {job_id} cannot cancel from status={job.status}")
        job.status = "cancelled"
        logger.debug("job %s cancelled", job_id)
        return self._save(job)

    def mark_partial(self, job_id: str, *, completed_preblocks: int) -> JobRecord:
        job = self.get(job_id)
        if job is None:
            raise JobProviderError(f"unknown job {job_id}")
        if job.status not in {"partitioned", "submitted", "partial"}:
            raise JobProviderError(f"job {job_id} cannot mark partial from status={job.status}")
        job.status = "partial"
        logger.debug("job %s partial completed_pb=%s", job_id, completed_preblocks)
        return self._save(job)

    def mark_settled(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job is None:
            raise JobProviderError(f"unknown job {job_id}")
        if job.status != "partitioned":
            raise JobProviderError(
                f"job {job_id} cannot settle from status={job.status}"
            )
        job.status = "settled"
        return self._save(job)
