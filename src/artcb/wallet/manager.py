"""Wallet manager — key storage, balance tracking, transaction history."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

from nacl import encoding, signing

from src.artcb.config import load_settings
from src.artcb.crypto.hybrid import sign_hybrid
from src.artcb.crypto.pqc import (
    PQC_SIG_ALGORITHM,
    generate_keypair,
    pack_keypair,
    pqc_enabled,
    unpack_keypair,
)
from src.artcb.wallet.address import (
    address_from_signing_key,
    generate_test_address,
    generate_test_hybrid_address_v2,
    hybrid_address_v2,
)
from src.artcb.wallet.encryption import (
    decrypt_private_key,
    decrypt_secret_blob,
    encrypt_legacy_key_file,
    encrypt_private_key,
    encrypt_secret_blob,
    is_encrypted_key_blob,
    is_plain_ed25519_seed,
)

logger = logging.getLogger("artcb.wallet.manager")


@dataclass
class Wallet:
    """ARTCB wallet with Ed25519 keypair and optional ML-DSA hybrid keys."""

    address: str
    signing_key: signing.SigningKey
    public_key_hex: str
    pqc_secret_key: bytes | None = None
    pqc_public_key: bytes | None = None
    address_v2: str | None = None

    @property
    def public_key_b64(self) -> str:
        return self.signing_key.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii")

    @property
    def pqc_public_key_hex(self) -> str | None:
        return self.pqc_public_key.hex() if self.pqc_public_key else None

    @property
    def is_hybrid(self) -> bool:
        return self.pqc_secret_key is not None and self.pqc_public_key is not None

    def sign(self, message: bytes) -> str:
        """Sign message — hybrid Ed25519+ML-DSA when PQC keys present, else Ed25519 hex."""
        if self.is_hybrid and self.pqc_secret_key is not None:
            return sign_hybrid(
                ed25519_key=self.signing_key,
                pqc_secret_key=self.pqc_secret_key,
                message=message,
            )
        signed = self.signing_key.sign(message)
        return signed.signature.hex()

    def to_dict(self) -> dict:
        payload = {
            "address": self.address,
            "public_key_hex": self.public_key_hex,
            "public_key_b64": self.public_key_b64,
            "hybrid": self.is_hybrid,
        }
        if self.address_v2:
            payload["address_v2"] = self.address_v2
        if self.pqc_public_key_hex:
            payload["pqc_public_key_hex"] = self.pqc_public_key_hex
        return payload


class WalletManager:
    """Manages ARTCB wallets — creation, loading, balance tracking."""

    def __init__(self, wallet_dir: Path | None = None) -> None:
        settings = load_settings()
        self.wallet_dir = wallet_dir or (settings.data_dir / "wallets")
        self.wallet_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("WalletManager initialized wallet_dir=%s", self.wallet_dir)

    def _pqc_key_path(self, name: str) -> Path:
        return self.wallet_dir / f"{name}.pqc"

    def _load_pqc_keys(self, name: str) -> tuple[bytes, bytes] | None:
        pqc_path = self._pqc_key_path(name)
        if not pqc_path.is_file():
            return None
        raw = pqc_path.read_bytes()
        packed = decrypt_secret_blob(raw) if is_encrypted_key_blob(raw) else raw
        try:
            secret, public = unpack_keypair(packed)
        except Exception as exc:
            logger.warning("Invalid PQC key file for wallet %s: %s", name, exc)
            return None
        return secret, public

    def _save_pqc_keys(self, name: str, secret_key: bytes, public_key: bytes) -> bytes:
        pqc_path = self._pqc_key_path(name)
        pqc_path.write_bytes(encrypt_secret_blob(pack_keypair(secret_key, public_key)))
        pqc_path.chmod(0o600)
        return public_key

    def create_wallet(
        self,
        *,
        name: str = "default",
        user_password: str | None = None,
        wallet_namespace: str = "MAINNET",
    ) -> Wallet:
        """Create new wallet with Ed25519 keypair and optional ML-DSA hybrid keys.

        wallet_namespace : "MAINNET" (default) or "TEST".
          - "MAINNET" → legacy address_from_signing_key() → artcb1…
          - "TEST"    → generate_test_address() → artcbdev1… (domain-separated hash)
          Namespace is ALWAYS determined by this explicit parameter (rapport 354 §9,
          rapport 358 audit §5) — never inferred from the wallet name.

        Si user_password est fourni, la seed est chiffrée avec ce mot de passe utilisateur.
        Le login via /auth/login utilise ce même mot de passe pour déchiffrer.
        Sans user_password, seule la ARTCB_WALLET_PASSPHRASE serveur est utilisée (mode dev).
        """
        key_path = self.wallet_dir / f"{name}.key"
        if key_path.exists():
            raise FileExistsError(f"Wallet {name} already exists at {key_path}")

        ns = wallet_namespace.upper().strip()
        if ns not in ("MAINNET", "TEST"):
            raise ValueError(f"wallet_namespace must be 'MAINNET' or 'TEST', got '{wallet_namespace}'")

        signing_key = signing.SigningKey.generate()
        pubkey_bytes = signing_key.verify_key.encode()

        # Domain-separated address derivation (rapport 354 §14, rapport 355 §4)
        if ns == "TEST":
            address = generate_test_address(pubkey_bytes)  # artcbdev1…
        else:
            address = address_from_signing_key(signing_key)  # artcb1… (legacy path, unchanged)

        seed = signing_key.encode()
        # PROTOCOLE : chiffrer avec le mot de passe de l'utilisateur si fourni,
        # sinon fallback sur la passphrase serveur (mode dev uniquement).
        key_path.write_bytes(encrypt_private_key(seed, passphrase=user_password or None))
        key_path.chmod(0o600)

        pqc_secret: bytes | None = None
        pqc_public: bytes | None = None
        address_v2: str | None = None
        if pqc_enabled():
            try:
                pqc_secret, pqc_public = generate_keypair()
                pqc_public = self._save_pqc_keys(name, pqc_secret, pqc_public)
                # V-PQC-2: domain-separated hybrid address
                # TEST  → generate_test_hybrid_address_v2() → artcb2t…
                # MAINNET → legacy hybrid_address_v2() → artcb2…  (backward compat)
                if ns == "TEST":
                    address_v2 = generate_test_hybrid_address_v2(
                        signing_key.verify_key.encode(), pqc_public
                    )
                else:
                    address_v2 = hybrid_address_v2(signing_key.verify_key.encode(), pqc_public)
                logger.info(
                    "Created hybrid wallet PQC=%s address_v2=%s namespace=%s",
                    PQC_SIG_ALGORITHM, address_v2[:16], ns,
                )
            except Exception as exc:
                logger.warning("PQC key generation skipped: %s", exc)

        from datetime import datetime

        meta_path = self.wallet_dir / f"{name}.json"
        # P1-3 FIX: stocker le champ "name" dans le JSON metadata du wallet
        # Avant : name absent du JSON → list_wallets() utilisait meta_path.stem (nom de fichier)
        # Après : name explicitement dans le JSON pour robustesse + lisibilité
        metadata: dict = {
            "name": name,
            "address": address,
            "public_key_hex": signing_key.verify_key.encode().hex(),
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "key_encryption": "AES-256-GCM",
            "key_format": "ARTCBENC1",
            "hybrid": pqc_public is not None,
            "wallet_namespace": ns,
            "domain": ns,
        }
        if pqc_public is not None:
            metadata["pqc_algorithm"] = PQC_SIG_ALGORITHM
            metadata["pqc_public_key_hex"] = pqc_public.hex()
            metadata["address_v2"] = address_v2
            metadata["signature_algorithm"] = f"Ed25519+{PQC_SIG_ALGORITHM}"
        meta_path.write_text(json.dumps(metadata, indent=2))

        logger.info(
            "Created wallet name=%s address=%s namespace=%s hybrid=%s",
            name, address, ns, pqc_public is not None,
        )

        return Wallet(
            address=address,
            signing_key=signing_key,
            public_key_hex=metadata["public_key_hex"],
            pqc_secret_key=pqc_secret,
            pqc_public_key=pqc_public,
            address_v2=address_v2,
        )

    def load_wallet(self, *, name: str = "default", user_password: str | None = None) -> Wallet:
        """Load existing wallet.

        user_password : mot de passe utilisateur utilisé pour chiffrer la seed à la création.
        Obligatoire pour les wallets créés via /wallet/create {password}.

        V-PQC-2 fix (rapport 362): wallet_namespace is read from the .json metadata so that
        address_v2 is recomputed with the correct domain:
          - TEST    → generate_test_hybrid_address_v2() → artcb2t…
          - MAINNET → hybrid_address_v2() legacy          → artcb2…  (backward compat)
        Prevents create/load address_v2 mismatch identified by ChatGPT audit.
        """
        key_path = self.wallet_dir / f"{name}.key"
        if not key_path.exists():
            raise FileNotFoundError(f"Wallet {name} not found at {key_path}")

        raw = key_path.read_bytes()
        seed = decrypt_private_key(raw, passphrase=user_password)
        signing_key = signing.SigningKey(seed)

        if is_plain_ed25519_seed(raw):
            encrypt_legacy_key_file(key_path)
            meta_path = self.wallet_dir / f"{name}.json"
            if meta_path.is_file():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["key_encryption"] = "AES-256-GCM"
                meta["key_format"] = "ARTCBENC1"
                meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Read wallet_namespace from .json metadata (V-PQC-2 fix)
        meta_path = self.wallet_dir / f"{name}.json"
        stored_ns = "MAINNET"
        if meta_path.is_file():
            try:
                meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
                stored_ns = meta_data.get("wallet_namespace", "MAINNET").upper().strip()
            except (json.JSONDecodeError, OSError):
                stored_ns = "MAINNET"

        pqc_secret: bytes | None = None
        pqc_public: bytes | None = None
        address_v2: str | None = None
        pqc_loaded = self._load_pqc_keys(name)
        if pqc_loaded:
            pqc_secret, pqc_public = pqc_loaded
            # V-PQC-2: recalculate address_v2 using the stored namespace
            # TEST    → artcb2t… (domain-separated)
            # MAINNET → artcb2…  (legacy, backward compat)
            if stored_ns == "TEST":
                address_v2 = generate_test_hybrid_address_v2(
                    signing_key.verify_key.encode(), pqc_public
                )
            else:
                address_v2 = hybrid_address_v2(signing_key.verify_key.encode(), pqc_public)

        # Ed25519 address: also domain-aware for TEST wallets
        if stored_ns == "TEST":
            address = generate_test_address(signing_key.verify_key.encode())  # artcbdev1…
        else:
            address = address_from_signing_key(signing_key)  # artcb1… legacy

        logger.debug(
            "Loaded wallet name=%s address=%s hybrid=%s namespace=%s",
            name, address, pqc_public is not None, stored_ns,
        )

        return Wallet(
            address=address,
            signing_key=signing_key,
            public_key_hex=signing_key.verify_key.encode().hex(),
            pqc_secret_key=pqc_secret,
            pqc_public_key=pqc_public,
            address_v2=address_v2,
        )

    def list_wallets(self) -> list[dict]:
        """List all wallets with metadata.

        Retourne aussi has_key_file=True/False pour indiquer si la clé privée
        est présente sur CE serveur. Un wallet sans clé privée (has_key_file=False)
        est une adresse importée en lecture seule — ne peut PAS signer ni recevoir
        de rewards validés.
        """
        wallets = []
        for meta_path in self.wallet_dir.glob("*.json"):
            try:
                metadata = json.loads(meta_path.read_text())
                metadata["name"] = meta_path.stem
                # Indiquer si la clé privée (.key) est présente sur CE serveur
                # has_key_file=True  → wallet local, peut signer, authentifié
                # has_key_file=False → adresse importée, lecture seule uniquement
                key_path = self.wallet_dir / f"{meta_path.stem}.key"
                metadata["has_key_file"] = key_path.is_file()
                wallets.append(metadata)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load wallet metadata path=%s error=%s", meta_path, exc)
        return wallets

    def get_balance(self, address: str, blocks_path: Path) -> dict:
        """Calculate balance from blockchain."""
        if not blocks_path.exists():
            return {
                "address": address,
                "balance_satoshi": 0,
                "balance_artcb": 0.0,
                "block_count": 0,
                "rewards": [],
            }

        total_satoshi = 0
        rewards = []

        with blocks_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue

                block = json.loads(line)
                contributors = block.get("contributors", [])

                for contributor in contributors:
                    if contributor.get("address") == address:
                        reward_satoshi = contributor.get("reward_satoshi", 0)
                        total_satoshi += reward_satoshi
                        rewards.append({
                            "block_index": block["index"],
                            "reward_satoshi": reward_satoshi,
                            "pol_score": contributor.get("pol_score", 0.0),
                        })

        return {
            "address": address,
            "balance_satoshi": total_satoshi,
            "balance_artcb": total_satoshi / 1e8,
            "block_count": len(rewards),
            "rewards": rewards,
            "faucet_satoshi": 0,
            "faucet_artcb": 0.0,
        }

    def get_balance_with_faucet(self, address: str, blocks_path: Path, faucet_ledger: Path | None = None) -> dict:
        """Balance chaine PoL + credits faucet devnet."""
        base = self.get_balance(address, blocks_path)
        faucet_satoshi = 0
        if faucet_ledger and faucet_ledger.is_file():
            for line in faucet_ledger.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("address") == address:
                    faucet_satoshi += int(entry.get("amount_satoshi", 0))
        total = base["balance_satoshi"] + faucet_satoshi
        base["faucet_satoshi"] = faucet_satoshi
        base["faucet_artcb"] = faucet_satoshi / 1e8
        base["balance_satoshi"] = total
        base["balance_artcb"] = total / 1e8
        return base
