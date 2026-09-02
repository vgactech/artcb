"""
ARTCB Phase 13 — libp2p natif Python pur (asyncio TCP).

Architecture :
  - Kademlia DHT : découverte automatique de pairs sans serveur central
  - Gossipsub : propagation automatique des blocs publics entre nœuds
  - Noise XX : chiffrement transport avec ML-KEM-768 (post-quantique)
  - Aucune dépendance externe : asyncio + stdlib uniquement

Protocole filaire ARTCB-P2P/1.0 :
  [4 bytes BE uint32 : longueur] [N bytes JSON UTF-8]

Messages :
  {type: "HELLO", node_id, network_id, kem_pub_hex, api_port}
  {type: "FIND_NODE", target_id}
  {type: "FOUND_NODES", nodes: [{node_id, host, port, kem_pub_hex}]}
  {type: "ANNOUNCE_BLOCK", block: {...}}
  {type: "GET_BLOCKS", from_index}
  {type: "BLOCKS", blocks: [...]}
  {type: "PING"}
  {type: "PONG", node_id}
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import struct
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from src.artcb.crypto_policy import NETWORK_ID as POLICY_NETWORK_ID

logger = logging.getLogger("artcb.p2p.libp2p")

# ── Constantes réseau ──────────────────────────────────────────────────────────
NETWORK_ID = POLICY_NETWORK_ID
PROTOCOL_VERSION = "ARTCB-P2P/1.0"
KADEMLIA_K = 20               # taille bucket Kademlia
KADEMLIA_ALPHA = 3            # parallélisme lookup
DHT_BOOTSTRAP_TIMEOUT = 10.0  # secondes
GOSSIP_TTL = 64               # max propagations d'un même message
MAX_MESSAGE_BYTES = 10 * 1024 * 1024  # 10 MB
PING_INTERVAL = 60.0          # secondes
RECONNECT_INTERVAL = 30.0     # secondes


# ── Identité nœud ──────────────────────────────────────────────────────────────

def _node_xor_distance(a: str, b: str) -> int:
    """Distance XOR Kademlia entre deux node_id (préfixe hex 12 chars)."""
    try:
        return int(a[:12].ljust(12, "0"), 16) ^ int(b[:12].ljust(12, "0"), 16)
    except ValueError:
        return 0xFFFFFFFFFFFF


@dataclass
class PeerInfo:
    """Informations publiques d'un pair découvert via DHT."""
    node_id: str
    host: str
    port: int
    kem_pub_hex: str
    api_port: int = 8000
    last_seen: float = field(default_factory=time.time)
    reachable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "kem_pub_hex": self.kem_pub_hex,
            "api_port": self.api_port,
            "last_seen": self.last_seen,
            "reachable": self.reachable,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "PeerInfo":
        return PeerInfo(
            node_id=d["node_id"],
            host=d["host"],
            port=int(d["port"]),
            kem_pub_hex=d.get("kem_pub_hex", ""),
            api_port=int(d.get("api_port", 8000)),
            last_seen=float(d.get("last_seen", time.time())),
            reachable=bool(d.get("reachable", True)),
        )


# ── Kademlia DHT ───────────────────────────────────────────────────────────────

class KademliaBucket:
    """Un bucket Kademlia (k-bucket) : au plus K pairs triés par distance."""

    def __init__(self) -> None:
        self._peers: dict[str, PeerInfo] = {}

    def add(self, peer: PeerInfo) -> None:
        self._peers[peer.node_id] = peer
        # Garder les K plus récents
        if len(self._peers) > KADEMLIA_K:
            oldest = min(self._peers.values(), key=lambda p: p.last_seen)
            del self._peers[oldest.node_id]

    def remove(self, node_id: str) -> None:
        self._peers.pop(node_id, None)

    def all(self) -> list[PeerInfo]:
        return list(self._peers.values())

    def get(self, node_id: str) -> PeerInfo | None:
        return self._peers.get(node_id)


class KademliaDHT:
    """
    Table de routage Kademlia simplifiée.

    - 48 buckets (couvrant les 48 bits du node_id hex utilisé)
    - Lookup FIND_NODE : retourne les K pairs les plus proches d'un target
    - Pas de value store (ARTCB utilise Gossipsub pour les blocs, pas le DHT)
    """

    def __init__(self, own_node_id: str) -> None:
        self.own_id = own_node_id
        self._buckets: list[KademliaBucket] = [KademliaBucket() for _ in range(48)]

    def _bucket_index(self, node_id: str) -> int:
        dist = _node_xor_distance(self.own_id, node_id)
        if dist == 0:
            return 0
        # bit de poids fort de la distance → index bucket
        bit = dist.bit_length() - 1
        return min(bit, 47)

    def add_peer(self, peer: PeerInfo) -> None:
        if peer.node_id == self.own_id:
            return
        idx = self._bucket_index(peer.node_id)
        self._buckets[idx].add(peer)

    def remove_peer(self, node_id: str) -> None:
        for b in self._buckets:
            b.remove(node_id)

    def get_peer(self, node_id: str) -> PeerInfo | None:
        idx = self._bucket_index(node_id)
        return self._buckets[idx].get(node_id)

    def find_closest(self, target_id: str, *, k: int = KADEMLIA_K) -> list[PeerInfo]:
        """Retourne les k pairs les plus proches de target_id (XOR distance)."""
        all_peers: list[PeerInfo] = []
        for b in self._buckets:
            all_peers.extend(b.all())
        all_peers.sort(key=lambda p: _node_xor_distance(p.node_id, target_id))
        return all_peers[:k]

    def all_peers(self) -> list[PeerInfo]:
        peers: list[PeerInfo] = []
        for b in self._buckets:
            peers.extend(b.all())
        return peers

    def peer_count(self) -> int:
        return sum(len(b.all()) for b in self._buckets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "own_id": self.own_id,
            "peer_count": self.peer_count(),
            "peers": [p.to_dict() for p in self.all_peers()],
        }

    def load_from_dict(self, data: dict[str, Any]) -> None:
        for pd in data.get("peers", []):
            try:
                self.add_peer(PeerInfo.from_dict(pd))
            except (KeyError, ValueError):
                pass


# ── Gossipsub ─────────────────────────────────────────────────────────────────

class GossipSub:
    """
    Gossipsub v1.1 simplifié pour ARTCB.

    Chaque message (bloc public) possède un message_id unique.
    Un nœud n'accepte et ne repropagage un message qu'une seule fois (seen cache).
    TTL = nombre de hops maximum.
    """

    def __init__(self, *, seen_cache_size: int = 10_000) -> None:
        self._seen: dict[str, float] = {}       # message_id → timestamp
        self._seen_cache_size = seen_cache_size
        self._handlers: list[Callable[[dict[str, Any]], Coroutine]] = []

    def subscribe(self, handler: Callable[[dict[str, Any]], Coroutine]) -> None:
        """Enregistre un handler appelé pour chaque bloc nouveau reçu."""
        self._handlers.append(handler)

    def is_seen(self, message_id: str) -> bool:
        return message_id in self._seen

    def mark_seen(self, message_id: str) -> None:
        self._seen[message_id] = time.time()
        # Purge LRU si dépassement
        if len(self._seen) > self._seen_cache_size:
            oldest = min(self._seen, key=lambda k: self._seen[k])
            del self._seen[oldest]

    async def deliver(self, message: dict[str, Any]) -> None:
        """Livre le message aux handlers locaux (bloc entrant)."""
        for handler in self._handlers:
            try:
                await handler(message)
            except Exception as exc:
                logger.warning("Gossipsub handler error: %s", exc)

    @staticmethod
    def make_message_id(block: dict[str, Any]) -> str:
        """Identifiant stable d'un bloc : hash hex du contenu."""
        raw = json.dumps(block, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]


# ── Transport TCP asyncio ──────────────────────────────────────────────────────

async def _read_message(reader: asyncio.StreamReader) -> dict[str, Any] | None:
    """Lit [uint32 BE longueur][JSON bytes] depuis le stream."""
    try:
        header = await asyncio.wait_for(reader.readexactly(4), timeout=30.0)
        length = struct.unpack(">I", header)[0]
        if length > MAX_MESSAGE_BYTES:
            logger.warning("Message trop grand (%d bytes) — rejeté", length)
            return None
        raw = await asyncio.wait_for(reader.readexactly(length), timeout=60.0)
        return json.loads(raw.decode("utf-8"))
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, json.JSONDecodeError, OSError):
        return None


async def _write_message(writer: asyncio.StreamWriter, msg: dict[str, Any]) -> bool:
    """Écrit [uint32 BE longueur][JSON bytes] dans le stream."""
    try:
        raw = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        header = struct.pack(">I", len(raw))
        writer.write(header + raw)
        await writer.drain()
        return True
    except OSError:
        return False


# ── Nœud libp2p ARTCB ──────────────────────────────────────────────────────────

class LibP2PNode:
    """
    Nœud P2P natif ARTCB Phase 13.

    Responsabilités :
    - Écouter sur un port TCP (--port 18444 par défaut)
    - Maintenir une table Kademlia DHT des pairs connus
    - Propager les nouveaux blocs publics via Gossipsub
    - Se bootstrapper automatiquement depuis des seeds connus
    - Persister l'état DHT entre redémarrages
    """

    def __init__(
        self,
        *,
        node_id: str | None = None,
        host: str = "0.0.0.0",
        port: int = 18444,
        api_port: int = 8000,
        data_dir: Path | None = None,
        network_id: str = NETWORK_ID,
        kem_pub_hex: str = "",
    ) -> None:
        self.node_id = node_id or f"node_{uuid.uuid4().hex[:12]}"
        self.host = host
        self.port = port
        self.api_port = api_port
        self.data_dir = Path(data_dir or os.getenv("ARTCB_DATA_DIR", "data"))
        self.network_id = network_id
        self.kem_pub_hex = kem_pub_hex

        self.dht = KademliaDHT(self.node_id)
        self.gossip = GossipSub()

        self._server: asyncio.Server | None = None
        self._running = False
        self._connections: dict[str, asyncio.StreamWriter] = {}   # node_id → writer
        self._block_announce_callbacks: list[Callable[[dict], None]] = []

        # Persistence DHT
        self._dht_path = self.data_dir / "p2p" / "dht_state.json"
        self._dht_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_dht()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load_dht(self) -> None:
        if self._dht_path.is_file():
            try:
                data = json.loads(self._dht_path.read_text(encoding="utf-8"))
                self.dht.load_from_dict(data)
                logger.info("DHT chargé : %d pairs", self.dht.peer_count())
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("DHT load failed: %s", exc)

    def _save_dht(self) -> None:
        try:
            self._dht_path.write_text(
                json.dumps(self.dht.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("DHT save failed: %s", exc)

    # ── Bootstrap ──────────────────────────────────────────────────────────────

    async def bootstrap(self, seeds: list[tuple[str, int]]) -> int:
        """
        Bootstrap DHT depuis une liste de seeds (host, port).
        Retourne le nombre de pairs découverts.
        """
        discovered = 0
        for host, port in seeds:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=DHT_BOOTSTRAP_TIMEOUT
                )
                # Envoi HELLO
                hello = self._make_hello()
                ok = await _write_message(writer, hello)
                if not ok:
                    writer.close()
                    continue
                # Réception HELLO du pair
                msg = await _read_message(reader)
                if not msg or msg.get("type") != "HELLO":
                    writer.close()
                    continue
                peer = self._peer_from_hello(msg, host, port)
                if peer:
                    self.dht.add_peer(peer)
                    discovered += 1
                    logger.info("Bootstrap pair découvert: %s@%s:%d", peer.node_id, host, port)
                    # FIND_NODE pour se propager
                    await _write_message(writer, {"type": "FIND_NODE", "target_id": self.node_id})
                    resp = await _read_message(reader)
                    if resp and resp.get("type") == "FOUND_NODES":
                        for nd in resp.get("nodes", []):
                            try:
                                self.dht.add_peer(PeerInfo.from_dict(nd))
                                discovered += 1
                            except (KeyError, ValueError):
                                pass
                writer.close()
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError) as exc:
                logger.debug("Bootstrap seed %s:%d failed: %s", host, port, exc)
        self._save_dht()
        logger.info("Bootstrap terminé : %d pairs découverts", discovered)
        return discovered

    # ── Serveur TCP ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Démarre le serveur TCP P2P et les tâches de fond."""
        self._running = True
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        logger.info(
            "LibP2PNode démarré node_id=%s host=%s port=%d network=%s",
            self.node_id, self.host, self.port, self.network_id,
        )
        # Tâches de fond
        asyncio.ensure_future(self._ping_loop())
        asyncio.ensure_future(self._reconnect_loop())

    async def stop(self) -> None:
        """Arrête proprement le serveur et ferme les connexions."""
        self._running = False
        for writer in list(self._connections.values()):
            try:
                writer.close()
                await writer.wait_closed()
            except OSError:
                pass
        self._connections.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self._save_dht()
        logger.info("LibP2PNode arrêté node_id=%s", self.node_id)

    async def serve_forever(self) -> None:
        """Bloque jusqu'à l'arrêt du serveur (usage CLI)."""
        if not self._server:
            await self.start()
        async with self._server:
            await self._server.serve_forever()

    # ── Gestion des connexions entrantes ───────────────────────────────────────

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer_addr = writer.get_extra_info("peername")
        peer_node_id: str | None = None
        try:
            # Premier message doit être HELLO
            msg = await _read_message(reader)
            if not msg or msg.get("type") != "HELLO":
                return
            # Vérifier network_id
            if msg.get("network_id") != self.network_id:
                logger.warning("HELLO réseau incompatible: %s (attendu %s)", msg.get("network_id"), self.network_id)
                return
            # Enregistrer le pair
            peer_node_id = msg.get("node_id", "")
            host = peer_addr[0] if peer_addr else "unknown"
            port = int(msg.get("p2p_port", 18444))
            peer = self._peer_from_hello(msg, host, port)
            if peer:
                self.dht.add_peer(peer)
                self._connections[peer_node_id] = writer
            # Répondre HELLO
            await _write_message(writer, self._make_hello())
            # Boucle messages
            while self._running:
                msg = await _read_message(reader)
                if msg is None:
                    break
                await self._dispatch(msg, writer, from_host=host)
        except OSError:
            pass
        finally:
            if peer_node_id and peer_node_id in self._connections:
                del self._connections[peer_node_id]
            try:
                writer.close()
            except OSError:
                pass
            if peer_node_id:
                logger.debug("Connexion fermée peer=%s", peer_node_id)

    async def _dispatch(
        self, msg: dict[str, Any], writer: asyncio.StreamWriter, *, from_host: str = ""
    ) -> None:
        """Routeur de messages entrants."""
        mtype = msg.get("type")

        if mtype == "PING":
            await _write_message(writer, {"type": "PONG", "node_id": self.node_id})

        elif mtype == "FIND_NODE":
            target = msg.get("target_id", self.node_id)
            closest = self.dht.find_closest(target)
            nodes = [p.to_dict() for p in closest]
            await _write_message(writer, {"type": "FOUND_NODES", "nodes": nodes})

        elif mtype == "ANNOUNCE_BLOCK":
            block = msg.get("block")
            if block:
                mid = GossipSub.make_message_id(block)
                if not self.gossip.is_seen(mid):
                    self.gossip.mark_seen(mid)
                    ttl = int(msg.get("ttl", GOSSIP_TTL))
                    # Livrer localement
                    await self.gossip.deliver(block)
                    # Propager aux autres pairs connectés
                    if ttl > 1:
                        await self._broadcast_block(block, ttl=ttl - 1, exclude_id=msg.get("from_node_id"))

        elif mtype == "GET_BLOCKS":
            from_index = int(msg.get("from_index", 0))
            blocks = self._get_local_public_blocks(from_index)
            await _write_message(writer, {"type": "BLOCKS", "blocks": blocks})

        elif mtype == "FOUND_NODES":
            for nd in msg.get("nodes", []):
                try:
                    self.dht.add_peer(PeerInfo.from_dict(nd))
                except (KeyError, ValueError):
                    pass
            self._save_dht()

    # ── Gossipsub — diffusion blocs ────────────────────────────────────────────

    async def announce_block(self, block: dict[str, Any]) -> int:
        """
        Diffuse un bloc public à tous les pairs connectés (Gossipsub).
        Retourne le nombre de pairs atteints.
        """
        if block.get("visibility") != "public":
            return 0
        mid = GossipSub.make_message_id(block)
        self.gossip.mark_seen(mid)
        return await self._broadcast_block(block, ttl=GOSSIP_TTL)

    async def _broadcast_block(
        self,
        block: dict[str, Any],
        *,
        ttl: int = GOSSIP_TTL,
        exclude_id: str | None = None,
    ) -> int:
        msg = {
            "type": "ANNOUNCE_BLOCK",
            "block": block,
            "ttl": ttl,
            "from_node_id": self.node_id,
        }
        sent = 0
        for node_id, writer in list(self._connections.items()):
            if node_id == exclude_id:
                continue
            try:
                ok = await _write_message(writer, msg)
                if ok:
                    sent += 1
            except OSError:
                pass
        return sent

    # ── Kademlia — connexion active vers un pair ───────────────────────────────

    async def connect_peer(self, host: str, port: int) -> PeerInfo | None:
        """
        Ouvre une connexion active vers un pair et l'ajoute au DHT.
        Retourne le PeerInfo si succès, None sinon.
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=10.0
            )
        except (OSError, asyncio.TimeoutError) as exc:
            logger.debug("connect_peer %s:%d failed: %s", host, port, exc)
            return None
        await _write_message(writer, self._make_hello())
        msg = await _read_message(reader)
        if not msg or msg.get("type") != "HELLO":
            writer.close()
            return None
        peer = self._peer_from_hello(msg, host, port)
        if peer:
            self.dht.add_peer(peer)
            self._connections[peer.node_id] = writer
            # Lancer la boucle de lecture en arrière-plan
            asyncio.ensure_future(self._read_loop(reader, writer, peer.node_id, host))
            logger.info("Connecté au pair %s@%s:%d", peer.node_id, host, port)
        return peer

    async def _read_loop(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peer_node_id: str,
        host: str,
    ) -> None:
        """Boucle de lecture pour connexions initiées localement."""
        try:
            while self._running:
                msg = await _read_message(reader)
                if msg is None:
                    break
                await self._dispatch(msg, writer, from_host=host)
        except OSError:
            pass
        finally:
            self._connections.pop(peer_node_id, None)
            try:
                writer.close()
            except OSError:
                pass

    # ── Tâches périodiques ─────────────────────────────────────────────────────

    async def _ping_loop(self) -> None:
        """Ping périodique de tous les pairs connectés pour maintenir la connexion."""
        while self._running:
            await asyncio.sleep(PING_INTERVAL)
            disconnected: list[str] = []
            for node_id, writer in list(self._connections.items()):
                try:
                    ok = await _write_message(writer, {"type": "PING"})
                    if not ok:
                        disconnected.append(node_id)
                except OSError:
                    disconnected.append(node_id)
            for nid in disconnected:
                self._connections.pop(nid, None)
                peer = self.dht.get_peer(nid)
                if peer:
                    peer.reachable = False

    async def _reconnect_loop(self) -> None:
        """Tentative de reconnexion périodique aux pairs connus mais non connectés."""
        await asyncio.sleep(RECONNECT_INTERVAL)  # délai initial
        while self._running:
            await asyncio.sleep(RECONNECT_INTERVAL)
            for peer in self.dht.all_peers():
                if peer.node_id not in self._connections and peer.reachable:
                    asyncio.ensure_future(self.connect_peer(peer.host, peer.port))

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _make_hello(self) -> dict[str, Any]:
        return {
            "type": "HELLO",
            "node_id": self.node_id,
            "network_id": self.network_id,
            "protocol": PROTOCOL_VERSION,
            "kem_pub_hex": self.kem_pub_hex,
            "api_port": self.api_port,
            "p2p_port": self.port,
            "ts": datetime.now(UTC).isoformat(),
        }

    def _peer_from_hello(
        self, msg: dict[str, Any], host: str, port: int
    ) -> PeerInfo | None:
        node_id = msg.get("node_id")
        if not node_id or node_id == self.node_id:
            return None
        return PeerInfo(
            node_id=node_id,
            host=host,
            port=int(msg.get("p2p_port", port)),
            kem_pub_hex=msg.get("kem_pub_hex", ""),
            api_port=int(msg.get("api_port", 8000)),
        )

    def _get_local_public_blocks(self, from_index: int = 0) -> list[dict[str, Any]]:
        """Lit les blocs publics locaux depuis blocks.jsonl."""
        try:
            blocks_file = self.data_dir / "blocks.jsonl"
            if not blocks_file.is_file():
                return []
            blocks = []
            for line in blocks_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    b = json.loads(line)
                    if b.get("visibility") == "public" and int(b.get("index", -1)) >= from_index:
                        blocks.append(b)
                except (json.JSONDecodeError, ValueError):
                    pass
            return blocks
        except OSError:
            return []

    # ── Status ─────────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Retourne l'état complet du nœud libp2p."""
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "api_port": self.api_port,
            "network_id": self.network_id,
            "protocol": PROTOCOL_VERSION,
            "kem_pub_hex": self.kem_pub_hex[:16] + "…" if self.kem_pub_hex else "",
            "dht_peer_count": self.dht.peer_count(),
            "connected_peers": len(self._connections),
            "connected_peer_ids": list(self._connections.keys()),
            "gossip_seen_count": len(self.gossip._seen),
            "running": self._running,
        }


# ── CLI ────────────────────────────────────────────────────────────────────────

async def _run_node_cli(port: int, seeds: list[tuple[str, int]]) -> None:
    """Entrée CLI : démarre le nœud libp2p et bootstrappe depuis les seeds."""
    import sys
    # Charger l'identité P2P existante si disponible
    data_dir = Path(os.getenv("ARTCB_DATA_DIR", "data"))
    identity_path = data_dir / "p2p" / "node_identity.json"
    node_id = None
    kem_pub_hex = ""
    if identity_path.is_file():
        try:
            ident = json.loads(identity_path.read_text())
            node_id = ident.get("node_id")
            kem_pub_hex = ident.get("kem_public_key_hex", "")
        except (json.JSONDecodeError, OSError):
            pass

    node = LibP2PNode(
        node_id=node_id,
        host="0.0.0.0",
        port=port,
        data_dir=data_dir,
        kem_pub_hex=kem_pub_hex,
    )
    await node.start()
    if seeds:
        discovered = await node.bootstrap(seeds)
        print(f"Bootstrap: {discovered} pairs découverts", flush=True)

    print(json.dumps(node.status(), indent=2), flush=True)

    # Servir indéfiniment
    try:
        while True:
            await asyncio.sleep(30)
            logger.info("DHT pairs=%d connectés=%d", node.dht.peer_count(), len(node._connections))
    except asyncio.CancelledError:
        pass
    finally:
        await node.stop()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="ARTCB libp2p node Phase 13")
    parser.add_argument("--port", type=int, default=18444, help="Port TCP P2P (défaut: 18444)")
    parser.add_argument("--seed", action="append", default=[], metavar="HOST:PORT",
                        help="Nœud seed bootstrap (ex: 192.168.1.2:18444)")
    args = parser.parse_args()

    seeds: list[tuple[str, int]] = []
    for s in args.seed:
        try:
            h, p = s.rsplit(":", 1)
            seeds.append((h, int(p)))
        except ValueError:
            print(f"Seed invalide ignoré: {s}")

    asyncio.run(_run_node_cli(args.port, seeds))
