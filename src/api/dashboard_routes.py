"""Dashboard utility routes — logs réels, founders, minage (PROTOCOLE: pas de mock)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from src.artcb.economics.emission import issued_reward_satoshi
from src.artcb.tokenomics import EMISSION_MODEL, MAX_SUPPLY_SATOSHI, SATOSHI_PER_ARTCB

logger = logging.getLogger("artcb.api.dashboard")
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _settings(request: Request):
    return request.app.state.artcb.settings


@router.get("/logs/demo-live")
def demo_live_log(request: Request) -> dict:
    settings = _settings(request)
    path = settings.log_dir / "demo_live_latest.txt"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="demo_live_latest.txt not found")
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.strip().splitlines()
    return {"path": str(path), "lines": lines, "line_count": len(lines), "content": content}


@router.get("/logs/mining-latest")
def mining_latest_log(request: Request) -> dict:
    settings = _settings(request)
    log_dir = settings.log_dir
    candidates = sorted(log_dir.glob("mining_results_*.json"), reverse=True)
    if not candidates:
        raise HTTPException(status_code=404, detail="no mining_results_*.json in logs/")
    path = candidates[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"path": str(path), "data": data}


@router.get("/founders/allocation")
def founders_allocation(request: Request) -> dict:
    """Retourne l'allocation founders — priorité v2 (2 comptes) sur v1 (5 founders)."""
    settings = _settings(request)
    data_dir = settings.data_dir / "founders"

    # Priorité v2 (Créateur 1M + Dev 1M) — puis fallback v1 (5 founders legacy)
    for fname in ("founders_allocation_v2.json", "founders_allocation.json"):
        path = data_dir / fname
        if not path.is_file():
            path = Path("data/founders") / fname
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            # Normaliser le format v2 → v1 pour la compatibilité frontend
            if raw.get("version") == "2.0" and "founders" in raw:
                balances = [
                    {
                        "founder_id": i + 1,
                        "name": f["name"],
                        "address": f["address"],
                        "balance_artcb": f["allocation_artcb"],
                        "is_creator": f.get("is_creator", False),
                        "vote_weight": f.get("vote_weight", 1),
                    }
                    for i, f in enumerate(raw["founders"])
                ]
                return {
                    "version": "2.0",
                    "founders_total_artcb": sum(f["allocation_artcb"] for f in raw["founders"]),
                    "founders_percentage": round(
                        sum(f["allocation_artcb"] for f in raw["founders"]) / 21_000_000 * 100, 2
                    ),
                    "balances": balances,
                }
            return raw

    raise HTTPException(status_code=404, detail="founders_allocation not found")


@router.get("/mining/status")
def mining_status(request: Request) -> dict:
    state = request.app.state.artcb
    blocks = state.chain._read_all_blocks()
    block_count = len(blocks)
    issued_so_far = sum(int(b.get("block_reward", 0) or 0) for b in blocks)
    current_reward_satoshi = issued_reward_satoshi(
        block_count,
        issued_so_far_satoshi=issued_so_far,
    )
    remaining_satoshi = max(0, MAX_SUPPLY_SATOSHI - issued_so_far)
    velocity_per_day = state.chain._observe_velocity_per_day(86_400)
    total_rewards = issued_so_far
    return {
        "block_count": block_count,
        "current_reward_artcb": current_reward_satoshi / 1e8,
        "current_reward_satoshi": current_reward_satoshi,
        "emission_model": EMISSION_MODEL,
        "halving_interval": None,
        "halving_removed": True,
        "blocks_until_halving": None,
        "next_halving_at": None,
        "remaining_supply_artcb": remaining_satoshi / SATOSHI_PER_ARTCB,
        "total_rewards_artcb": total_rewards / 1e8,
        "pol_score": state.pol_state.get("pol_score"),
        "velocity_blocks_per_day": velocity_per_day,
        "epoch_fixe": None,
        "epoch_dynamique": None,
        "epoch_total": None,
    }


@router.get("/wallet/{address}/rewards")
def wallet_rewards(address: str, request: Request) -> dict:
    state = request.app.state.artcb
    blocks = state.chain._read_all_blocks()
    rewards: list[dict] = []
    total = 0
    for block in blocks:
        for c in block.get("contributors", []):
            if c.get("address") == address:
                sat = int(c.get("reward_satoshi", 0))
                total += sat
                rewards.append({
                    "block_index": block.get("index"),
                    "reward_satoshi": sat,
                    "reward_artcb": sat / 1e8,
                    "pol_score": c.get("pol_score"),
                    "timestamp": block.get("timestamp"),
                })
    return {"address": address, "rewards": rewards, "total_satoshi": total, "total_artcb": total / 1e8}
