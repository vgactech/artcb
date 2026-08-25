"""ARTCB economic protocol layer (R(H), HBP, owner decay, settlement)."""

from src.artcb.economics.emission import (
    H_REF,
    REWARD_POPULATION_ALPHA,
    asymptotic_schedule_supply_satoshi,
    cumulative_schedule_artcb,
    issued_reward_satoshi,
    population_reward_artcb,
    schedule_reward_satoshi,
)
from src.artcb.economics.hbp import hbp_rate
from src.artcb.economics.human_binding import (
    HumanBindingError,
    MachineRecord,
    MachineRegistry,
)
from src.artcb.economics.job_provider import JobProvider, JobProviderError, JobRecord
from src.artcb.economics.owner_decay import human_share, owner_share
from src.artcb.economics.preblocks import PreBlockShare, partition_block_reward
from src.artcb.economics.settlement import (
    MachineContribution,
    SettlementResult,
    settle_block,
)

__all__ = [
    "H_REF",
    "HumanBindingError",
    "JobProvider",
    "JobProviderError",
    "JobRecord",
    "MachineContribution",
    "MachineRecord",
    "MachineRegistry",
    "PreBlockShare",
    "REWARD_POPULATION_ALPHA",
    "SettlementResult",
    "asymptotic_schedule_supply_satoshi",
    "cumulative_schedule_artcb",
    "hbp_rate",
    "human_share",
    "issued_reward_satoshi",
    "owner_share",
    "partition_block_reward",
    "population_reward_artcb",
    "schedule_reward_satoshi",
    "settle_block",
]
