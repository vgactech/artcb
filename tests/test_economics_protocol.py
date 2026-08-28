"""Economic protocol — 21M hard cap + R(H) geopopulation (D-024).

210k block-index halving and velocity extra_epochs are removed from the live path.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.artcb.chain.manager import ChainManager
from src.artcb.economics.emission import (
    H_REF,
    issued_reward_satoshi,
    population_reward_artcb,
)
from src.artcb.economics.hbp import HBP_PEAK_HUMANS, hbp_rate
from src.artcb.economics.human_binding import HumanBindingError, MachineRegistry
from src.artcb.economics.job_provider import JobProvider
from src.artcb.economics.owner_decay import human_share, owner_share
from src.artcb.economics.preblocks import partition_block_reward
from src.artcb.economics.settlement import MachineContribution, settle_block
from src.artcb.tokenomics import (
    EMISSION_MODEL,
    INITIAL_BLOCK_REWARD_ARTCB,
    MAX_SUPPLY_ARTCB,
    MAX_SUPPLY_SATOSHI,
    SATOSHI_PER_ARTCB,
)


class TestEmissionIdentity:
    def test_constants_restore_21m_hard_cap_not_schedule(self):
        assert INITIAL_BLOCK_REWARD_ARTCB == 50.0
        assert MAX_SUPPLY_ARTCB == 21_000_000.0
        assert EMISSION_MODEL == "R(H)"

    def test_index_does_not_halve_reward(self):
        assert issued_reward_satoshi(0) == 50 * SATOSHI_PER_ARTCB
        assert issued_reward_satoshi(209_999) == 50 * SATOSHI_PER_ARTCB
        assert issued_reward_satoshi(210_000) == 50 * SATOSHI_PER_ARTCB
        assert issued_reward_satoshi(420_000) == 50 * SATOSHI_PER_ARTCB
        assert issued_reward_satoshi(64 * 210_000) == 50 * SATOSHI_PER_ARTCB

    def test_hard_cap_clips_last_block(self):
        almost = MAX_SUPPLY_SATOSHI - 1_000
        issued = issued_reward_satoshi(0, issued_so_far_satoshi=almost)
        assert issued == 1_000

    def test_velocity_extra_epochs_ignored(self):
        with_extra = issued_reward_satoshi(0, extra_epochs=12)
        without = issued_reward_satoshi(0, extra_epochs=0)
        assert with_extra == without == 50 * SATOSHI_PER_ARTCB


class TestPopulationReward:
    def test_anchors(self):
        assert population_reward_artcb(0) == pytest.approx(50.0)
        assert population_reward_artcb(H_REF) == pytest.approx(50.0)
        assert population_reward_artcb(10_000_000) == pytest.approx(5.7323, rel=1e-4)
        assert population_reward_artcb(100_000_000) == pytest.approx(0.6572, rel=1e-3)
        assert population_reward_artcb(1_000_000_000) == pytest.approx(0.07534, rel=1e-4)
        assert population_reward_artcb(64_000_000) == pytest.approx(1.0, rel=1e-6)

    def test_no_floor_at_one(self):
        assert population_reward_artcb(1_000_000_000) < 1.0
        assert population_reward_artcb(2_000_000_000) < population_reward_artcb(1_000_000_000)

    def test_issued_is_r_h_clipped_by_cap(self):
        genesis_at_1b = issued_reward_satoshi(0, verified_humans=1_000_000_000)
        assert genesis_at_1b < SATOSHI_PER_ARTCB
        assert genesis_at_1b == pytest.approx(
            population_reward_artcb(1_000_000_000) * SATOSHI_PER_ARTCB,
            rel=1e-6,
        )
        late_index_same = issued_reward_satoshi(210_000, verified_humans=1_000_000_000)
        assert late_index_same == genesis_at_1b


class TestHBP:
    def test_anchors(self):
        assert hbp_rate(0) == pytest.approx(0.10)
        assert hbp_rate(HBP_PEAK_HUMANS) == pytest.approx(0.60)
        assert hbp_rate(8_300_000_000) == pytest.approx(0.20)

    def test_one_hundred_million(self):
        assert hbp_rate(100_000_000) == pytest.approx(0.112048, rel=1e-4)

    def test_one_billion(self):
        assert hbp_rate(1_000_000_000) == pytest.approx(0.2205, rel=1e-3)


class TestOwnerDecay:
    def test_first_machine_is_full_owner(self):
        assert owner_share(1) == 1.0
        assert human_share(1) == 0.0

    def test_second_machine_is_half(self):
        assert owner_share(2) == pytest.approx(0.50)
        assert human_share(2) == pytest.approx(0.50)

    def test_user_examples_49_and_48(self):
        from src.artcb.economics.owner_decay import fleet_owner_share, payout_owner_share

        assert fleet_owner_share(3) == pytest.approx(0.49)
        assert fleet_owner_share(4) == pytest.approx(0.48, abs=5e-4)
        assert payout_owner_share(is_first_machine=True, n_economic=1_000_000) == 1.0
        assert payout_owner_share(is_first_machine=False, n_economic=3) == pytest.approx(0.49)

    def test_all_extras_share_same_p(self):
        from src.artcb.economics.owner_decay import payout_owner_share

        p = payout_owner_share(is_first_machine=False, n_economic=4)
        assert payout_owner_share(is_first_machine=False, n_economic=4) == p

    def test_strictly_decreasing_after_two(self):
        previous = owner_share(2)
        for n in (3, 4, 5, 10, 50, 100, 200):
            current = owner_share(n)
            assert current < previous
            previous = current
        # Fleet curve hits the 10% floor well before n=1000 (162 k from P(3)=49%).
        assert owner_share(10_000) == pytest.approx(0.10)
        assert owner_share(100_000) == pytest.approx(0.10)

    def test_floor_is_ten_percent(self):
        assert owner_share(10**12) == pytest.approx(0.10, abs=1e-4)
        assert owner_share(10**12) >= 0.10

    def test_legacy_38pct_at_1000_superseded(self):
        # Rapport 124 calibration is no longer live (user GO 162).
        assert owner_share(1_000) == pytest.approx(0.10, abs=1e-8)


class TestHumanBinding:
    def test_first_machine_no_third_party(self, tmp_path):
        registry = MachineRegistry(tmp_path / "machines.json")
        rec = registry.register(machine_id="A1", owner_address="A")
        assert rec.machine_index == 1
        assert rec.bound_human_address is None
        with pytest.raises(HumanBindingError):
            registry.register(
                machine_id="Z1",
                owner_address="Z",
                bound_human_address="Y",
            )
        other = registry.register(machine_id="C1", owner_address="C")
        assert other.machine_index == 1

    def test_additional_machine_requires_distinct_human(self, tmp_path):
        registry = MachineRegistry(tmp_path / "machines.json")
        registry.register(machine_id="A1", owner_address="A")
        with pytest.raises(HumanBindingError):
            registry.register(machine_id="A2", owner_address="A")
        with pytest.raises(HumanBindingError):
            registry.register(machine_id="A2", owner_address="A", bound_human_address="A")
        a2 = registry.register(machine_id="A2", owner_address="A", bound_human_address="B")
        assert a2.machine_index == 2
        with pytest.raises(HumanBindingError):
            registry.register(machine_id="A3", owner_address="A", bound_human_address="B")
        a3 = registry.register(machine_id="A3", owner_address="A", bound_human_address="C")
        assert a3.machine_index == 3

    def test_c1_independent_of_being_bound_on_a3(self, tmp_path):
        registry = MachineRegistry(tmp_path / "machines.json")
        registry.register(machine_id="A1", owner_address="A")
        registry.register(machine_id="A2", owner_address="A", bound_human_address="B")
        registry.register(machine_id="A3", owner_address="A", bound_human_address="C")
        c1 = registry.register(machine_id="C1", owner_address="C")
        assert c1.machine_index == 1
        assert owner_share(c1.machine_index) == 1.0


class TestPreblocks:
    def test_conservation(self):
        shares = partition_block_reward(5_000_000_000, [1, 1, 2])
        assert sum(s.reward_satoshi for s in shares) == 5_000_000_000
        assert shares[2].reward_satoshi == 2_500_000_000

    def test_never_mints_n_times_reward(self):
        r_block = 50 * SATOSHI_PER_ARTCB
        shares = partition_block_reward(r_block, [1, 1, 1, 1, 1])
        assert sum(s.reward_satoshi for s in shares) == r_block
        assert len(shares) == 5


class TestJobProvider:
    def test_submit_partition_settle(self, tmp_path):
        provider = JobProvider(tmp_path / "jobs.json")
        job = provider.submit(provider_address="artcb1provider", payload="learn chapter 1")
        r_block = 50 * SATOSHI_PER_ARTCB
        shares = provider.partition(
            job.job_id,
            worker_capacities=[1.0, 1.0, 2.0],
            r_block_satoshi=r_block,
        )
        assert sum(s.reward_satoshi for s in shares) == r_block
        settled = provider.mark_settled(job.job_id)
        assert settled.status == "settled"


class TestSettlementABCD:
    def _four_machines(self) -> list[MachineContribution]:
        return [
            MachineContribution("A1", "A", 1, None, 1.0),
            MachineContribution("A2", "A", 2, "B", 1.0),
            MachineContribution("A3", "A", 3, "C", 1.0),
            MachineContribution("D1", "D", 1, None, 1.0),
        ]

    def test_conservation_at_100m_with_r0_50(self):
        r_block = 50 * SATOSHI_PER_ARTCB
        result = settle_block(
            r_block_satoshi=r_block,
            verified_humans=100_000_000,
            machines=self._four_machines(),
        )
        assert result.total_satoshi == r_block
        assert result.hbp_rate == pytest.approx(0.112048, rel=1e-4)
        by_addr = result.by_address()
        assert set(by_addr) == {"A", "B", "C", "D"}
        assert by_addr["A"] > by_addr["D"]
        a3_owner = next(
            line.reward_satoshi
            for line in result.lines
            if line.machine_id == "A3" and line.role == "owner"
        )
        a3_human = next(
            line.reward_satoshi
            for line in result.lines
            if line.machine_id == "A3" and line.role == "human"
        )
        assert a3_human > a3_owner
        a2_owner = next(
            line.reward_satoshi
            for line in result.lines
            if line.machine_id == "A2" and line.role == "owner"
        )
        # 162: all extras share the same P(N_economic=3) = 49%
        assert a3_owner == a2_owner

    def test_dual_role_c_owns_c1_and_is_bound_on_a3(self):
        r_block = 50 * SATOSHI_PER_ARTCB
        machines = self._four_machines() + [
            MachineContribution("C1", "C", 1, None, 1.0),
        ]
        result = settle_block(
            r_block_satoshi=r_block,
            verified_humans=100_000_000,
            machines=machines,
        )
        assert result.total_satoshi == r_block
        roles_c = {line.role for line in result.lines if line.address == "C"}
        assert "human" in roles_c
        assert "owner" in roles_c
        assert "hbp" in roles_c

    def test_one_billion_hbp_and_r_h(self):
        r_h = population_reward_artcb(1_000_000_000)
        r_block = issued_reward_satoshi(0, verified_humans=1_000_000_000)
        result = settle_block(
            r_block_satoshi=r_block,
            verified_humans=1_000_000_000,
            machines=self._four_machines(),
        )
        assert result.total_satoshi == r_block
        assert result.hbp_rate == pytest.approx(0.2205, rel=1e-3)
        assert r_h == pytest.approx(0.07534, rel=1e-4)
        assert result.hbp_pool_satoshi / SATOSHI_PER_ARTCB == pytest.approx(0.01661, rel=2e-3)


class TestChainIntegration:
    def test_legacy_split_uses_50_artcb(self, tmp_path):
        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl", enable_security=False)
        block = chain.append_block(
            graph_id="g",
            graph_root="abc",
            pol_score=0.8,
            contributors=[{"address": "artcb1alice", "pol_score": 1.0, "signature": "s"}],
        )
        assert block.block_reward == 50 * SATOSHI_PER_ARTCB
        assert block.contributors[0]["reward_satoshi"] == 50 * SATOSHI_PER_ARTCB

    def test_machine_settlement_on_chain(self, tmp_path):
        chain = ChainManager(blocks_path=tmp_path / "blocks.jsonl", enable_security=False)
        block = chain.append_block(
            graph_id="g",
            graph_root="abc",
            pol_score=0.8,
            verified_humans=100_000_000,
            contributors=[
                {
                    "address": "A",
                    "pol_score": 1.0,
                    "signature": "s1",
                    "machine_id": "A1",
                    "owner_address": "A",
                    "machine_index": 1,
                },
                {
                    "address": "A",
                    "pol_score": 1.0,
                    "signature": "s2",
                    "machine_id": "A2",
                    "owner_address": "A",
                    "machine_index": 2,
                    "bound_human_address": "B",
                },
            ],
        )
        assert block.block_reward == pytest.approx(
            population_reward_artcb(100_000_000) * SATOSHI_PER_ARTCB, rel=1e-6
        )
        total = sum(c["reward_satoshi"] for c in block.contributors)
        assert total == block.block_reward
        assert block.economics is not None
        assert block.economics["hbp_rate"] == pytest.approx(0.112048, rel=1e-4)
        payload = json.loads(block.to_json_line())
        assert "economics" in payload


class TestEconomicsAPI:
    def test_params_and_settle_preview(self):
        client = TestClient(create_app())
        params = client.get("/api/v1/economics/params")
        assert params.status_code == 200
        assert params.json()["initial_block_reward_artcb"] == 50.0
        assert params.json()["halving_removed"] is True
        assert params.json()["halving_interval"] is None
        assert params.json()["emission_model"] == "R(H)"
        body = {
            "verified_humans": 100_000_000,
            "r_block_satoshi": 50 * SATOSHI_PER_ARTCB,
            "machines": [
                {
                    "machine_id": "A1",
                    "owner_address": "A",
                    "machine_index": 1,
                    "work_weight": 1,
                },
                {
                    "machine_id": "A2",
                    "owner_address": "A",
                    "machine_index": 2,
                    "bound_human_address": "B",
                    "work_weight": 1,
                },
                {
                    "machine_id": "A3",
                    "owner_address": "A",
                    "machine_index": 3,
                    "bound_human_address": "C",
                    "work_weight": 1,
                },
                {
                    "machine_id": "D1",
                    "owner_address": "D",
                    "machine_index": 1,
                    "work_weight": 1,
                },
            ],
        }
        resp = client.post("/api/v1/economics/settle", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_satoshi"] == data["r_block_satoshi"]
        assert data["r_block_artcb"] == pytest.approx(50.0)
