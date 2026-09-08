"""Synchronisation P2P — blocs publics uniquement (jamais private en clair).

Official replica of the full book lives in ``official_replica.py``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

from src.artcb.chain import ffi
from src.artcb.chain.ffi import HASH_VERSION_V1, HASH_VERSION_V2
from src.artcb.chain.manager import ChainManager
from src.artcb.crypto.kem import KEMError, decrypt_payload, encrypt_payload
from src.artcb.p2p.node_identity import NodeIdentity
from src.artcb.p2p.peers import PeerManager, PeerRecord
from src.artcb.p2p.public_archive import PublicBlockArchive
from src.artcb.p2p.symbol_sync import SymbolSyncService
from src.artcb.authz.domains import is_converging_public_event

logger = logging.getLogger("artcb.p2p.sync")

ImportAction = Literal["reject", "archive_only", "append", "duplicate"]


@dataclass(frozen=True)
class ImportDecision:
    """Same verdict for receive and pull. One block → one action."""

    action: ImportAction
    reason: str


class P2PSyncError(Exception):
    """P2P sync failed."""


def decide_public_import(
    block: dict[str, Any],
    *,
    local_len: int,
    local_tip: str,
    local_hashes: set[str],
    structure_ok: bool,
    existing_at_index: dict[str, Any] | None = None,
    check_signature_envelope: bool = True,
) -> ImportDecision:
    """Deterministic import rule. receive and pull must call this same function.

    Order: visibility → structure/hash → duplicate → DOMAIN_COMMITMENT
    binding (when present) → equivocation (same index, other hash) →
    index → prev_hash → signature envelope / embedded key → append.

    A public block that extends the tip (correct index + prev_hash + hash
    + parseable signature) is appended. Forks stay off the tip.
    Two different hashes at the same index are evidence, not a merge.
    This is not PBFT view-change.
    """
    from src.artcb.consensus.byzantine_guard import (
        signature_envelope_ok,
        verify_offered_signature,
    )

    if block.get("visibility") != "public":
        return ImportDecision("reject", "not_public")
    if not structure_ok:
        return ImportDecision("reject", "hash_mismatch")
    block_hash = str(block.get("hash") or "")
    if block_hash and block_hash in local_hashes:
        return ImportDecision("duplicate", "already_on_chain")
    if is_converging_public_event(block):
        symbols = block.get("public_symbols") or {}
        if symbols.get("artcb_event") == "DOMAIN_COMMITMENT":
            if symbols.get("content_hash") and str(symbols.get("content_hash")) != str(block.get("graph_root") or ""):
                return ImportDecision("reject", "symbols_not_bound_to_hash")
            expected_gid = f"commit:{symbols.get('kind')}:{symbols.get('domain_id')}"
            if block.get("graph_id") and str(block.get("graph_id")) != expected_gid:
                return ImportDecision("reject", "symbols_not_bound_to_hash")
    try:
        index = int(block.get("index", -1))
    except (TypeError, ValueError):
        return ImportDecision("reject", "bad_index")
    if existing_at_index:
        held = str(existing_at_index.get("hash") or "")
        if block_hash and held == block_hash:
            return ImportDecision("duplicate", "already_on_chain")
        if block_hash and held and held != block_hash:
            return ImportDecision("reject", "equivocation")
    if index != local_len:
        return ImportDecision("reject", "wrong_index")
    if str(block.get("prev_hash") or "") != local_tip:
        return ImportDecision("reject", "wrong_prev_hash")
    if check_signature_envelope and not signature_envelope_ok(str(block.get("signature") or "")):
        return ImportDecision("reject", "invalid_signature")
    remote_sig = verify_offered_signature(block)
    if remote_sig is False:
        return ImportDecision("reject", "invalid_signature")
    return ImportDecision("append", "extends_tip")


class P2PSyncService:
    """
    Sync artcb-devnet : propagation des blocs ``visibility=public`` seulement.
    Transport chiffré ML-KEM + AES-GCM entre pairs.
    """

    def __init__(
        self,
        *,
        chain: ChainManager,
        peers: PeerManager,
        identity: NodeIdentity,
        archive: PublicBlockArchive | None = None,
        symbol_sync: SymbolSyncService | None = None,
    ) -> None:
        self.chain = chain
        self.peers = peers
        self.identity = identity
        self.archive = archive or PublicBlockArchive(chain.blocks_path.parent.parent)
        self.symbol_sync = symbol_sync
        self.last_import_decisions: list[ImportDecision] = []

    def get_public_blocks(self, *, from_index: int = 0) -> list[dict[str, Any]]:
        blocks = self.chain.list_blocks(visibility="public")
        return [b for b in blocks if int(b.get("index", 0)) >= from_index]

    def import_public_blocks(
        self,
        blocks: list[dict[str, Any]],
        *,
        from_node_id: str = "unknown",
        extend_tip: bool = False,
    ) -> int:
        """Same decision for receive and pull. ``extend_tip`` is ignored (rapport 222)."""
        _ = extend_tip
        decisions: list[ImportDecision] = []
        to_archive: list[dict[str, Any]] = []
        extended = 0
        offered_at: dict[int, str] = {}
        ordered = sorted(blocks, key=lambda row: int(row.get("index") or 0) if str(row.get("index") or "").isdigit() or isinstance(row.get("index"), int) else 0)
        for block in ordered:
            local = self.chain._read_all_blocks()
            local_hashes = {str(row.get("hash") or "") for row in local}
            try:
                idx = int(block.get("index", -1))
            except (TypeError, ValueError):
                idx = -1
            existing = next((row for row in local if int(row.get("index", -1)) == idx), None) if idx >= 0 else None
            offered_hash = str(block.get("hash") or "")
            if idx >= 0 and idx in offered_at and offered_at[idx] and offered_hash and offered_at[idx] != offered_hash:
                decision = ImportDecision("reject", "equivocation")
            else:
                decision = decide_public_import(
                    block,
                    local_len=len(local),
                    local_tip=self.chain.last_hash(),
                    local_hashes=local_hashes,
                    structure_ok=self.verify_block_structure(block) if block.get("visibility") == "public" else False,
                    existing_at_index=existing,
                )
            decisions.append(decision)
            if decision.action == "reject":
                logger.warning("P2P import reject index=%s reason=%s", block.get("index"), decision.reason)
                if decision.reason in {"equivocation", "invalid_signature", "hash_mismatch"}:
                    try:
                        from src.artcb.consensus.byzantine_evidence import record_reject

                        record_reject(
                            self.chain.blocks_path,
                            reason=decision.reason,
                            block=block,
                            from_node_id=from_node_id,
                            hash_held=str((existing or {}).get("hash") or offered_at.get(idx) or ""),
                        )
                    except Exception:
                        logger.debug("byzantine evidence skip", exc_info=True)
                continue
            if decision.action == "duplicate":
                continue
            to_archive.append(block)
            if decision.action == "append":
                if idx >= 0 and offered_hash:
                    offered_at[idx] = offered_hash
                try:
                    if self.chain.import_extending_public_block(block):
                        extended += 1
                except Exception as exc:
                    logger.debug("public block did not extend local tip: %s", exc)
        stored = 0
        if self.archive and to_archive:
            stored = self.archive.store_blocks(to_archive, from_node_id=from_node_id)
        if self.symbol_sync and to_archive:
            self.symbol_sync.extract_from_blocks(to_archive, from_node_id=from_node_id)
        self.last_import_decisions = decisions
        return stored + extended

    @staticmethod
    def verify_block_structure(block: dict) -> bool:
        """Vérifie cohérence hash — signature = clé du nœud émetteur (pas vérifiable localement)."""
        try:
            eco = None
            version = int(block.get("hash_version") or HASH_VERSION_V1)
            if version >= HASH_VERSION_V2:
                eco = str(
                    block.get("economic_root")
                    or (block.get("economics") or {}).get("economic_root")
                    or ""
                )
            expected = ffi.build_block_hash(
                int(block["index"]),
                str(block["timestamp"]),
                str(block["prev_hash"]),
                str(block["graph_root"]),
                str(block.get("merkle_root") or block["graph_root"]),
                float(block["pol_score"]),
                economic_root=eco,
            )
        except (KeyError, TypeError, ValueError):
            return False
        return block.get("hash") == expected

    def build_encrypted_envelope(self, blocks: list[dict[str, Any]], peer: PeerRecord) -> dict[str, str]:
        payload = json.dumps({"blocks": blocks, "network_id": self.identity.network_id}, ensure_ascii=False).encode(
            "utf-8"
        )
        peer_pk = bytes.fromhex(peer.kem_public_key_hex)
        envelope = encrypt_payload(payload, peer_pk)
        envelope["from_node_id"] = self.identity.node_id
        envelope["from_kem_public_key_hex"] = self.identity.kem_public_key_hex
        return envelope

    def decrypt_envelope(self, envelope: dict[str, str]) -> dict[str, Any]:
        secret = bytes.fromhex(self.identity.kem_secret_key_hex)
        plaintext = decrypt_payload(envelope, secret)
        return json.loads(plaintext.decode("utf-8"))

    def push_to_peer(self, peer: PeerRecord, *, from_index: int = 0) -> dict[str, Any]:
        from src.artcb.p2p.flux import append_flux

        blocks = self.get_public_blocks(from_index=from_index)
        data_dir = Path(self.chain.blocks_path).parent.parent
        if not blocks:
            return {"peer_id": peer.peer_id, "pushed": 0, "message": "Aucun bloc public à envoyer"}
        chunk = 40
        imported_remote = 0
        last: dict[str, Any] = {}
        for offset in range(0, len(blocks), chunk):
            batch = blocks[offset : offset + chunk]
            t0 = time.perf_counter()
            try:
                envelope = self.build_encrypted_envelope(batch, peer)
            except (KEMError, ValueError, RuntimeError) as exc:
                logger.error("P2P push envelope to %s failed: %s", peer.peer_id, type(exc).__name__)
                self.peers.update_peer_status(peer.peer_id, last_sync_ok=False)
                append_flux(
                    data_dir,
                    {
                        "kind": "public_push",
                        "direction": "push",
                        "peer": peer.peer_id,
                        "host": peer.host,
                        "ok": False,
                        "error": f"push_encrypt_failed:{type(exc).__name__}",
                    },
                )
                raise P2PSyncError(f"push_encrypt_failed:{type(exc).__name__}") from exc
            encrypt_ms = round((time.perf_counter() - t0) * 1000, 2)
            url = f"{peer.base_url}/api/v1/p2p/blocks/receive"
            t_http = time.perf_counter()
            try:
                with httpx.Client(timeout=120.0) as client:
                    r = client.post(url, json={"envelope": envelope})
                    r.raise_for_status()
                    data = r.json()
                http_ms = round((time.perf_counter() - t_http) * 1000, 2)
                imported_remote += int(data.get("imported") or 0)
                last = data
                append_flux(
                    data_dir,
                    {
                        "kind": "public_push",
                        "direction": "push",
                        "peer": peer.peer_id,
                        "host": peer.host,
                        "chunk": f"{batch[0].get('index')}-{batch[-1].get('index')}",
                        "pushed": len(batch),
                        "imported": data.get("imported", 0),
                        "encrypt_ms": encrypt_ms,
                        "http_ms": http_ms,
                        "rtt_ms": round(encrypt_ms + http_ms, 2),
                        "ok": True,
                    },
                )
            except Exception as exc:
                logger.error("P2P push to %s failed: %s", peer.peer_id, exc)
                self.peers.update_peer_status(peer.peer_id, last_sync_ok=False)
                append_flux(
                    data_dir,
                    {
                        "kind": "public_push",
                        "direction": "push",
                        "peer": peer.peer_id,
                        "host": peer.host,
                        "ok": False,
                        "error": type(exc).__name__,
                    },
                )
                raise P2PSyncError(str(exc)) from exc
        self.peers.update_peer_status(peer.peer_id, last_sync_ok=True, blocks_received_delta=0)
        return {
            "peer_id": peer.peer_id,
            "pushed": len(blocks),
            "imported_remote": imported_remote,
            "encrypted": True,
            "kem": "ML-KEM-768",
            "last_remote": last,
        }

    def pull_from_peer(self, peer: PeerRecord, *, from_index: int = 0) -> dict[str, Any]:
        """Demande les blocs publics au pair.

        GO-B 2026-09-07 : envoie X-ARTCB-KEM-Public-Key + X-ARTCB-Node-Id.
        Si la réponse est chiffrée ({"envelope": ...}) → déchiffrement local.
        Si le pair est ancien (réponse en clair) → import direct (rétrocompat).
        from_node_id est lié à la clé KEM déclarée du pair, pas auto-déclaré.
        """
        from src.artcb.p2p.flux import append_flux

        url = f"{peer.base_url}/api/v1/p2p/blocks/public"
        headers = {
            "X-ARTCB-KEM-Public-Key": self.identity.kem_public_key_hex,
            "X-ARTCB-Node-Id": self.identity.node_id,
        }
        data_dir = Path(self.chain.blocks_path).parent.parent
        t0 = time.perf_counter()
        try:
            with httpx.Client(timeout=120.0) as client:
                r = client.get(url, params={"from_index": from_index}, headers=headers)
                r.raise_for_status()
                resp = r.json()
            http_ms = round((time.perf_counter() - t0) * 1000, 2)

            encrypted = resp.get("encrypted", False)
            if encrypted and "envelope" in resp:
                # GO-B : déchiffrement de la réponse pull
                try:
                    payload = self.decrypt_envelope(resp["envelope"])
                    blocks = payload.get("blocks", [])
                    # from_node_id lié à la clé KEM du pair (vérifiable)
                    from_node = resp["envelope"].get("from_node_id", peer.peer_id)
                    logger.info("P2P pull chiffré de %s : %d blocs", peer.peer_id, len(blocks))
                except Exception as exc:  # noqa: BLE001 — crypto errors vary (InvalidTag, KEMError, …)
                    logger.error("P2P pull decrypt from %s failed: %s", peer.peer_id, exc)
                    self.peers.update_peer_status(peer.peer_id, last_sync_ok=False)
                    raise P2PSyncError(f"pull_decrypt_failed:{type(exc).__name__}") from exc
            else:
                # Rétrocompatibilité : ancien pair sans chiffrement pull
                blocks = resp.get("blocks", [])
                from_node = peer.peer_id
                if blocks:
                    logger.debug("P2P pull en clair de %s (ancien pair) : %d blocs", peer.peer_id, len(blocks))

            imported = self.import_public_blocks(blocks, from_node_id=from_node)
            self.peers.update_peer_status(
                peer.peer_id,
                last_sync_ok=True,
                blocks_received_delta=imported,
            )
            append_flux(
                data_dir,
                {
                    "kind": "public_pull",
                    "direction": "pull",
                    "peer": peer.peer_id,
                    "host": peer.host,
                    "pushed": len(blocks),
                    "imported": imported,
                    "http_ms": http_ms,
                    "rtt_ms": http_ms,
                    "encrypted": encrypted,
                    "ok": True,
                },
            )
            return {
                "peer_id": peer.peer_id,
                "received": len(blocks),
                "imported": imported,
                "encrypted": encrypted,
                "http_ms": http_ms,
            }
        except P2PSyncError as exc:
            append_flux(
                data_dir,
                {
                    "kind": "public_pull",
                    "direction": "pull",
                    "peer": peer.peer_id,
                    "host": peer.host,
                    "ok": False,
                    "error": str(exc)[:200],
                },
            )
            raise
        except Exception as exc:
            logger.error("P2P pull from %s failed: %s", peer.peer_id, exc)
            self.peers.update_peer_status(peer.peer_id, last_sync_ok=False)
            append_flux(
                data_dir,
                {
                    "kind": "public_pull",
                    "direction": "pull",
                    "peer": peer.peer_id,
                    "host": peer.host,
                    "ok": False,
                    "error": type(exc).__name__,
                },
            )
            raise P2PSyncError(str(exc)) from exc

    def sync_all_peers(self, *, from_index: int = 0) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for peer in self.peers.list_peers():
            pulled: dict[str, Any] | None = None
            try:
                pulled = self.pull_from_peer(peer, from_index=from_index)
                pushed = self.push_to_peer(peer, from_index=from_index)
                results.append({"peer_id": peer.peer_id, "pull": pulled, "push": pushed, "ok": True})
            except P2PSyncError as exc:
                results.append(
                    {
                        "peer_id": peer.peer_id,
                        "ok": False,
                        "error": str(exc),
                        "pull": pulled,
                        "push_ok": False,
                    }
                )
            except Exception as exc:  # noqa: BLE001 — never turn a secondary path into HTTP 500
                logger.error("P2P sync peer %s unexpected: %s", peer.peer_id, type(exc).__name__)
                results.append(
                    {
                        "peer_id": peer.peer_id,
                        "ok": False,
                        "error": type(exc).__name__,
                        "pull": pulled,
                    }
                )
        return results
