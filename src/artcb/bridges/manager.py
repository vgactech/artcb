"""Bridge manager ARTCB — orchestration des ponts vers blockchains externes.

Zéro dépendance native : utilise uniquement urllib + json (stdlib Python).
Pour Ethereum/BNB/Polygon/Avalanche : JSON-RPC via HTTP.
Pour Bitcoin : mempool.space API REST.
Pour Solana : Solana JSON-RPC.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("artcb.bridges.manager")

# RPC defaults — endpoints publics gratuits, aucune clé requise
_ETH_RPC = os.getenv("ETHEREUM_RPC_URL", "https://cloudflare-eth.com")
_BSC_RPC = os.getenv("BNB_RPC_URL", "https://bsc-dataseed.binance.org")
_POLYGON_RPC = os.getenv("POLYGON_RPC_URL", "https://polygon-bor-rpc.publicnode.com")
_AVAX_RPC = os.getenv("AVALANCHE_RPC_URL", "https://api.avax.network/ext/bc/C/rpc")
_SOL_RPC = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
_BTC_API = os.getenv("BITCOIN_API_URL", "https://mempool.space/api")

SUPPORTED_CHAINS = ["ethereum", "bitcoin", "solana", "bnb", "polygon", "avalanche"]


class BridgeError(Exception):
    """Erreur lors de l'import d'une transaction externe."""


@dataclass
class BridgeResult:
    """Résultat d'un import de transaction externe."""
    chain: str
    tx_hash: str
    block_number: int | None
    from_address: str
    to_address: str
    value: str
    timestamp: str
    raw_data: dict[str, Any]
    ir_text: str = field(default="")  # texte encodé en IR PoL

    def to_ir_text(self) -> str:
        """Génère le texte à graver en IR PoL."""
        ts = self.timestamp or datetime.now(UTC).isoformat()
        value_str = f"{self.value}" if self.value else "valeur inconnue"
        return (
            f"Transaction {self.chain.upper()} importée dans ARTCB. "
            f"De {self.from_address[:20]}… "
            f"vers {self.to_address[:20]}… "
            f"Montant : {value_str}. "
            f"Bloc : {self.block_number}. "
            f"Hash : {self.tx_hash[:32]}…. "
            f"Horodatage : {ts}."
        )


class BridgeManager:
    """Gestionnaire des bridges vers les blockchains externes."""

    _status_ttl_s = 20.0

    def __init__(self) -> None:
        self._status_cache: tuple[float, list[dict[str, Any]]] | None = None

    # ------------------------------------------------------------------
    # Méthode principale
    # ------------------------------------------------------------------

    def import_transaction(self, *, chain: str, tx_hash: str) -> BridgeResult:
        """Importe une transaction externe et retourne un BridgeResult encodable en IR PoL."""
        chain = chain.lower()
        if chain not in SUPPORTED_CHAINS:
            raise BridgeError(f"Chaîne non supportée : {chain}. Supportées : {SUPPORTED_CHAINS}")

        if chain == "bitcoin":
            return self._fetch_bitcoin(tx_hash)
        elif chain in ("ethereum", "bnb", "polygon", "avalanche"):
            rpc = {"ethereum": _ETH_RPC, "bnb": _BSC_RPC,
                   "polygon": _POLYGON_RPC, "avalanche": _AVAX_RPC}[chain]
            return self._fetch_evm(chain, tx_hash, rpc)
        elif chain == "solana":
            return self._fetch_solana(tx_hash)
        else:
            raise BridgeError(f"Chaîne non gérée : {chain}")

    def ping_chain(self, chain: str, *, timeout: float = 15) -> dict[str, Any]:
        """Vérifie la disponibilité du RPC d'une chaîne."""
        chain = chain.lower()
        try:
            if chain == "bitcoin":
                data = self._http_get(f"{_BTC_API}/blocks/tip/height", timeout=timeout)
                return {"chain": chain, "status": "ok", "tip_height": data}
            elif chain in ("ethereum", "bnb", "polygon", "avalanche"):
                rpc = {"ethereum": _ETH_RPC, "bnb": _BSC_RPC,
                       "polygon": _POLYGON_RPC, "avalanche": _AVAX_RPC}[chain]
                result = self._evm_rpc(rpc, "eth_blockNumber", [], timeout=timeout)
                block = int(result, 16) if isinstance(result, str) and result.startswith("0x") else result
                return {"chain": chain, "status": "ok", "block": block}
            elif chain == "solana":
                result = self._sol_rpc("getSlot", [], timeout=timeout)
                return {"chain": chain, "status": "ok", "slot": result}
            else:
                return {"chain": chain, "status": "unknown"}
        except Exception as exc:
            return {"chain": chain, "status": "error", "error": str(exc)[:100]}

    def status_all(self) -> list[dict[str, Any]]:
        """Ping toutes les chaînes en parallèle — timeout court (rapport 255: 105s sequential).

        20 s TTL cache: GRA11 egress is ~14 s; repeating the six RPCs on every
        OpenAPI probe is what made /bridges/status a burst killer.
        """
        import time

        from src.artcb.trace.ns import emit, now_mono_ns

        now = time.monotonic()
        if self._status_cache and now - self._status_cache[0] < self._status_ttl_s:
            emit(
                None,
                {
                    "kind": "bridges_status",
                    "cache": True,
                    "count": len(self._status_cache[1]),
                    "dur_ns": 0,
                    "ok": True,
                },
            )
            return list(self._status_cache[1])

        t0 = now_mono_ns()
        out: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=len(SUPPORTED_CHAINS)) as pool:
            futs = {pool.submit(self.ping_chain, c, timeout=2.0): c for c in SUPPORTED_CHAINS}
            try:
                for fut in as_completed(futs, timeout=2.5):
                    chain = futs[fut]
                    try:
                        out.append(fut.result(timeout=0.1))
                    except Exception as exc:
                        out.append({"chain": chain, "status": "error", "error": str(exc)[:100]})
            except TimeoutError:
                pass
        seen = {row.get("chain") for row in out}
        for chain in SUPPORTED_CHAINS:
            if chain not in seen:
                out.append({"chain": chain, "status": "timeout"})
        data_dir = None
        try:
            from src.artcb.config import load_settings

            data_dir = load_settings().data_dir
        except Exception:
            data_dir = None
        emit(
            data_dir,
            {
                "kind": "bridges_status",
                "cache": False,
                "count": len(out),
                "ok_n": sum(1 for r in out if r.get("status") == "ok"),
                "dur_ns": now_mono_ns() - t0,
                "ok": True,
            },
        )
        self._status_cache = (time.monotonic(), list(out))
        return out

    # ------------------------------------------------------------------
    # Implémentations par chaîne
    # ------------------------------------------------------------------

    def _fetch_bitcoin(self, tx_hash: str) -> BridgeResult:
        """Lit une transaction Bitcoin via mempool.space API."""
        data = self._http_get(f"{_BTC_API}/tx/{tx_hash}")
        if isinstance(data, dict) and "txid" not in data:
            raise BridgeError(f"Transaction Bitcoin introuvable : {tx_hash}")
        vin = data.get("vin", [{}])[0]
        vout = data.get("vout", [{}])[0]
        from_addr = vin.get("prevout", {}).get("scriptpubkey_address", "coinbase")
        to_addr = vout.get("scriptpubkey_address", "unknown")
        value_sat = vout.get("value", 0)
        value_btc = f"{value_sat / 1e8:.8f} BTC"
        block_height = data.get("status", {}).get("block_height")
        ts = data.get("status", {}).get("block_time")
        timestamp = datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts else datetime.now(UTC).isoformat()
        result = BridgeResult(
            chain="bitcoin", tx_hash=tx_hash,
            block_number=block_height, from_address=from_addr,
            to_address=to_addr, value=value_btc,
            timestamp=timestamp, raw_data=data,
        )
        result.ir_text = result.to_ir_text()
        return result

    def _fetch_evm(self, chain: str, tx_hash: str, rpc_url: str) -> BridgeResult:
        """Lit une transaction EVM via JSON-RPC (Ethereum/BNB/Polygon/Avalanche)."""
        tx = self._evm_rpc(rpc_url, "eth_getTransactionByHash", [tx_hash])
        if not tx or tx is None:
            raise BridgeError(f"Transaction {chain} introuvable : {tx_hash}")
        receipt = self._evm_rpc(rpc_url, "eth_getTransactionReceipt", [tx_hash])
        value_wei = int(tx.get("value", "0x0"), 16)
        value_eth = f"{value_wei / 1e18:.8f} {chain.upper()[:3]}"
        block_num_hex = tx.get("blockNumber", "0x0")
        block_num = int(block_num_hex, 16) if isinstance(block_num_hex, str) else None
        from_addr = tx.get("from", "unknown")
        to_addr = tx.get("to") or "contract-creation"
        result = BridgeResult(
            chain=chain, tx_hash=tx_hash,
            block_number=block_num, from_address=from_addr,
            to_address=to_addr, value=value_eth,
            timestamp=datetime.now(UTC).isoformat(),
            raw_data={"tx": tx, "receipt": receipt or {}},
        )
        result.ir_text = result.to_ir_text()
        return result

    def _fetch_solana(self, tx_hash: str) -> BridgeResult:
        """Lit une transaction Solana via JSON-RPC."""
        tx = self._sol_rpc("getTransaction", [tx_hash, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
        if not tx:
            raise BridgeError(f"Transaction Solana introuvable : {tx_hash}")
        accounts = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
        from_addr = accounts[0] if accounts else "unknown"
        to_addr = accounts[1] if len(accounts) > 1 else "unknown"
        slot = tx.get("slot", 0)
        meta = tx.get("meta", {})
        fee = meta.get("fee", 0)
        result = BridgeResult(
            chain="solana", tx_hash=tx_hash,
            block_number=slot, from_address=from_addr,
            to_address=to_addr, value=f"{fee} lamports fee",
            timestamp=datetime.now(UTC).isoformat(), raw_data=tx,
        )
        result.ir_text = result.to_ir_text()
        return result

    # ------------------------------------------------------------------
    # Helpers HTTP
    # ------------------------------------------------------------------

    @staticmethod
    def _http_get(url: str, timeout: float = 15) -> Any:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ARTCB-Bridge/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip().startswith(("{", "[")) else raw
        except urllib.error.HTTPError as exc:
            raise BridgeError(f"HTTP {exc.code} GET {url}") from exc
        except Exception as exc:
            raise BridgeError(f"GET {url}: {exc}") from exc

    @classmethod
    def _evm_rpc(cls, rpc_url: str, method: str, params: list, timeout: float = 15) -> Any:
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(
            rpc_url, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ARTCB-Bridge/0.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                if "error" in data:
                    raise BridgeError(f"RPC error: {data['error']}")
                return data.get("result")
        except BridgeError:
            raise
        except Exception as exc:
            raise BridgeError(f"EVM RPC {method}: {exc}") from exc

    @classmethod
    def _sol_rpc(cls, method: str, params: list, timeout: float = 15) -> Any:
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(
            _SOL_RPC, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ARTCB-Bridge/0.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                if "error" in data:
                    raise BridgeError(f"Solana RPC error: {data['error']}")
                return data.get("result")
        except BridgeError:
            raise
        except Exception as exc:
            raise BridgeError(f"Solana RPC {method}: {exc}") from exc
