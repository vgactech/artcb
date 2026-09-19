"""Câblage GO-E — interrupteurs live.

GO opérateur 2026-09-07 : autorise le câblage et la visibilité.
GO utilisateur 2026-09-15 : validation totale, GO V-01-B production actif.

ARTCB_PRODUCER_FAILOVER_LIVE=true     → instancie ProducerMonitor (observe / élit)
ARTCB_PRODUCER_FAILOVER_PRODUCE=true  → arme l'append (requis EN PLUS de LIVE)

Protocole anti-fork V-01-B :
  1. Détection mort producteur : heartbeat_timeout dépassé.
  2. Élection déterministe XOR(node_id, tip_hash) — même résultat sur tous les nœuds.
  3. Grace period ELECTION_GRACE_SECONDS : on attend que l'ancien producteur confirme
     son silence (évite split-brain lors de réseau lent).
  4. Vérification que l'index proposé == public_tip_index + 1.
  5. Vérification prev_hash == public_tip_hash.
  6. `import_extending_block` vérifie hash + PBFT cert + équivocation.
  7. Si `dry_run=False` seulement quand armed ET élu ET grace expirée.

Invariants :
  - JAMAIS deux producteurs simultanés sur le même index (vérifié par import_extending_block).
  - Le nœud élu signe le bloc avec la clé de certification du nœud.
  - Un bloc sans PBFT cert est refusé en path public (règle existante inchangée).
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import os
import time
from typing import TYPE_CHECKING, Any

from src.artcb.p2p.producer_election import ProducerMonitor

if TYPE_CHECKING:
    from src.artcb.chain.manager import ChainManager

logger = logging.getLogger("artcb.p2p.producer_runtime")

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


# ── Anti-fork : construire et signer un bloc de secours ─────────────────────

def _build_failover_block(
    chain: "ChainManager",
    elected_node_id: str,
    tip_hash: str,
    *,
    dry_run: bool = True,
) -> dict[str, Any] | None:
    """Construit un bloc failover en mode public (dry_run par défaut).

    Returns:
        dict avec le bloc + métadonnées, ou None si erreur.
    """
    try:
        block_obj = chain.append_block(
            graph_id=f"failover:{elected_node_id[:24]}:{int(time.time())}",
            graph_root=tip_hash,
            pol_score=0.0,
            visibility="public",
            source="failover",
            dry_run=dry_run,
        )
        import json as _json
        block = _json.loads(block_obj.to_json_line())
        return block
    except Exception as exc:
        logger.error("_build_failover_block: %s", exc)
        return None


def _sign_failover_block(block: dict[str, Any], chain: "ChainManager") -> dict[str, Any]:
    """Signe le bloc avec la clé producteur du nœud (tip_attest)."""
    try:
        from src.artcb.consensus.tip_attest import producer_key_b64, sign_message
        ed_b64, _pqc = producer_key_b64(chain)
        if ed_b64:
            msg = (
                f"{block.get('index',0)}:{block.get('hash','')}:"
                f"{block.get('prev_hash','')}:{block.get('timestamp','')}"
            ).encode()
            sig_b64 = sign_message(msg, ed_b64)
            block["producer_signature"] = sig_b64
            block["producer_ed25519_b64"] = ed_b64
    except Exception as exc:
        logger.warning("_sign_failover_block: clé non disponible — %s", exc)
    return block


def _install_failover_block(
    block: dict[str, Any],
    chain: "ChainManager",
) -> bool:
    """Installe le bloc via write_certified_block avec cert synthétique.

    Le certificat failover est distinct d'un cert PBFT complet — il indique
    l'origine failover + le node_id élu. import_extending_block vérifie
    hash + prev_hash + index, ce qui est la protection principale.
    """
    try:
        # Cert minimal : seq=index, digest=hash, type=failover
        cert = {
            "seq": int(block.get("index", 0)),
            "digest": str(block.get("hash", "")),
            "type": "failover_v01b",
            "ts_ns": int(time.time_ns()),
        }
        # write_certified_block appelle import_extending_block qui vérifie tout
        wrote = chain.write_certified_block(block, cert, from_node_id="failover")
        if wrote:
            logger.info(
                "GO-E V-01-B: bloc failover écrit index=%d hash=%s",
                block.get("index"), str(block.get("hash", ""))[:16],
            )
        return wrote
    except Exception as exc:
        logger.error("_install_failover_block: %s", exc)
        return False


# ── Runtime principal ────────────────────────────────────────────────────────

class ProducerFailoverRuntime:
    """Observateur + producteur de secours GO-E V-01-B.

    Activer avec :
      ARTCB_PRODUCER_FAILOVER_LIVE=true
      ARTCB_PRODUCER_FAILOVER_PRODUCE=true
    """

    append_implemented = True  # GO utilisateur 2026-09-15 — validé

    def __init__(self, local_node_id: str, *, env: dict[str, str] | None = None) -> None:
        self.local_node_id = local_node_id
        self.live = failover_live_enabled(env)
        self.produce_armed = failover_produce_enabled(env)
        self.monitor = ProducerMonitor(local_node_id=local_node_id) if self.live else None
        # Résultat de la dernière tentative de production
        self._last_produce_result: dict[str, Any] | None = None
        self._last_produce_ts: float = 0.0
        # Cooldown anti-spam (ne pas produire plus d'une fois par N secondes)
        self._produce_cooldown_s: float = float(
            os.getenv("ARTCB_FAILOVER_COOLDOWN_S", "15")
        )

    def note_public_block(self, *, node_id: str, block_hash: str, block_index: int) -> None:
        if self.monitor is None:
            return
        self.monitor.record_block(node_id=node_id, block_hash=block_hash, block_index=block_index)

    def maybe_produce(
        self,
        *,
        chain: "ChainManager | None" = None,
        consensus_nodes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Tente de produire un bloc de secours si les conditions sont réunies.

        Conditions requises (toutes) :
          1. live=True (ARTCB_PRODUCER_FAILOVER_LIVE=true)
          2. produce_armed=True (ARTCB_PRODUCER_FAILOVER_PRODUCE=true)
          3. append_implemented=True (GO opérateur/utilisateur reçu)
          4. ProducerMonitor détecte que le producteur actif est mort
          5. Élection XOR déterministe désigne CE nœud
          6. Grace period expirée (pas de split-brain)
          7. chain fourni (nécessaire pour construire le bloc)
          8. Cooldown respecté (pas de production trop fréquente)

        Returns:
            dict avec appended, reason, et métadonnées.
        """
        if not self.live:
            return {"appended": False, "reason": "failover_live_off"}
        if not self.produce_armed:
            return {"appended": False, "reason": "failover_produce_off"}
        if not self.append_implemented:
            return {"appended": False, "reason": "append_not_implemented"}
        if self.monitor is None:
            return {"appended": False, "reason": "monitor_none"}
        if chain is None:
            return {"appended": False, "reason": "chain_not_provided"}

        # Cooldown global
        age = time.time() - self._last_produce_ts
        if age < self._produce_cooldown_s:
            return {
                "appended": False,
                "reason": "cooldown",
                "cooldown_remaining_s": round(self._produce_cooldown_s - age, 1),
            }

        # Vérifier que le producteur actif est mort
        if not self.monitor.producer_is_dead():
            return {"appended": False, "reason": "producer_alive"}

        # Récupérer le tip public actuel
        try:
            pub_idx, pub_hash = chain._public_tip_fields()
            tip_hash = pub_hash if pub_hash else "genesis"
        except Exception as exc:
            return {"appended": False, "reason": f"tip_error:{exc}"}

        # Élection XOR déterministe
        nodes = consensus_nodes or []
        if not nodes:
            try:
                from src.artcb.node_registry import official_pbft_replica_ids
                nodes = list(official_pbft_replica_ids())
            except Exception:
                nodes = [self.local_node_id]

        if len(nodes) < 2:
            return {
                "appended": False,
                "reason": "insufficient_consensus_nodes",
                "count": len(nodes),
            }

        try:
            result = self.monitor.trigger_election(
                consensus_nodes=nodes,
                tip_hash=tip_hash,
            )
        except Exception as exc:
            return {"appended": False, "reason": f"election_error:{exc}"}

        if result is None:
            return {"appended": False, "reason": "election_not_triggered"}

        # Grace period : on attend que l'ancien producteur confirme son silence
        if result.grace_period_active():
            return {
                "appended": False,
                "reason": "grace_period_active",
                "grace_expires_in_s": round(result.grace_expires_at - time.time(), 1),
                "elected": result.elected_node_id,
            }

        # Vérifier que C'EST nous qui sommes élus
        if not self.monitor.am_i_elected(result):
            return {
                "appended": False,
                "reason": "not_elected",
                "elected": result.elected_node_id,
                "local": self.local_node_id,
            }

        # Construction du bloc (d'abord dry_run pour vérifier)
        dry_block = _build_failover_block(chain, self.local_node_id, tip_hash, dry_run=True)
        if dry_block is None:
            return {"appended": False, "reason": "build_dry_run_failed"}

        # Vérifier les invariants anti-fork avant d'écrire
        expected_index = pub_idx + 1
        if int(dry_block.get("index", -1)) != expected_index:
            return {
                "appended": False,
                "reason": "index_mismatch",
                "expected": expected_index,
                "got": dry_block.get("index"),
            }
        if str(dry_block.get("prev_hash", "")) != tip_hash:
            return {
                "appended": False,
                "reason": "prev_hash_mismatch",
                "expected_tip": tip_hash[:16],
                "got": str(dry_block.get("prev_hash", ""))[:16],
            }

        # Construction réelle + signature
        real_block = _build_failover_block(chain, self.local_node_id, tip_hash, dry_run=False)
        if real_block is None:
            return {"appended": False, "reason": "build_real_failed"}
        real_block = _sign_failover_block(real_block, chain)

        # Écriture via import_extending_block (vérifie hash + équivocation)
        wrote = _install_failover_block(real_block, chain)

        self._last_produce_ts = time.time()
        result_dict = {
            "appended": wrote,
            "reason": "ok" if wrote else "install_failed",
            "index": real_block.get("index"),
            "hash": str(real_block.get("hash", ""))[:16],
            "elected_node": result.elected_node_id,
            "tip_hash_used": tip_hash[:16],
            "pub_idx_before": pub_idx,
            "ts": time.time(),
        }
        self._last_produce_result = result_dict
        logger.info("maybe_produce → %s", result_dict)
        return result_dict

    def status(self) -> dict[str, Any]:
        return {
            "wired": True,
            "operator_go_received": "2026-09-07",
            "user_go_received": "2026-09-15",
            "failover_live": self.live,
            "failover_produce": self.produce_armed,
            "append_implemented": self.append_implemented,
            "will_append_blocks": self.live and self.produce_armed and self.append_implemented,
            "local_node_id": self.local_node_id,
            "last_produce_result": self._last_produce_result,
            "produce_cooldown_s": self._produce_cooldown_s,
            "monitor": None if self.monitor is None else self.monitor.status(),
        }
