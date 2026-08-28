"""Provider/Worker split — non-zero provider scores must actually split the PoL pool."""

from __future__ import annotations

from src.artcb.economics.provider_worker import PROVIDER_START, split_pol_pool
from src.artcb.economics.settlement import MachineContribution, settle_block
from src.artcb.tokenomics import SATOSHI_PER_ARTCB


def test_split_pol_pool_two_providers_fifty_fifty() -> None:
    provider, worker, p_pool, w_pool = split_pol_pool(
        1_000_000,
        provider_share=PROVIDER_START,
        provider_scores={"JP1": 1.0, "JP2": 1.0},
        worker_scores={"M1": 1.0, "M2": 1.0},
    )
    assert p_pool + w_pool == 1_000_000
    assert abs(p_pool - w_pool) <= 1
    assert provider["JP1"] > 0 and provider["JP2"] > 0
    assert abs(provider["JP1"] - provider["JP2"]) <= 1
    assert sum(provider.values()) + sum(worker.values()) == 1_000_000


def test_split_pol_pool_no_providers_workers_take_all() -> None:
    provider, worker, p_pool, w_pool = split_pol_pool(
        1_000_000,
        provider_share=PROVIDER_START,
        provider_scores={},
        worker_scores={"M1": 1.0},
    )
    assert provider == {}
    assert p_pool == 0
    assert w_pool == 1_000_000
    assert worker["M1"] == 1_000_000


def test_settle_block_exercises_provider_split() -> None:
    r_block = 50 * SATOSHI_PER_ARTCB
    machines = [
        MachineContribution("A:M1", "A", 1, None, 1.0, n_economic=1, is_first_machine=True),
    ]
    result = settle_block(
        r_block_satoshi=r_block,
        h_adult=5,
        machines=machines,
        provider_scores={"JP1": 2.0, "JP2": 2.0},
    )
    assert result.total_satoshi == r_block
    assert result.provider_pool_satoshi > 0
    assert result.worker_pool_satoshi > 0
    assert abs(result.provider_pool_satoshi - result.worker_pool_satoshi) <= 1
    by_addr = result.by_address()
    assert by_addr["JP1"] > 0
    assert by_addr["JP2"] > 0
    roles = {line.role for line in result.lines if line.address in {"JP1", "JP2"}}
    assert roles == {"provider"}
