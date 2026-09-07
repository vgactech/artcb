"""Câblage GO-E — interrupteurs live. N'append jamais un bloc par défaut.

GO opérateur 2026-09-07 (« GO ») : autorise ce câblage et la visibilité.
Ce n'est pas une D-0xx. Ce n'est pas V-01-B producteur exécuté.

ARTCB_PRODUCER_FAILOVER_LIVE=true     → instancie ProducerMonitor (observe / élit)
ARTCB_PRODUCER_FAILOVER_PRODUCE=true  → requis EN PLUS pour un futur append

Les deux défauts sont false. ``maybe_produce`` refuse toujours l'append
tant que ``append_implemented`` est false — volontaire : un env oublié
sur 4 nœuds ne doit pas forker le tip.
"""

from __future__ import annotations

import os
from typing import Any

from src.artcb.p2p.producer_election import ProducerMonitor

ENV_FAILOVER_LIVE = "ARTCB_PRODUCER_FAILOVER_LIVE"
ENV_FAILOVER_PRODUCE = "ARTCB_PRODUCER_FAILOVER_PRODUCE"

_TRUE = frozenset({"1", "true", "yes", "on"})


def failover_live_enabled(env: dict[str, str] | None = None) -> bool:
    src = env if env is not None else os.environ
    return str(src.get(ENV_FAILOVER_LIVE, "false")).strip().lower() in _TRUE


def failover_produce_enabled(env: dict[str, str] | None = None) -> bool:
    src = env if env is not None else os.environ
    if not failover_live_enabled(src):
        return False
    return str(src.get(ENV_FAILOVER_PRODUCE, "false")).strip().lower() in _TRUE


class ProducerFailoverRuntime:
    """Observateur optionnel. Pas un producteur mainnet."""

    append_implemented = False

    def __init__(self, local_node_id: str, *, env: dict[str, str] | None = None) -> None:
        self.local_node_id = local_node_id
        self.live = failover_live_enabled(env)
        self.produce_armed = failover_produce_enabled(env)
        self.monitor = ProducerMonitor(local_node_id=local_node_id) if self.live else None

    def note_public_block(self, *, node_id: str, block_hash: str, block_index: int) -> None:
        if self.monitor is None:
            return
        self.monitor.record_block(node_id=node_id, block_hash=block_hash, block_index=block_index)

    def maybe_produce(self) -> dict[str, Any]:
        """Refuse tout append. Le chemin d'écriture n'existe pas encore."""
        if not self.live:
            return {"appended": False, "reason": "failover_live_off"}
        if not self.produce_armed:
            return {"appended": False, "reason": "failover_produce_off"}
        return {
            "appended": False,
            "reason": "append_not_implemented",
            "detail": "GO-E câblé ; V-01-B append exige un GO dédié + implémentation anti-fork",
        }

    def status(self) -> dict[str, Any]:
        return {
            "wired": True,
            "operator_go_received": "2026-09-07",
            "operator_go_is_not_d0xx": True,
            "failover_live": self.live,
            "failover_produce": self.produce_armed,
            "append_implemented": self.append_implemented,
            "will_append_blocks": False,
            "local_node_id": self.local_node_id,
            "monitor": None if self.monitor is None else self.monitor.status(),
        }
