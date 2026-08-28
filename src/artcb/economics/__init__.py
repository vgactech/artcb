"""ARTCB economic protocol layer (R(H), HBP, owner decay, settlement) — D-024 + rapport 162."""

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
from src.artcb.economics.owner_decay import (
    OWNER_DECAY_K,
    fleet_owner_share,
    human_share,
    owner_share,
    payout_owner_share,
)
from src.artcb.economics.preblocks import PreBlockShare, partition_block_reward
from src.artcb.economics.settlement import (
    MachineContribution,
    SettlementResult,
    settle_block,
)

__all__ = [
    "H_REF",
    "OWNER_DECAY_K",
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
    "fleet_owner_share",
    "hbp_rate",
    "human_share",
    "issued_reward_satoshi",
    "owner_share",
    "partition_block_reward",
    "payout_owner_share",
    "population_reward_artcb",
    "schedule_reward_satoshi",
    "settle_block",
]
