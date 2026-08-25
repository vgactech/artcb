"""Shared API dependencies and application state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.artcb.agents.critic import DualAgentLoop
from src.artcb.agents.explorer import ExplorerAgent
from src.artcb.chain.manager import ChainManager
from src.artcb.config import ArtcbSettings, load_settings
from src.artcb.connectors.manager import ConnectorManager
from src.artcb.devnet.faucet import DevnetFaucet
from src.artcb.economics.human_binding import MachineRegistry
from src.artcb.economics.job_provider import JobProvider
from src.artcb.governance.manager import GovernanceManager
from src.artcb.groups.join_requests import JoinRequestManager
from src.artcb.groups.manager import GroupManager
from src.artcb.ir.decoder import IRDecoder
from src.artcb.ir.encoder import IREncoder
from src.artcb.ir.models import IRGraph
from src.artcb.ir.symbol_store import PersistentSymbolRegistry
from src.artcb.memory.graph_store import GraphStore
from src.artcb.memory.vector_store import VectorStore
from src.artcb.notifications.manager import NotificationManager
from src.artcb.p2p.gossip import GossipRegistry
from src.artcb.p2p.node_identity import NodeIdentityStore
from src.artcb.security.hardware_identity import DeviceIdentity, DeviceIdentityStore
from src.artcb.security.wallet_device_binding import WalletDeviceBindingStore
from src.artcb.p2p.peers import PeerManager
from src.artcb.p2p.public_archive import PublicBlockArchive
from src.artcb.p2p.symbol_archive import PublicSymbolArchive
from src.artcb.p2p.symbol_sync import SymbolSyncService
from src.artcb.p2p.sync import P2PSyncService
from src.artcb.pol.scorer import PolScorer
from src.artcb.pool.service import PoolService
from src.artcb.rtleg.timeline import RTLEGTimeline
from src.artcb.system.hardware import HardwareProfile, detect_hardware
from src.artcb.system.optimizer import (
    OptimizationProfile,
    apply_optimization_profile,
    build_optimization_profile,
)


@dataclass
class AppState:
    settings: ArtcbSettings
    encoder: IREncoder
    decoder: IRDecoder
    dual: DualAgentLoop
    timeline: RTLEGTimeline
    scorer: PolScorer
    graphs: GraphStore
    vectors: VectorStore
    chain: ChainManager
    groups: GroupManager
    join_requests: JoinRequestManager
    governance: GovernanceManager
    connectors: ConnectorManager
    notifications: NotificationManager
    p2p_peers: PeerManager
    p2p_identity: Any
    p2p_sync: P2PSyncService
    p2p_archive: PublicBlockArchive
    symbol_registry: PersistentSymbolRegistry
    symbol_archive: PublicSymbolArchive
    symbol_sync: SymbolSyncService
    gossip: GossipRegistry
    faucet: DevnetFaucet
    pool: PoolService | None = None
    hardware: HardwareProfile | None = None
    optimization: OptimizationProfile | None = None
    device_identity: DeviceIdentity | None = None
    wallet_device_binding: WalletDeviceBindingStore | None = None
    machine_registry: MachineRegistry | None = None
    job_provider: JobProvider | None = None
    pol_state: dict[str, Any] = field(default_factory=lambda: {
        "pol_score": 0.6,
        "delta_compression": 0.68,
        "validation_rate": 1.0,
        "retrieval_accuracy": 1.0,
        "block_accepted": True,
        "blocks_accepted": 0,
        "blocks_rejected": 0,
    })
    node_index: dict[str, tuple[str, str]] = field(default_factory=dict)

    def register_graph(self, graph: IRGraph) -> None:
        self.graphs.save(graph)
        self.vectors.index_graph(graph)
        for node in graph.nodes:
            self.node_index[node.id] = (graph.graph_id, node.txt)

    def get_graph(self, graph_id: str) -> IRGraph | None:
        if graph_id in self.graphs.cache:
            return self.graphs.cache[graph_id]
        return self.graphs.load(graph_id)

    def publish_public_symbols(
        self,
        orig_symbols: dict[str, str],
        *,
        block_index: int | None = None,
        graph_id: str | None = None,
    ) -> dict[str, str]:
        return self.symbol_sync.publish_public_symbols(
            orig_symbols,
            block_index=block_index,
            graph_id=graph_id,
        )


def build_app_state() -> AppState:
    settings = load_settings()
    hardware = detect_hardware()
    optimization = build_optimization_profile(hardware)
    apply_optimization_profile(optimization)
    graphs = GraphStore(settings.data_dir / "graphs")
    groups_dir = settings.data_dir / "groups"
    groups = GroupManager(groups_dir)
    governance = GovernanceManager(settings.data_dir)
    connectors = ConnectorManager(settings.data_dir)
    notifications = NotificationManager(settings.data_dir)
    p2p_peers = PeerManager(settings.data_dir)
    p2p_identity = NodeIdentityStore(settings.data_dir).load_or_create(api_port=8000)
    device_identity = DeviceIdentityStore(settings.data_dir).load_or_create()
    wallet_device_binding = WalletDeviceBindingStore(settings.data_dir)
    p2p_archive = PublicBlockArchive(settings.data_dir)
    symbol_registry = PersistentSymbolRegistry(settings.data_dir)
    symbol_archive = PublicSymbolArchive(settings.data_dir)
    symbol_sync = SymbolSyncService(
        registry=symbol_registry,
        archive=symbol_archive,
        peers=p2p_peers,
        node_id=p2p_identity.node_id,
    )
    gossip = GossipRegistry(settings.data_dir)
    faucet = DevnetFaucet(settings.data_dir)
    machine_registry = MachineRegistry(settings.data_dir / "economics" / "machines.json")
    job_provider = JobProvider(settings.data_dir / "economics" / "jobs.json")
    encoder = IREncoder(symbol_registry=symbol_registry.registry)
    explorer = ExplorerAgent(encoder=encoder, symbol_registry=symbol_registry)
    dual = DualAgentLoop(explorer=explorer)
    chain = ChainManager(settings.data_dir / "chain" / "blocks.jsonl")
    timeline = RTLEGTimeline()
    p2p_sync = P2PSyncService(
        chain=chain,
        peers=p2p_peers,
        identity=p2p_identity,
        archive=p2p_archive,
        symbol_sync=symbol_sync,
    )

    state = AppState(
        settings=settings,
        encoder=encoder,
        decoder=IRDecoder(),
        dual=dual,
        timeline=timeline,
        scorer=PolScorer(),
        graphs=graphs,
        vectors=VectorStore(),
        chain=chain,
        groups=groups,
        join_requests=JoinRequestManager(groups_dir, groups),
        governance=governance,
        connectors=connectors,
        notifications=notifications,
        p2p_peers=p2p_peers,
        p2p_identity=p2p_identity,
        p2p_sync=p2p_sync,
        p2p_archive=p2p_archive,
        symbol_registry=symbol_registry,
        symbol_archive=symbol_archive,
        symbol_sync=symbol_sync,
        gossip=gossip,
        faucet=faucet,
        pool=None,  # type: ignore[arg-type]
        hardware=hardware,
        optimization=optimization,
        device_identity=device_identity,
        wallet_device_binding=wallet_device_binding,
        machine_registry=machine_registry,
        job_provider=job_provider,
    )

    def _run_pool_reasoning(text: str) -> dict[str, Any]:
        from src.artcb.ir.models import sha256_text

        result = state.dual.run(text)
        graph = result.graph
        graph_root = sha256_text(graph.checksum).replace("sha256:", "")
        state.register_graph(graph)
        return {
            "graph_id": graph.graph_id,
            "pol_score": result.pol.pol_score,
            "graph_root": graph_root,
            "node_count": len(graph.nodes),
        }

    def _finalize_pool_job(job, full_text: str, extra_contributors: list[dict]) -> dict[str, Any]:
        from src.artcb.mining.pipeline import MiningPipeline
        from src.artcb.wallet.manager import WalletManager

        pipeline = MiningPipeline(
            dual=state.dual,
            chain=state.chain,
            wallet_manager=WalletManager(),
            connectors=state.connectors,
            groups=state.groups,
            timeline=state.timeline,
            register_graph=state.register_graph,
            publish_public_symbols=state.publish_public_symbols,
        )
        result = pipeline.run_from_text(
            full_text,
            session_id=f"pool_{job.job_id}",
            actor_address=job.actor_address,
            wallet_name=job.wallet_name,
            visibility=job.visibility,
            group_id=job.group_id,
            store_block=True,
            extra_contributors=extra_contributors,
            learning_source=f"pool:{job.job_id}",
        )
        return {
            "job_id": job.job_id,
            "graph_id": result.graph_id,
            "block_index": result.block_index,
            "block_hash": result.block_hash,
            "contributors": result.contributors,
            "pol_score": result.pol_score,
        }

    state.pool = PoolService(
        settings.data_dir,
        node_id=p2p_identity.node_id,
        kem_public_hex=p2p_identity.kem_public_key_hex,
        kem_secret_hex=p2p_identity.kem_secret_key_hex,
        run_reasoning=_run_pool_reasoning,
        finalize_job=_finalize_pool_job,
    )

    for graph in graphs.load_all():
        state.register_graph(graph)
    return state
