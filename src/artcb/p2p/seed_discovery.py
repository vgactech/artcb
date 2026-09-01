"""Consume BOOTSTRAP_NODES so a git clone and Replit see live infrastructure.

Why this was not automatic from day one
---------------------------------------
``BOOTSTRAP_NODES`` used to list dead DNS names and **no startup path read
the list**. ``register-public`` only wrote the *local* ``peers.json``. HTTP
peers, libp2p DHT and gossip were three unbridged stores. Replit bootstrap
returned 503 on ``/p2p/*`` until a wallet existed. A clone therefore could
not discover anyone, and Replit could not be seen.

D-045: every process seeds a local directory from the well-known HTTP URLs
(even in bootstrap, without a wallet). Live probes are optional and skipped
in unit tests (``ARTCB_SKIP_SEED_DISCOVERY=1``).
"""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.artcb.config import bootstrap_nodes
from src.artcb.node_registry import NODES

logger = logging.getLogger("artcb.p2p.seed_discovery")


def skip_seed_discovery() -> bool:
    return os.getenv("ARTCB_SKIP_SEED_DISCOVERY", "").lower() in {"1", "true", "yes", "on"}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http_json(url: str, timeout: float = 1.5) -> tuple[int, dict[str, Any]]:
    try:
        import httpx

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            parsed = resp.json() if resp.content else {}
            return int(resp.status_code), parsed if isinstance(parsed, dict) else {"raw": parsed}
    except Exception as exc:  # noqa: BLE001 — discovery must never crash startup
        return 0, {"error": type(exc).__name__, "url": url}


class DirectoryStore:
    """Observer directory — no KEM required (Replit bootstrap / git clones)."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "p2p" / "directory.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write({"nodes": []})

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"nodes": []}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def upsert(self, entry: dict[str, Any]) -> dict[str, Any]:
        url = (entry.get("url") or "").rstrip("/")
        if not url:
            raise ValueError("directory url required")
        raw = self._read()
        items = [n for n in raw.get("nodes", []) if n.get("url") != url]
        entry = {**entry, "url": url, "updated_at": _now()}
        items.append(entry)
        raw["nodes"] = items[-200:]
        self._write(raw)
        return entry

    def list_nodes(self) -> list[dict[str, Any]]:
        return list(self._read().get("nodes", []))


def seed_urls() -> list[str]:
    return bootstrap_nodes()


def probe_seed(url: str, timeout: float = 1.5) -> dict[str, Any]:
    root = url.rstrip("/")
    health_c, health = _http_json(f"{root}/health", timeout=timeout)
    p2p_c, p2p = _http_json(f"{root}/api/v1/p2p/status", timeout=timeout)
    net_c, net = _http_json(f"{root}/api/v1/network/nodes", timeout=timeout)
    return {
        "url": root,
        "health_http": health_c,
        "p2p_http": p2p_c,
        "network_dir_http": net_c,
        "online": health_c == 200,
        "bootstrap_mode": bool(health.get("bootstrap_mode")) if isinstance(health, dict) else None,
        "git_sha": health.get("git_sha") if isinstance(health, dict) else None,
        "git_branch": health.get("git_branch") if isinstance(health, dict) else None,
        "network_id": (health.get("network_id") or p2p.get("network_id")) if isinstance(health, dict) else None,
        "protocol_version": health.get("protocol_version") if isinstance(health, dict) else None,
        "genesis_hash": health.get("genesis_hash") if isinstance(health, dict) else None,
        "kem_public_key_hex": p2p.get("kem_public_key_hex") if isinstance(p2p, dict) else "",
        "peer_count": p2p.get("peer_count") if isinstance(p2p, dict) else None,
        "directory_count": (net.get("live_online") if isinstance(net, dict) else None),
        "machine": health.get("machine") if isinstance(health, dict) else None,
    }


def probe_all_seeds(*, timeout: float = 1.5) -> list[dict[str, Any]]:
    urls = seed_urls()
    if skip_seed_discovery() or not urls:
        return [
            {
                "url": u,
                "health_http": 0,
                "online": None,
                "skipped": True,
                "reason": "ARTCB_SKIP_SEED_DISCOVERY",
            }
            for u in urls
        ]
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(urls)))) as pool:
        futs = {pool.submit(probe_seed, u, timeout): u for u in urls}
        try:
            for fut in as_completed(futs, timeout=max(3.0, timeout + 1.0)):
                try:
                    rows.append(fut.result())
                except Exception as exc:  # noqa: BLE001
                    rows.append({"url": futs[fut], "health_http": 0, "online": False, "error": type(exc).__name__})
        except TimeoutError:
            for fut, url in futs.items():
                if not fut.done():
                    fut.cancel()
                    rows.append({"url": url, "health_http": 0, "online": False, "error": "probe_deadline"})
    rows.sort(key=lambda r: r.get("url") or "")
    return rows


def static_registry_rows() -> dict[str, Any]:
    return {
        nid: {
            "display_name": spec.display_name,
            "provider": spec.provider,
            "health_http": spec.health_http,
            "api_https": spec.api_https,
            "notes": spec.public_notes,
        }
        for nid, spec in NODES.items()
    }


def seed_known_nodes(peers, identity, data_dir: Path) -> dict[str, Any]:
    """Best-effort: directory always; PeerManager only when remote KEM is real."""
    store = DirectoryStore(data_dir)
    report: dict[str, Any] = {"directory": [], "peers_added": [], "errors": [], "skipped": skip_seed_discovery()}
    for spec in NODES.values():
        url = (spec.health_http or spec.api_https or "").rstrip("/")
        if not url:
            continue
        entry = store.upsert(
            {
                "url": url,
                "node_id": spec.node_id,
                "provider": spec.provider,
                "source": "static_registry",
            }
        )
        report["directory"].append(entry["url"])
    if skip_seed_discovery():
        return report
    self_url = (getattr(identity, "node_public_url", None) or "").rstrip("/")
    for row in probe_all_seeds():
        url = row.get("url") or ""
        if not url or url == self_url:
            continue
        try:
            store.upsert(
                {
                    "url": url,
                    "source": "seed_probe",
                    "online": row.get("online"),
                    "git_sha": row.get("git_sha"),
                    "network_id": row.get("network_id"),
                    "bootstrap_mode": row.get("bootstrap_mode"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            report["errors"].append({"url": url, "error": type(exc).__name__})
            continue
        kem = (row.get("kem_public_key_hex") or "").strip()
        if peers is None or len(kem) < 64 or set(kem) <= {"0"}:
            continue
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host:
            continue
        try:
            peer = peers.add_peer(
                host=host,
                port=int(port),
                kem_public_key_hex=kem,
                label=f"seed:{host}",
                network_id=row.get("network_id") or "",
                protocol_version=row.get("protocol_version") or "",
                genesis_hash=row.get("genesis_hash") or "",
                scheme="https" if parsed.scheme == "https" else "http",
            )
            report["peers_added"].append(peer.peer_id)
        except Exception as exc:  # noqa: BLE001
            report["errors"].append({"url": url, "error": type(exc).__name__})
    logger.info(
        "seed_known_nodes directory=%s peers_added=%s errors=%s skipped=%s",
        len(report["directory"]),
        len(report["peers_added"]),
        len(report["errors"]),
        report["skipped"],
    )
    return report


def public_directory_payload(*, live: bool = False, data_dir: Path | None = None) -> dict[str, Any]:
    from src.artcb.crypto_policy import GENESIS_HASH, NETWORK_ID, PROTOCOL_VERSION

    live_rows = probe_all_seeds() if live and not skip_seed_discovery() else []
    announced: list[dict[str, Any]] = []
    if data_dir is not None:
        announced = DirectoryStore(data_dir).list_nodes()
    online = [r for r in live_rows if r.get("online")]
    return {
        "network_id": NETWORK_ID,
        "protocol_version": PROTOCOL_VERSION,
        "genesis_hash": GENESIS_HASH,
        "discovery": "static_registry_plus_consumed_bootstrap_seeds",
        "wallet_required_for_p2p": True,
        "wallet_required_to_list_nodes": False,
        "seeds": seed_urls(),
        "why_discovery_was_not_automatic": (
            "BOOTSTRAP_NODES existed as a constant but no process consumed it at "
            "startup; register-public wrote only local peers.json; bootstrap "
            "blocked /p2p until init-node."
        ),
        "nodes": static_registry_rows(),
        "announced": announced,
        "live": live_rows,
        "live_online": len(online),
        "live_probed": bool(live_rows) and not skip_seed_discovery(),
    }
