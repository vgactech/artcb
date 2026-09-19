"""Politique sécurité pool — chiffrement obligatoire si distribué, validation visibilité."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

from typing import TYPE_CHECKING

from src.artcb.crypto.kem import kem_enabled

if TYPE_CHECKING:
    from src.artcb.groups.manager import GroupManager


class PoolPolicyError(Exception):
    """Violation politique pool."""


VALID_VISIBILITIES = frozenset({"private", "public", "group"})


def validate_pool_options(
    *,
    use_distributed: bool,
    encrypt_transport: bool,
    visibility: str,
    group_id: str | None = None,
    actor_address: str | None = None,
    groups: GroupManager | None = None,
) -> None:
    """
    Règles :
    - Calcul local (non distribué) : pas de transport réseau pool.
    - Calcul distribué : chiffrement ML-KEM **obligatoire** (encrypt_transport=true).
    - visibility group : group_id + membre acteur requis.
  """
    if visibility not in VALID_VISIBILITIES:
        raise PoolPolicyError(f"visibility invalide: {visibility}")

    if not use_distributed:
        return

    if not encrypt_transport:
        raise PoolPolicyError(
            "Calcul distribué refusé sans chiffrement E2E — activez encrypt_transport "
            "ou désactivez use_distributed_pool pour calcul 100 % local"
        )

    if not kem_enabled():
        raise PoolPolicyError("ML-KEM désactivé — impossible d'activer le pool distribué chiffré")

    if visibility == "group":
        if not group_id:
            raise PoolPolicyError("group_id requis pour visibility=group")
        if not actor_address:
            raise PoolPolicyError("actor_address requis pour visibility=group")
        if groups and not groups.is_member(group_id, actor_address):
            raise PoolPolicyError("actor non membre du groupe")
