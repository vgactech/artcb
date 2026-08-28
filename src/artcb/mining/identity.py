"""Attach HumanID / MachineID / WorkID onto mining contributors (sim 164).

Legacy contributors without machine_index keep the historic PoL 50/50 split.
When a MachineRegistry is bound, each owner is expanded to their economic
machines so ChainManager.settle_block runs the protocol path.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger("artcb.mining.identity")


def enrich_contributors_with_identity(
    contributors: list[dict],
    *,
    machine_registry=None,
    human_registry=None,
    work_registry=None,
    job_id: str | None = None,
    graph_id: str | None = None,
) -> list[dict]:
    if not contributors:
        return contributors
    if all("machine_index" in c and "owner_address" in c for c in contributors):
        return _stamp_work_and_humans(
            contributors,
            human_registry=human_registry,
            work_registry=work_registry,
            job_id=job_id,
            graph_id=graph_id,
        )
    if machine_registry is None:
        logger.debug("identity attach skipped — no machine registry")
        return contributors

    expanded: list[dict] = []
    for contributor in contributors:
        address = str(contributor.get("address") or contributor.get("owner_address") or "")
        machines = machine_registry.economic_machines_of(address) if address else []
        if not machines:
            expanded.append(dict(contributor))
            continue
        n_econ = machine_registry.economic_count(address)
        weight = float(contributor.get("pol_score", contributor.get("work_weight", 0.0)))
        per = weight / max(1, len(machines))
        for machine in machines:
            row = dict(contributor)
            row["address"] = address
            row["owner_address"] = machine.owner_address
            row["machine_id"] = machine.machine_id
            row["machine_index"] = machine.machine_index
            row["bound_human_address"] = machine.bound_human_address
            row["is_first_machine"] = machine.is_first_machine or machine.machine_index == 1
            row["n_economic"] = n_econ
            row["work_weight"] = per
            row["pol_score"] = per
            expanded.append(row)
            logger.debug(
                "attached machine=%s index=%s owner=%s human=%s N=%s",
                machine.machine_id,
                machine.machine_index,
                machine.owner_address,
                machine.bound_human_address,
                n_econ,
            )
    if not all("machine_index" in c and "owner_address" in c for c in expanded):
        logger.debug("mixed identity/legacy contributors — keeping legacy PoL split")
        return contributors
    return _stamp_work_and_humans(
        expanded,
        human_registry=human_registry,
        work_registry=work_registry,
        job_id=job_id,
        graph_id=graph_id,
    )


def _stamp_work_and_humans(
    contributors: list[dict],
    *,
    human_registry=None,
    work_registry=None,
    job_id: str | None = None,
    graph_id: str | None = None,
) -> list[dict]:
    out: list[dict] = []
    for contributor in contributors:
        row = dict(contributor)
        owner = str(row.get("owner_address") or row.get("address") or "")
        bound = row.get("bound_human_address")
        if human_registry is not None:
            rec = human_registry.get_by_address(owner)
            if rec is not None:
                row["human_id"] = rec.human_id
                row["adult_verified"] = rec.adult_verified
            if bound:
                bound_rec = human_registry.get_by_address(str(bound))
                if bound_rec is not None:
                    row["bound_human_id"] = bound_rec.human_id
        if work_registry is not None and not row.get("work_id"):
            work_id = f"W-{uuid.uuid4().hex[:16]}"
            jid = str(job_id or graph_id or "mining")
            work_registry.create(work_id=work_id, job_id=jid)
            row["work_id"] = work_id
            row["job_id"] = jid
            logger.debug("minted WorkID %s job=%s", work_id, jid)
        out.append(row)
    return out


def identity_ready(contributor: dict[str, Any]) -> bool:
    return "machine_index" in contributor and "owner_address" in contributor
