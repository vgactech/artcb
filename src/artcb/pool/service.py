"""Pool de calcul distribué — jobs chiffrés E2E ML-KEM."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from src.artcb.pool.e2e import (
    decrypt_chunk_payload,
    decrypt_result_payload,
    encrypt_chunk_payload,
    encrypt_result_payload,
)

logger = logging.getLogger("artcb.pool.service")


class PoolError(Exception):
    """Pool operation failed."""


@dataclass
class PoolChunk:
    chunk_id: str
    chunk_index: int
    worker_node_id: str
    worker_kem_public_hex: str
    envelope: dict[str, str]
    status: str = "pending"
    result_envelope: dict[str, str] | None = None
    contributor_address: str | None = None
    pol_score: float | None = None
    graph_id: str | None = None
    node_count: int | None = None
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "worker_node_id": self.worker_node_id,
            "worker_kem_public_hex": self.worker_kem_public_hex,
            "envelope": self.envelope,
            "status": self.status,
            "result_envelope": self.result_envelope,
            "contributor_address": self.contributor_address,
            "pol_score": self.pol_score,
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PoolChunk:
        return cls(
            chunk_id=data["chunk_id"],
            chunk_index=int(data["chunk_index"]),
            worker_node_id=data["worker_node_id"],
            worker_kem_public_hex=data["worker_kem_public_hex"],
            envelope=data["envelope"],
            status=data.get("status", "pending"),
            result_envelope=data.get("result_envelope"),
            contributor_address=data.get("contributor_address"),
            pol_score=data.get("pol_score"),
            graph_id=data.get("graph_id"),
            node_count=data.get("node_count"),
            signature=data.get("signature"),
        )


@dataclass
class PoolJob:
    job_id: str
    owner_node_id: str
    owner_kem_public_hex: str
    visibility: str
    status: str
    chunks: list[PoolChunk] = field(default_factory=list)
    created_at: str = ""
    actor_address: str | None = None
    wallet_name: str | None = None
    group_id: str | None = None
    encrypt_transport: bool = True
    final_graph_id: str | None = None
    block_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "owner_node_id": self.owner_node_id,
            "owner_kem_public_hex": self.owner_kem_public_hex,
            "visibility": self.visibility,
            "status": self.status,
            "chunks": [c.to_dict() for c in self.chunks],
            "created_at": self.created_at,
            "actor_address": self.actor_address,
            "wallet_name": self.wallet_name,
            "group_id": self.group_id,
            "encrypt_transport": self.encrypt_transport,
            "final_graph_id": self.final_graph_id,
            "block_index": self.block_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PoolJob:
        return cls(
            job_id=data["job_id"],
            owner_node_id=data["owner_node_id"],
            owner_kem_public_hex=data["owner_kem_public_hex"],
            visibility=data.get("visibility", "private"),
            status=data.get("status", "open"),
            chunks=[PoolChunk.from_dict(c) for c in data.get("chunks", [])],
            created_at=data.get("created_at", ""),
            actor_address=data.get("actor_address"),
            wallet_name=data.get("wallet_name"),
            group_id=data.get("group_id"),
            encrypt_transport=bool(data.get("encrypt_transport", True)),
            final_graph_id=data.get("final_graph_id"),
            block_index=data.get("block_index"),
        )


def split_text_chunks(text: str, *, chunk_chars: int = 400) -> list[str]:
    """Découpe le texte en morceaux — préserve phrases si possible."""
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        if end < len(text):
            for sep in (". ", ".\n", "\n\n", " "):
                idx = text.rfind(sep, start, end)
                if idx > start:
                    end = idx + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks if chunks else [text]


class PoolService:
    """
    Pool calcul distribué opt-in — morceaux chiffrés ML-KEM E2E.
    Règle : jamais de texte en clair sur le réseau pour jobs private/public pool.
    """

    def __init__(
        self,
        data_dir: Path,
        *,
        node_id: str,
        kem_public_hex: str,
        kem_secret_hex: str,
        run_reasoning: Callable[[str], dict[str, Any]],
        finalize_job: Callable[[PoolJob, str, list[dict[str, Any]]], dict[str, Any]] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.pool_dir = self.data_dir / "pool"
        self.jobs_path = self.pool_dir / "jobs.jsonl"
        self.incoming_path = self.pool_dir / "incoming_chunks.jsonl"
        self.pool_dir.mkdir(parents=True, exist_ok=True)
        self.node_id = node_id
        self.kem_public_hex = kem_public_hex
        self.kem_secret_hex = kem_secret_hex
        self._run_reasoning = run_reasoning
        self._finalize_job = finalize_job

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _read_jobs(self) -> list[PoolJob]:
        if not self.jobs_path.is_file():
            return []
        jobs = []
        for line in self.jobs_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                jobs.append(PoolJob.from_dict(json.loads(line)))
        return jobs

    def _write_jobs(self, jobs: list[PoolJob]) -> None:
        lines = [json.dumps(j.to_dict(), ensure_ascii=False, separators=(",", ":")) for j in jobs]
        self.jobs_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        self.jobs_path.chmod(0o600)

    def _read_incoming(self) -> list[dict[str, Any]]:
        if not self.incoming_path.is_file():
            return []
        items = []
        for line in self.incoming_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(json.loads(line))
        return items

    def _append_incoming(self, item: dict[str, Any]) -> None:
        with self.incoming_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.incoming_path.chmod(0o600)

    def _save_incoming_all(self, items: list[dict[str, Any]]) -> None:
        lines = [json.dumps(i, ensure_ascii=False, separators=(",", ":")) for i in items]
        self.incoming_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        self.incoming_path.chmod(0o600)

    def list_jobs(self) -> list[PoolJob]:
        return self._read_jobs()

    def get_job(self, job_id: str) -> PoolJob | None:
        for job in self._read_jobs():
            if job.job_id == job_id:
                return job
        return None

    def _update_job(self, job: PoolJob) -> None:
        jobs = self._read_jobs()
        jobs = [j for j in jobs if j.job_id != job.job_id]
        jobs.append(job)
        self._write_jobs(jobs)

    def create_job(
        self,
        text: str,
        *,
        visibility: str = "private",
        workers: list[dict[str, str]],
        actor_address: str | None = None,
        wallet_name: str | None = None,
        group_id: str | None = None,
        chunk_chars: int = 400,
        encrypt_transport: bool = True,
        anti_sybil=None,
        source: str = "unknown",
    ) -> PoolJob:
        """
        workers: [{node_id, kem_public_hex, base_url?, contributor_address?}, ...]

        PRE-FILTRE ANTI-SYBIL :
        Si anti_sybil est fourni, tout worker dont le contributor_address est en
        cooldown ou blacklisté est retiré de la rotation AVANT l'attribution des chunks.
        Un wallet inéligible ne reçoit aucun chunk — il ne travaille pas pour rien.
        """
        if not workers:
            raise PoolError("Au moins un worker requis")
        if visibility not in ("private", "public", "group"):
            raise PoolError("visibility invalide")
        if visibility == "group" and not group_id:
            raise PoolError("group_id requis pour visibility=group")
        if not encrypt_transport:
            raise PoolError("encrypt_transport obligatoire pour pool distribué")

        # ── PRE-FILTRE WORKERS : exclure les wallets inéligibles ─────────────
        eligible_workers = workers
        if anti_sybil is not None:
            eligible_workers = []
            for w in workers:
                addr = w.get("contributor_address") or w.get("node_id", "")
                ok, reason = anti_sybil.is_eligible(addr, source=source)
                if ok:
                    eligible_workers.append(w)
                else:
                    logger.warning(
                        "Pool PRE-FILTER: worker node=%s addr=%s exclu avant job — %s",
                        w.get("node_id", "?")[:12], addr[:12], reason,
                    )
            if not eligible_workers:
                raise PoolError(
                    "Aucun worker éligible après pré-filtrage anti-Sybil — "
                    "tous les wallets candidats sont en cooldown ou suspendus. "
                    "Attendez la fin du cooldown avant de relancer."
                )
            if len(eligible_workers) < len(workers):
                logger.info(
                    "Pool PRE-FILTER: %d/%d workers éligibles pour ce job",
                    len(eligible_workers), len(workers),
                )

        pieces = split_text_chunks(text, chunk_chars=chunk_chars)
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        chunks: list[PoolChunk] = []

        for i, piece in enumerate(pieces):
            worker = eligible_workers[i % len(eligible_workers)]
            w_node = worker["node_id"]
            w_kem = worker["kem_public_hex"]
            envelope = encrypt_chunk_payload(piece, w_kem)
            chunk = PoolChunk(
                chunk_id=f"chk_{uuid.uuid4().hex[:10]}",
                chunk_index=i,
                worker_node_id=w_node,
                worker_kem_public_hex=w_kem,
                envelope=envelope,
            )
            chunks.append(chunk)

        job = PoolJob(
            job_id=job_id,
            owner_node_id=self.node_id,
            owner_kem_public_hex=self.kem_public_hex,
            visibility=visibility,
            status="dispatched",
            chunks=chunks,
            created_at=self._now(),
            actor_address=actor_address,
            wallet_name=wallet_name,
            group_id=group_id,
            encrypt_transport=encrypt_transport,
        )
        self._update_job(job)
        logger.info("Pool job %s created chunks=%d visibility=%s", job_id, len(chunks), visibility)
        return job

    def dispatch_to_peers(self, job: PoolJob, peer_urls: dict[str, str]) -> list[dict[str, Any]]:
        """Envoie les chunks aux workers distants via HTTP chiffré."""
        results: list[dict[str, Any]] = []
        for chunk in job.chunks:
            if chunk.worker_node_id == self.node_id:
                self._append_incoming({
                    "job_id": job.job_id,
                    "owner_node_id": job.owner_node_id,
                    "owner_kem_public_hex": job.owner_kem_public_hex,
                    "owner_callback_base": peer_urls.get(job.owner_node_id, ""),
                    "visibility": job.visibility,
                    "group_id": job.group_id,
                    **chunk.to_dict(),
                })
                results.append({"chunk_id": chunk.chunk_id, "target": "local", "ok": True})
                continue
            base = peer_urls.get(chunk.worker_node_id)
            if not base:
                results.append({"chunk_id": chunk.chunk_id, "ok": False, "error": "peer url unknown"})
                continue
            payload = {
                "job_id": job.job_id,
                "owner_node_id": job.owner_node_id,
                "owner_kem_public_hex": job.owner_kem_public_hex,
                "owner_callback_base": peer_urls.get(job.owner_node_id, ""),
                "visibility": job.visibility,
                "group_id": job.group_id,
                **chunk.to_dict(),
            }
            try:
                with httpx.Client(timeout=30.0) as client:
                    r = client.post(f"{base.rstrip('/')}/api/v1/pool/incoming", json=payload)
                    r.raise_for_status()
                results.append({"chunk_id": chunk.chunk_id, "target": base, "ok": True})
            except Exception as exc:
                logger.error("Dispatch chunk %s failed: %s", chunk.chunk_id, exc)
                results.append({"chunk_id": chunk.chunk_id, "ok": False, "error": str(exc)})
        return results

    def receive_incoming_chunk(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Worker reçoit un chunk chiffré depuis le coordinateur."""
        required = {"job_id", "chunk_id", "envelope", "owner_kem_public_hex"}
        if not required.issubset(payload.keys()):
            raise PoolError(f"Payload incomplet — requis: {required}")
        items = self._read_incoming()
        if any(i.get("chunk_id") == payload["chunk_id"] for i in items):
            return {"chunk_id": payload["chunk_id"], "status": "already_received"}
        payload["status"] = "pending"
        payload["received_at"] = self._now()
        items.append(payload)
        self._save_incoming_all(items)
        return {"chunk_id": payload["chunk_id"], "status": "queued"}

    def list_incoming(self) -> list[dict[str, Any]]:
        return [i for i in self._read_incoming() if i.get("status") == "pending"]

    def process_incoming_chunk(
        self,
        chunk_id: str,
        *,
        contributor_address: str,
        sign_fn: Callable[[bytes], str] | None = None,
    ) -> dict[str, Any]:
        """Déchiffre, exécute raisonnement local, renvoie résultat chiffré au owner."""
        items = self._read_incoming()
        target = next((i for i in items if i.get("chunk_id") == chunk_id), None)
        if not target:
            raise PoolError(f"Chunk incoming introuvable: {chunk_id}")

        text = decrypt_chunk_payload(target["envelope"], self.kem_secret_hex)
        reasoning = self._run_reasoning(text)
        graph_id = reasoning["graph_id"]
        pol_score = float(reasoning["pol_score"])
        graph_root = reasoning.get("graph_root", graph_id)
        node_count = int(reasoning.get("node_count", 0))

        signature = ""
        if sign_fn:
            signature = sign_fn(graph_root.encode("utf-8"))

        result_body = {
            "chunk_id": chunk_id,
            "job_id": target["job_id"],
            "worker_node_id": self.node_id,
            "graph_id": graph_id,
            "pol_score": pol_score,
            "graph_root": graph_root,
            "node_count": node_count,
            "contributor_address": contributor_address,
            "signature": signature,
        }
        result_envelope = encrypt_result_payload(result_body, target["owner_kem_public_hex"])

        callback = target.get("owner_callback_base", "")
        owner_node = target.get("owner_node_id", "")
        if owner_node == self.node_id:
            self.receive_result(target["job_id"], chunk_id, result_envelope)
        elif callback:
            try:
                with httpx.Client(timeout=60.0) as client:
                    r = client.post(
                        f"{callback.rstrip('/')}/api/v1/pool/jobs/{target['job_id']}/results",
                        json={"chunk_id": chunk_id, "result_envelope": result_envelope},
                    )
                    r.raise_for_status()
            except Exception as exc:
                logger.error("Callback result failed: %s", exc)
                raise PoolError(f"Envoi résultat au owner échoué: {exc}") from exc

        for i in items:
            if i.get("chunk_id") == chunk_id:
                i["status"] = "done"
                i["result_envelope"] = result_envelope
        self._save_incoming_all(items)

        return {"chunk_id": chunk_id, "pol_score": pol_score, "graph_id": graph_id, "encrypted": True}

    def receive_result(self, job_id: str, chunk_id: str, result_envelope: dict[str, str]) -> dict[str, Any]:
        """Owner reçoit résultat chiffré d'un worker."""
        job = self.get_job(job_id)
        if not job:
            raise PoolError("Job introuvable")
        result = decrypt_result_payload(result_envelope, self.kem_secret_hex)
        if result.get("chunk_id") != chunk_id:
            raise PoolError("chunk_id mismatch")

        for chunk in job.chunks:
            if chunk.chunk_id == chunk_id:
                chunk.status = "done"
                chunk.result_envelope = result_envelope
                chunk.pol_score = float(result.get("pol_score", 0))
                chunk.graph_id = result.get("graph_id")
                chunk.node_count = int(result.get("node_count", 0))
                chunk.contributor_address = result.get("contributor_address")
                chunk.signature = result.get("signature", "")
                break
        else:
            raise PoolError("Chunk inconnu dans job")

        if all(c.status == "done" for c in job.chunks):
            job.status = "ready_finalize"
        self._update_job(job)
        return {"job_id": job_id, "chunk_id": chunk_id, "status": job.status}

    def finalize_job(self, job_id: str, full_text: str) -> dict[str, Any]:
        """Fusionne contributions, graphe final + bloc (si finalize callback configuré)."""
        job = self.get_job(job_id)
        if not job:
            raise PoolError("Job introuvable")
        pending = [c for c in job.chunks if c.status != "done"]
        if pending:
            raise PoolError(f"Chunks incomplets: {len(pending)} restants")

        extra_contributors = []
        for c in job.chunks:
            if c.contributor_address and c.pol_score is not None:
                # Chunks traités par l'owner localement → rôle reasoner via pipeline finalize
                if job.actor_address and c.contributor_address == job.actor_address:
                    continue
                extra_contributors.append({
                    "address": c.contributor_address,
                    "pol_score": c.pol_score,
                    "signature": c.signature or "",
                    "role": "pool_worker",
                })

        if self._finalize_job:
            out = self._finalize_job(job, full_text, extra_contributors)
            job.status = "completed"
            job.final_graph_id = out.get("graph_id")
            job.block_index = out.get("block_index")
            self._update_job(job)
            return out

        job.status = "completed"
        self._update_job(job)
        return {
            "job_id": job_id,
            "status": "completed",
            "contributors": extra_contributors,
            "message": "Finalize callback non configuré — contributors collectés",
        }

    def process_local_pending(
        self,
        *,
        contributor_address: str,
        sign_fn: Callable[[bytes], str] | None = None,
    ) -> list[dict[str, Any]]:
        """Traite tous les chunks incoming en attente sur ce nœud."""
        results = []
        for item in self.list_incoming():
            try:
                r = self.process_incoming_chunk(
                    item["chunk_id"],
                    contributor_address=contributor_address,
                    sign_fn=sign_fn,
                )
                results.append({"ok": True, **r})
            except Exception as exc:
                results.append({"ok": False, "chunk_id": item.get("chunk_id"), "error": str(exc)})
        return results
