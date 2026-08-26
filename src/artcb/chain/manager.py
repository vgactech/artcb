"""Blockchain manager — persistence + hybrid signatures + SHA-3 audit hash."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from nacl import encoding, signing

from src.artcb.chain import ffi
from src.artcb.config import load_settings
from src.artcb.crypto.hashing import sha3_256_hex
from src.artcb.crypto.hybrid import sign_hybrid, verify_hybrid
from src.artcb.crypto.pqc import (
    PQC_SIG_ALGORITHM,
    generate_keypair,
    pack_keypair,
    pqc_enabled,
    unpack_keypair,
)
from src.artcb.economics.emission import issued_reward_satoshi
from src.artcb.economics.settlement import MachineContribution, settle_block
from src.artcb.security.anti_sybil import AntiSybilValidator
from src.artcb.security.slashing import SlashingManager
from src.artcb.wallet.encryption import (
    decrypt_private_key,
    decrypt_secret_blob,
    encrypt_private_key,
    encrypt_secret_blob,
    is_encrypted_key_blob,
    is_plain_ed25519_seed,
)

logger = logging.getLogger("artcb.chain.manager")


@dataclass
class ChainBlock:
    index: int
    timestamp: str
    prev_hash: str
    graph_root: str
    merkle_root: str
    pol_score: float
    hash: str
    signature: str
    graph_id: str
    visibility: str = "private"
    group_id: str | None = None
    block_reward: int = 0
    contributors: list[dict] = field(default_factory=list)
    public_symbols: dict[str, str] = field(default_factory=dict)
    hash_sha3: str | None = None
    economics: dict | None = None

    def to_json_line(self) -> str:
        payload = {
            "index": self.index,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "graph_root": self.graph_root,
            "merkle_root": self.merkle_root,
            "pol_score": self.pol_score,
            "hash": self.hash,
            "signature": self.signature,
            "graph_id": self.graph_id,
            "visibility": self.visibility,
            "group_id": self.group_id,
            "block_reward": self.block_reward,
            "contributors": self.contributors,
        }
        if self.economics:
            payload["economics"] = self.economics
        if self.public_symbols:
            payload["public_symbols"] = self.public_symbols
        if self.hash_sha3:
            payload["hash_sha3"] = self.hash_sha3
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        # Stocker la taille réelle du bloc (en octets UTF-8) dans le payload lui-même
        # Utile pour les analyses tokenomics et l'audit de la chaîne
        payload["block_size_bytes"] = len(line.encode("utf-8"))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


GENESIS_PREV_HASH = "0" * 64


class ChainManager:
    def __init__(
        self,
        blocks_path: Path,
        key_path: Path | None = None,
        enable_security: bool = True,
    ) -> None:
        settings = load_settings()
        self.blocks_path = blocks_path
        self.blocks_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path = key_path or (settings.data_dir / "chain.key")
        self._pqc_key_path = self.key_path.with_suffix(".pqc")
        self._signing_key, self._pqc_secret_key, self._pqc_public_key = self._load_or_create_keys()

        self.enable_security = enable_security
        if enable_security:
            self.anti_sybil = AntiSybilValidator()
            self.slashing = SlashingManager()
            logger.info("Security modules enabled (Anti-Sybil + Slashing)")
        else:
            self.anti_sybil = None
            self.slashing = None
            logger.warning("Security modules DISABLED")

    def _load_or_create_keys(self) -> tuple[signing.SigningKey, bytes | None, bytes | None]:
        if self.key_path.exists():
            raw = self.key_path.read_bytes()
            if is_encrypted_key_blob(raw):
                seed = decrypt_private_key(raw)
            elif is_plain_ed25519_seed(raw):
                seed = raw
            else:
                seed = raw[:32]
            signing_key = signing.SigningKey(seed)
        else:
            signing_key = signing.SigningKey.generate()
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            if pqc_enabled():
                try:
                    self.key_path.write_bytes(encrypt_private_key(signing_key.encode()))
                except Exception:
                    self.key_path.write_bytes(signing_key.encode())
            else:
                self.key_path.write_bytes(signing_key.encode())
            logger.debug("Generated new Ed25519 chain key path=%s", self.key_path)

        pqc_secret: bytes | None = None
        pqc_public: bytes | None = None
        if self._pqc_key_path.is_file():
            raw_pqc = self._pqc_key_path.read_bytes()
            try:
                packed = decrypt_secret_blob(raw_pqc) if is_encrypted_key_blob(raw_pqc) else raw_pqc
                pqc_secret, pqc_public = unpack_keypair(packed)
            except Exception as exc:
                logger.warning("Chain PQC key invalid or undecryptable, regenerating: %s", exc)
                pqc_secret = None
        if pqc_secret is None and pqc_enabled():
            try:
                pqc_secret, pqc_public = generate_keypair()
                self._pqc_key_path.write_bytes(encrypt_secret_blob(pack_keypair(pqc_secret, pqc_public)))
                logger.info("Generated chain hybrid key %s", PQC_SIG_ALGORITHM)
            except Exception as exc:
                logger.warning("Chain PQC key generation skipped: %s", exc)

        return signing_key, pqc_secret, pqc_public

    @property
    def public_key_b64(self) -> str:
        return self._signing_key.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii")

    @property
    def is_hybrid(self) -> bool:
        return self._pqc_secret_key is not None and self._pqc_public_key is not None

    def _sign_block(self, block_hash: str) -> str:
        message = block_hash.encode("utf-8")
        if self.is_hybrid and self._pqc_secret_key is not None:
            return sign_hybrid(
                ed25519_key=self._signing_key,
                pqc_secret_key=self._pqc_secret_key,
                message=message,
            )
        signed = self._signing_key.sign(message)
        return f"ed25519:{signed.signature.hex()}"

    def verify_block_signature(self, block_hash: str, signature: str) -> bool:
        message = block_hash.encode("utf-8")
        return verify_hybrid(
            message=message,
            signature_value=signature,
            ed25519_public_key=self._signing_key.verify_key.encode(),
            pqc_public_key=self._pqc_public_key or b"",
        )

    def list_blocks(
        self,
        *,
        visibility: str | None = None,
        group_id: str | None = None,
    ) -> list[dict]:
        blocks = self._read_all_blocks()
        if visibility:
            blocks = [b for b in blocks if b.get("visibility") == visibility]
        if group_id:
            blocks = [b for b in blocks if b.get("group_id") == group_id]
        return blocks

    def _read_all_blocks(self) -> list[dict]:
        if not self.blocks_path.exists():
            return []
        blocks: list[dict] = []
        with self.blocks_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    blocks.append(json.loads(line))
        return blocks

    def list_blocks_legacy(self) -> list[dict]:
        return self._read_all_blocks()

    def last_hash(self) -> str:
        blocks = self._read_all_blocks()
        if not blocks:
            return GENESIS_PREV_HASH
        return blocks[-1]["hash"]

    def append_block(
        self,
        *,
        graph_id: str,
        graph_root: str,
        pol_score: float,
        merkle_root: str | None = None,
        visibility: str = "private",
        group_id: str | None = None,
        contributors: list[dict] | None = None,
        block_reward: int | None = None,
        public_symbols: dict[str, str] | None = None,
        source: str = "unknown",  # "ai_memo" | "ai_think" | "mining" — pour bypass AI
        verified_humans: float | None = None,
    ) -> ChainBlock:
        all_blocks = self._read_all_blocks()
        index = len(all_blocks)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        prev_hash = self.last_hash()
        merkle = merkle_root or graph_root

        if self.enable_security and self.anti_sybil and contributors:
            valid, reason = self.anti_sybil.validate_block(contributors, pol_score, index, source=source)
            if not valid:
                logger.error("Block %d rejected by Anti-Sybil: %s", index, reason)
                # Slashing uniquement si ce n'est pas un bloc IA bypassé
                is_ai = source.startswith("ai:")
                bypass_active = (self.anti_sybil.ai_bypass and is_ai) or self.anti_sybil.study_mode
                if self.slashing and not bypass_active:
                    for contributor in contributors:
                        self.slashing.slash(
                            address=contributor["address"],
                            reason=reason or "Anti-Sybil validation failed",
                            severity="minor",
                            reward_satoshi=0,
                            block_index=index,
                        )
                raise ValueError(f"Block rejected: {reason}")

            if self.slashing:
                for contributor in contributors:
                    allowed, reason = self.slashing.is_allowed(contributor["address"])
                    if not allowed:
                        logger.error("Contributor %s... not allowed: %s", contributor["address"][:12], reason)
                        raise ValueError(f"Contributor blocked: {reason}")

        if block_reward is None:
            block_reward = self._calculate_block_reward(
                index,
                verified_humans=verified_humans if verified_humans is not None else 0.0,
            )

        final_contributors = []
        economics_payload: dict | None = None
        if contributors:
            machine_contribs = _machine_contributions(contributors)
            if machine_contribs is not None:
                humans = verified_humans if verified_humans is not None else 0.0
                settlement = settle_block(
                    r_block_satoshi=block_reward,
                    verified_humans=humans,
                    machines=machine_contribs,
                )
                pol_by_address = {
                    c["address"]: c.get("pol_score", 0.0) for c in contributors
                }
                sig_by_address = {
                    c["address"]: c.get("signature", "") for c in contributors
                }
                merged: dict[str, dict] = {}
                for line in settlement.lines:
                    entry = merged.setdefault(
                        line.address,
                        {
                            "address": line.address,
                            "pol_score": pol_by_address.get(line.address, 0.0),
                            "reward_satoshi": 0,
                            "signature": sig_by_address.get(line.address, ""),
                            "role": line.role,
                            "legs": [],
                        },
                    )
                    entry["reward_satoshi"] += line.reward_satoshi
                    entry["legs"].append({
                        "role": line.role,
                        "machine_id": line.machine_id,
                        "reward_satoshi": line.reward_satoshi,
                    })
                final_contributors = list(merged.values())
                economics_payload = {
                    "verified_humans": humans,
                    "hbp_rate": settlement.hbp_rate,
                    "work_pool_satoshi": settlement.work_pool_satoshi,
                    "hbp_pool_satoshi": settlement.hbp_pool_satoshi,
                }
            else:
                from src.artcb.economics.satoshi import allocate_satoshi

                contributor_scores = {c["address"]: float(c["pol_score"]) for c in contributors}
                allocated = allocate_satoshi(contributor_scores, block_reward)
                for contributor in contributors:
                    address = contributor["address"]
                    final_contributors.append({
                        "address": address,
                        "pol_score": contributor["pol_score"],
                        "reward_satoshi": allocated.get(address, 0),
                        "signature": contributor.get("signature", ""),
                        "role": contributor.get("role", "contributor"),
                    })

        block_hash = ffi.build_block_hash(
            index, timestamp, prev_hash, graph_root, merkle, pol_score
        )
        hash_sha3 = sha3_256_hex(block_hash)
        signature = self._sign_block(block_hash)

        block = ChainBlock(
            index=index,
            timestamp=timestamp,
            prev_hash=prev_hash,
            graph_root=graph_root,
            merkle_root=merkle,
            pol_score=pol_score,
            hash=block_hash,
            hash_sha3=hash_sha3,
            signature=signature,
            graph_id=graph_id,
            visibility=visibility,
            group_id=group_id,
            block_reward=block_reward,
            contributors=final_contributors,
            public_symbols=dict(public_symbols) if public_symbols else {},
            economics=economics_payload,
        )
        with self.blocks_path.open("a", encoding="utf-8") as handle:
            handle.write(block.to_json_line() + "\n")

        if self.enable_security and self.anti_sybil and contributors:
            self.anti_sybil.record_valid_block(contributors, pol_score, index)

        logger.debug(
            "Appended block index=%d hash=%s sha3=%s reward=%d contributors=%d hybrid=%s",
            index, block_hash, hash_sha3[:16], block_reward, len(final_contributors), self.is_hybrid,
        )
        return block

    def _issued_so_far_satoshi(self) -> int:
        return sum(int(b.get("block_reward", 0) or 0) for b in self._read_all_blocks())

    def _calculate_block_reward(
        self,
        block_index: int,
        *,
        verified_humans: float = 0.0,
    ) -> int:
        """Reward issued = min(R(H), remaining 21M cap). Index does not cut R.

        The 210_000-block schedule and velocity extra_epochs were removed (D-024).
        """
        return issued_reward_satoshi(
            block_index,
            verified_humans=verified_humans,
            issued_so_far_satoshi=self._issued_so_far_satoshi(),
        )

    def _compute_dynamic_epoch(self, velocity_ref: int, window_sec: int) -> int:
        """REMOVED from emission (D-024). Kept as a velocity *metric* only.

        Always returns 0 so leftover dashboard callers cannot re-halve R_block.
        Use ``_observe_velocity_per_day`` if a UI needs blocs/jour.
        """
        logger.debug(
            "dynamic epoch unused for reward velocity_ref=%s window_sec=%s",
            velocity_ref,
            window_sec,
        )
        return 0

    def _observe_velocity_per_day(self, window_sec: int = 86_400) -> float:
        """Blocs/jour observés sur la fenêtre — métrique, pas un halving."""
        from datetime import UTC, datetime, timedelta

        try:
            all_blocks = self._read_all_blocks()
            if len(all_blocks) < 2:
                return 0.0
            cutoff = datetime.now(UTC) - timedelta(seconds=window_sec)
            count_recent = 0
            for b in all_blocks:
                ts_raw = b.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    if ts >= cutoff:
                        count_recent += 1
                except (ValueError, AttributeError):
                    pass
            return count_recent * (86_400 / window_sec)
        except Exception:
            return 0.0

    def verify(self) -> dict:
        try:
            valid, message = ffi.verify_chain_file(self.blocks_path)
        except FileNotFoundError as exc:
            return {"valid": False, "message": str(exc), "block_count": 0}
        return {
            "valid": valid,
            "message": message,
            "block_count": len(self._read_all_blocks()),
            "public_key": self.public_key_b64,
            "hybrid_signatures": self.is_hybrid,
            "pqc_algorithm": PQC_SIG_ALGORITHM if self.is_hybrid else None,
        }

    def verify_block_dict(self, block: dict) -> bool:
        """Vérifie hash d'un bloc public local."""
        if block.get("visibility") != "public":
            return False
        try:
            expected = ffi.build_block_hash(
                int(block["index"]),
                str(block["timestamp"]),
                str(block["prev_hash"]),
                str(block["graph_root"]),
                str(block.get("merkle_root") or block["graph_root"]),
                float(block["pol_score"]),
            )
        except (KeyError, TypeError, ValueError):
            return False
        if block.get("hash") != expected:
            return False
        return self.verify_block_signature(str(block["hash"]), str(block.get("signature", "")))


def _machine_contributions(contributors: list[dict]) -> list[MachineContribution] | None:
    """Return machine contributions when every contributor carries machine fields.

    Mixed/legacy contributor lists keep the historic PoL split (100% of R_block).
    """
    if not contributors:
        return None
    if not all("machine_index" in c and "owner_address" in c for c in contributors):
        return None
    result: list[MachineContribution] = []
    for contributor in contributors:
        result.append(
            MachineContribution(
                machine_id=str(
                    contributor.get("machine_id")
                    or f"{contributor['owner_address']}:{contributor['machine_index']}"
                ),
                owner_address=str(contributor["owner_address"]),
                machine_index=int(contributor["machine_index"]),
                bound_human_address=contributor.get("bound_human_address"),
                work_weight=float(contributor.get("pol_score", contributor.get("work_weight", 0.0))),
            )
        )
    return result
