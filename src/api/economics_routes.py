"""Economics protocol routes — R(H), HBP, owner decay, settlement preview.

Read-only preview plus job-provider mutations. No mocks: every figure is
computed by ``src.artcb.economics``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.economics.emission import (
    cumulative_schedule_artcb,
    issued_reward_satoshi,
    population_reward_artcb,
)
from src.artcb.economics.hbp import hbp_rate
from src.artcb.economics.human_binding import HumanBindingError
from src.artcb.economics.job_provider import JobProviderError
from src.artcb.economics.owner_decay import human_share, owner_share
from src.artcb.economics.preblocks import partition_block_reward
from src.artcb.economics.settlement import MachineContribution, settle_block
from src.artcb.tokenomics import (
    HALVING_INTERVAL,
    INITIAL_BLOCK_REWARD_ARTCB,
    MAX_SUPPLY_ARTCB,
    SATOSHI_PER_ARTCB,
)

logger = logging.getLogger("artcb.api.economics")
router = APIRouter(prefix="/api/v1/economics", tags=["economics"])


class MachineIn(BaseModel):
    machine_id: str
    owner_address: str
    machine_index: int = Field(..., ge=1)
    bound_human_address: str | None = None
    work_weight: float = Field(..., ge=0)


class SettleIn(BaseModel):
    r_block_satoshi: int | None = None
    verified_humans: float = Field(0, ge=0)
    block_index: int = Field(0, ge=0)
    machines: list[MachineIn]


class PartitionIn(BaseModel):
    r_block_satoshi: int = Field(..., ge=0)
    weights: list[float]


class JobSubmitIn(BaseModel):
    provider_address: str
    payload: str


class JobPartitionIn(BaseModel):
    worker_capacities: list[float]
    r_block_satoshi: int = Field(..., ge=0)


class MachineRegisterIn(BaseModel):
    machine_id: str
    owner_address: str
    bound_human_address: str | None = None
    device_fingerprint: str | None = None


def _state(request: Request):
    return request.app.state.artcb


@router.get("/params")
def economics_params() -> dict:
    return {
        "max_supply_artcb": MAX_SUPPLY_ARTCB,
        "initial_block_reward_artcb": INITIAL_BLOCK_REWARD_ARTCB,
        "halving_interval": HALVING_INTERVAL,
        "identity": (
            f"{INITIAL_BLOCK_REWARD_ARTCB} × {HALVING_INTERVAL} × 2 = "
            f"{INITIAL_BLOCK_REWARD_ARTCB * HALVING_INTERVAL * 2:.0f}"
        ),
        "r_h": "50 * (max(H, 1e6) / 1e6) ** (-ln(50)/ln(64))",
        "hbp": "10% → 60% @ 4.15e9 → 20% @ 8.3e9",
        "owner_decay": "P(1)=100%; P(n≥2): 50% → 10% continuous",
    }


@router.get("/emission")
def economics_emission(
    block_index: int = 0,
    verified_humans: float = 0,
    extra_epochs: int = 0,
) -> dict:
    if block_index < 0 or verified_humans < 0 or extra_epochs < 0:
        raise HTTPException(status_code=400, detail="indices and counts must be >= 0")
    issued = issued_reward_satoshi(
        block_index,
        verified_humans=verified_humans,
        extra_epochs=extra_epochs,
    )
    return {
        "block_index": block_index,
        "verified_humans": verified_humans,
        "r_h_artcb": population_reward_artcb(verified_humans),
        "issued_satoshi": issued,
        "issued_artcb": issued / SATOSHI_PER_ARTCB,
        "cumulative_schedule_artcb": cumulative_schedule_artcb(block_index + 1),
    }


@router.get("/hbp")
def economics_hbp(verified_humans: float = 0) -> dict:
    if verified_humans < 0:
        raise HTTPException(status_code=400, detail="verified_humans must be >= 0")
    rate = hbp_rate(verified_humans)
    return {"verified_humans": verified_humans, "hbp_rate": rate, "hbp_percent": rate * 100}


@router.get("/owner-share")
def economics_owner_share(machine_index: int = 1) -> dict:
    if machine_index < 1:
        raise HTTPException(status_code=400, detail="machine_index must be >= 1")
    p = owner_share(machine_index)
    return {
        "machine_index": machine_index,
        "owner_share": p,
        "human_share": human_share(machine_index),
    }


@router.post("/settle")
def economics_settle(body: SettleIn) -> dict:
    r_block = body.r_block_satoshi
    if r_block is None:
        r_block = issued_reward_satoshi(
            body.block_index,
            verified_humans=body.verified_humans,
        )
    try:
        result = settle_block(
            r_block_satoshi=r_block,
            verified_humans=body.verified_humans,
            machines=[
                MachineContribution(
                    machine_id=m.machine_id,
                    owner_address=m.owner_address,
                    machine_index=m.machine_index,
                    bound_human_address=m.bound_human_address,
                    work_weight=m.work_weight,
                )
                for m in body.machines
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.debug("settle preview R=%s humans=%s total=%s", r_block, body.verified_humans, result.total_satoshi)
    return {
        "r_block_satoshi": result.r_block_satoshi,
        "r_block_artcb": result.r_block_satoshi / SATOSHI_PER_ARTCB,
        "verified_humans": result.verified_humans,
        "hbp_rate": result.hbp_rate,
        "work_pool_satoshi": result.work_pool_satoshi,
        "hbp_pool_satoshi": result.hbp_pool_satoshi,
        "total_satoshi": result.total_satoshi,
        "by_address_satoshi": result.by_address(),
        "lines": [
            {
                "address": line.address,
                "role": line.role,
                "machine_id": line.machine_id,
                "reward_satoshi": line.reward_satoshi,
                "reward_artcb": line.reward_satoshi / SATOSHI_PER_ARTCB,
            }
            for line in result.lines
        ],
    }


@router.post("/preblocks/partition")
def economics_preblocks(body: PartitionIn) -> dict:
    try:
        shares = partition_block_reward(body.r_block_satoshi, body.weights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "r_block_satoshi": body.r_block_satoshi,
        "total_satoshi": sum(s.reward_satoshi for s in shares),
        "preblocks": [
            {
                "preblock_id": s.preblock_id,
                "weight": s.weight,
                "reward_satoshi": s.reward_satoshi,
            }
            for s in shares
        ],
    }


@router.post("/machines")
def register_machine(body: MachineRegisterIn, request: Request) -> dict:
    registry = _state(request).machine_registry
    try:
        record = registry.register(
            machine_id=body.machine_id,
            owner_address=body.owner_address,
            bound_human_address=body.bound_human_address,
            device_fingerprint=body.device_fingerprint,
        )
    except HumanBindingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record.to_dict()


@router.get("/machines/{owner_address}")
def list_machines(owner_address: str, request: Request) -> dict:
    registry = _state(request).machine_registry
    records = registry.machines_of(owner_address)
    return {
        "owner_address": owner_address,
        "count": len(records),
        "machines": [r.to_dict() for r in records],
    }


@router.post("/jobs")
def submit_job(body: JobSubmitIn, request: Request) -> dict:
    provider = _state(request).job_provider
    try:
        job = provider.submit(provider_address=body.provider_address, payload=body.payload)
    except JobProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job.to_dict()


@router.post("/jobs/{job_id}/partition")
def partition_job(job_id: str, body: JobPartitionIn, request: Request) -> dict:
    provider = _state(request).job_provider
    try:
        shares = provider.partition(
            job_id,
            worker_capacities=body.worker_capacities,
            r_block_satoshi=body.r_block_satoshi,
        )
    except JobProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "job_id": job_id,
        "r_block_satoshi": body.r_block_satoshi,
        "total_satoshi": sum(s.reward_satoshi for s in shares),
        "preblocks": [
            {
                "preblock_id": s.preblock_id,
                "weight": s.weight,
                "reward_satoshi": s.reward_satoshi,
            }
            for s in shares
        ],
    }
