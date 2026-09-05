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
from src.artcb.crypto.hybrid import sign_hybrid, verify_hybrid_and_or_window
from src.artcb.crypto.pqc import (
    PQC_SIG_ALGORITHM,
    generate_keypair,
    pack_keypair,
    pqc_enabled,
    unpack_keypair,
)
from src.artcb.economics.economic_root import (
    HASH_VERSION_V1,
    HASH_VERSION_V2,
    economic_root,
    mix_merkle_with_economic_root,
    native_economic_root_available,
)
from src.artcb.economics.emission import issued_reward_satoshi
from src.artcb.economics.settlement import MachineContribution, settle_block
from src.artcb.economics.workid import WorkIDError, WorkStatus
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
    hash_version: int = HASH_VERSION_V1

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
            "hash_version": self.hash_version,
        }
        if self.economics and self.economics.get("economic_root"):
            # Top-level BEFORE nested economics so C strstr hits the consensus field first.
            payload["economic_root"] = self.economics["economic_root"]
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
        self.human_registry = None
        self.machine_registry = None
        self.work_registry = None
        if enable_security:
            self.anti_sybil = AntiSybilValidator()
            self.slashing = SlashingManager()
            logger.info("Security modules enabled (Anti-Sybil + Slashing)")
        else:
            self.anti_sybil = None
            self.slashing = None
            logger.warning("Security modules DISABLED")

    def bind_identity(
        self,
        *,
        human_registry=None,
        machine_registry=None,
        work_registry=None,
    ) -> None:
        """Attach live identity registries so H_adult and WorkID are consensus-visible."""
        self.human_registry = human_registry
        self.machine_registry = machine_registry
        self.work_registry = work_registry
        logger.debug(
            "chain identity bound humans=%s machines=%s work=%s",
            human_registry is not None,
            machine_registry is not None,
            work_registry is not None,
        )

    def adult_verified_count(self) -> float:
        if self.human_registry is None:
            return 0.0
        count = float(self.human_registry.verified_adult_count())
        logger.debug("H_adult from HumanRegistry=%s", count)
        return count

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
        return verify_hybrid_and_or_window(
            message=message,
            signature_value=signature,
            ed25519_public_key=self._signing_key.verify_key.encode(),
            pqc_public_key=self._pqc_public_key,
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

    def public_state_digest(self) -> str:
        """SHA-256 of public block hashes in order — comparable across nodes after sync."""
        import hashlib

        hashes = [str(b.get("hash") or "") for b in self.list_blocks(visibility="public")]
        material = "|".join(hashes).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def import_extending_public_block(self, block: dict) -> bool:
        """Append a remote public block if it extends the local tip (PRE-DV-04).

        Hash structure is verified. The producer signature uses the remote
        chain key and is not checked against this node's key.
        """
        if block.get("visibility") != "public":
            return False
        existing = self._read_all_blocks()
        if any(str(row.get("hash") or "") == str(block.get("hash") or "") for row in existing):
            return False
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
        if block.get("hash") != expected:
            return False
        expected_index = len(self._read_all_blocks())
        if int(block.get("index", -1)) != expected_index:
            return False
        if str(block.get("prev_hash") or "") != self.last_hash():
            return False
        line = json.dumps(block, ensure_ascii=False, separators=(",", ":"))
        with self.blocks_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        logger.info("Imported extending public block index=%s hash=%s", block.get("index"), str(block.get("hash") or "")[:16])
        return True

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
        h_adult: float | None = None,
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

        humans = self._resolve_adult_h(verified_humans=verified_humans, h_adult=h_adult)

        if self.work_registry is not None and contributors:
            _assert_workids_unsettleable(self.work_registry, contributors)

        if block_reward is None:
            block_reward = self._calculate_block_reward(
                index,
                verified_humans=humans,
                actual_block_interval_seconds=self._last_observed_interval_seconds(),
            )

        final_contributors = []
        economics_payload: dict | None = None
        hash_version = HASH_VERSION_V1
        eco_root_for_hash: str | None = None
        if contributors:
            machine_contribs = _machine_contributions(contributors)
            if machine_contribs is not None:
                hbp_scores = {
                    str(c.get("bound_human_address") or c.get("owner_address") or c.get("address")): float(
                        c["hbp_score"]
                    )
                    for c in contributors
                    if c.get("hbp_score") is not None
                }
                provider_scores = {
                    str(c.get("owner_address") or c.get("address")): float(c["provider_score"])
                    for c in contributors
                    if c.get("provider_score") is not None and float(c.get("provider_score") or 0) > 0
                }
                settlement = settle_block(
                    r_block_satoshi=block_reward,
                    verified_humans=humans,
                    h_adult=humans,
                    machines=machine_contribs,
                    provider_scores=provider_scores or None,
                    hbp_scores=hbp_scores or None,
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
                eco = economic_root(settlement.economic_parts)
                economics_payload = {
                    "verified_humans": humans,
                    "h_adult": humans,
                    "hbp_rate": settlement.hbp_rate,
                    "work_pool_satoshi": settlement.work_pool_satoshi,
                    "hbp_pool_satoshi": settlement.hbp_pool_satoshi,
                    "provider_pool_satoshi": settlement.provider_pool_satoshi,
                    "worker_pool_satoshi": settlement.worker_pool_satoshi,
                    "economic_root": eco,
                    "pre_economic_merkle": merkle,
                }
                if native_economic_root_available():
                    hash_version = HASH_VERSION_V2
                    eco_root_for_hash = eco
                    logger.debug(
                        "native C EconomicRoot v2 index=%s root=%s",
                        index,
                        eco[:16],
                    )
                else:
                    merkle = mix_merkle_with_economic_root(merkle, eco)
                    economics_payload["hash_path"] = "python_merkle_mix_fallback"
                    logger.debug(
                        "C ABI v2 missing — Python merkle mix fallback index=%s",
                        index,
                    )
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
            index,
            timestamp,
            prev_hash,
            graph_root,
            merkle,
            pol_score,
            economic_root=eco_root_for_hash,
        )
        hash_sha3 = sha3_256_hex(block_hash)
        signature = self._sign_block(block_hash)

        if self.work_registry is not None and contributors:
            _mark_workids_settled(self.work_registry, contributors)

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
            hash_version=hash_version,
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
        actual_block_interval_seconds: float | None = None,
    ) -> int:
        """Reward issued = min(R(H)*dt/T, remaining 21M cap). Index does not cut R.

        The 210_000-block schedule and velocity extra_epochs were removed (D-024).
        Rapport 162: faster blocks scale the per-block amount, not the cap.
        """
        return issued_reward_satoshi(
            block_index,
            verified_humans=verified_humans,
            issued_so_far_satoshi=self._issued_so_far_satoshi(),
            actual_block_interval_seconds=actual_block_interval_seconds,
        )

    def _last_observed_interval_seconds(self) -> float | None:
        """Median inter-block time for emission scaling (rapport 162).

        Sub-second bursts (CPU test appends) are ignored so a lab loop cannot
        accidentally mint near-zero rewards; a real 10 s chain still scales.
        This floor is a measurement filter, not a 210k calendar.
        """
        from src.artcb.tokenomics import TARGET_BLOCK_SECONDS

        blocks = self._read_all_blocks()
        if len(blocks) < 2:
            return TARGET_BLOCK_SECONDS
        stamps: list[datetime] = []
        for block in blocks[-13:]:
            ts_raw = block.get("timestamp", "")
            try:
                stamps.append(datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")))
            except (ValueError, TypeError):
                continue
        if len(stamps) < 2:
            return TARGET_BLOCK_SECONDS
        stamps.sort()
        intervals = [
            (stamps[i] - stamps[i - 1]).total_seconds()
            for i in range(1, len(stamps))
            if (stamps[i] - stamps[i - 1]).total_seconds() >= 1.0
        ]
        if not intervals:
            return TARGET_BLOCK_SECONDS
        intervals.sort()
        return intervals[len(intervals) // 2]

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

    def _resolve_adult_h(
        self,
        *,
        verified_humans: float | None,
        h_adult: float | None,
    ) -> float:
        if h_adult is not None:
            logger.debug("H_adult explicit=%s", h_adult)
            return float(h_adult)
        if verified_humans is not None:
            logger.debug("H from verified_humans override=%s", verified_humans)
            return float(verified_humans)
        return self.adult_verified_count()

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
        if block.get("hash") != expected:
            return False
        return self.verify_block_signature(str(block["hash"]), str(block.get("signature", "")))


def _machine_contributions(contributors: list[dict]) -> list[MachineContribution] | None:
    """Return machine contributions when worker rows carry machine fields.

    Job-provider rows (role=provider) are ignored here; their scores are
    collected separately. Mixed/legacy lists without machine fields keep
    the historic PoL split.
    """
    if not contributors:
        return None
    machine_rows = [c for c in contributors if c.get("role") != "provider"]
    if not machine_rows:
        return None
    if not all("machine_index" in c and "owner_address" in c for c in machine_rows):
        return None
    result: list[MachineContribution] = []
    for contributor in machine_rows:
        n_econ = contributor.get("n_economic")
        result.append(
            MachineContribution(
                machine_id=str(
                    contributor.get("machine_id")
                    or f"{contributor['owner_address']}:{contributor['machine_index']}"
                ),
                owner_address=str(contributor["owner_address"]),
                machine_index=int(contributor["machine_index"]),
                bound_human_address=contributor.get("bound_human_address"),
                work_weight=float(contributor.get("work_weight", contributor.get("pol_score", 0.0))),
                n_economic=int(n_econ) if n_econ is not None else None,
                is_first_machine=contributor.get("is_first_machine"),
                provider_score=float(contributor.get("provider_score", 0.0) or 0.0),
                hbp_contribution=float(
                    contributor.get("hbp_contribution", contributor.get("hbp_score", 1.0)) or 1.0
                ),
            )
        )
    return result


def _assert_workids_unsettleable(work_registry, contributors: list[dict]) -> None:
    for contributor in contributors:
        work_id = contributor.get("work_id")
        if not work_id:
            continue
        rec = work_registry.get(str(work_id))
        if rec is None:
            continue
        if rec.status == WorkStatus.SETTLED.value or rec.settlement_count >= 1:
            raise WorkIDError(f"REJECT_DOUBLE_SETTLEMENT: {work_id}")


def _mark_workids_settled(work_registry, contributors: list[dict]) -> None:
    seen: set[str] = set()
    for contributor in contributors:
        work_id = contributor.get("work_id")
        if not work_id or work_id in seen:
            continue
        seen.add(str(work_id))
        rec = work_registry.get(str(work_id))
        if rec is None:
            work_registry.create(
                work_id=str(work_id),
                job_id=str(contributor.get("job_id") or "mining"),
            )
        work_registry.transition(str(work_id), WorkStatus.SETTLED)
