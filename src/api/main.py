"""FastAPI application — ARTCB MVP Phase 2+3."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from src.artcb.config import ARTCB_DOMAIN
from src.artcb.logging_config import setup_logging

# Configure the root logger before importing routers and application state.
# Their module-level initialization can emit warnings/errors during startup.
setup_logging("artcb.api")
logger = logging.getLogger("artcb.api")

from src.api.api_keys_routes import router as api_keys_router
from src.api.auth_routes import router as auth_router
from src.api.ai_routes import router_ai, router_chain_ext, router_webhooks
from src.api.security_routes import router_security
from src.api.pol_phase11_routes import router as pol_phase11_router
from src.api.connectors_routes import router as connectors_router
from src.api.dashboard_routes import router as dashboard_router
from src.api.economics_routes import router as economics_router
from src.api.bridges_routes import router as bridges_router
from src.api.deps import build_app_state
from src.api.devnet_routes import router as devnet_router
from src.api.governance_routes import router as governance_router
from src.api.groups_routes import router as groups_router
from src.api.mining_routes import router as mining_router
from src.api.notifications_routes import router as notifications_router
from src.api.p2p_routes import router as p2p_router
from src.api.consensus_routes import router as consensus_router
from src.api.libp2p_routes import router as libp2p_router
from src.api.pool_routes import router as pool_router
from src.api.routes import router as api_router
from src.api.symbols_routes import router as symbols_router
from src.api.websocket import router as ws_router
from src.api.privacy_routes import router as privacy_router
from src.api.setup_routes import router as setup_router
from src.api.network_routes import router as network_router

# Any Replit account — never a named Autoscale hostname in git.
REPLIT_CORS_ORIGIN_REGEX = r"https://.*\.(replit\.app|repl\.co|replit\.dev)"


def create_app() -> FastAPI:
    app = FastAPI(title="ARTCB API", version="0.3.0")
    # CORS : allow_origins=["*"] + allow_credentials=True est un anti-pattern
    # (la spec CORS interdit * avec credentials → Starlette reflète l'Origin).
    # On construit une liste blanche : domaines ARTCB + env var optionnelle ARTCB_CORS_ORIGINS.
    _extra = [o.strip() for o in os.getenv("ARTCB_CORS_ORIGINS", "").split(",") if o.strip()]
    _allowed_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        f"https://{ARTCB_DOMAIN}",
        f"https://n1.{ARTCB_DOMAIN}",
        f"https://n2.{ARTCB_DOMAIN}",
        f"https://node.{ARTCB_DOMAIN}",
        *_extra,
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_origin_regex=REPLIT_CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    state = build_app_state()
    app.state.artcb = state

    # Routes /setup/* — toujours montées (état bootstrap ou non)
    app.include_router(setup_router)
    app.include_router(network_router)

    if state.p2p_identity.bootstrap_mode:
        # ── MODE BOOTSTRAP ─────────────────────────────────────────────────
        # Le nœud n'a pas encore d'identité configurée.
        # Seules les routes /setup/* et /health sont accessibles.
        # Toutes les autres routes retournent 503 avec un message explicite.
        logger.warning(
            "ARTCB démarré en MODE BOOTSTRAP. "
            "Aucune identité P2P. Appeler POST /setup/init-node pour configurer."
        )

        def _bootstrap_health_response() -> dict:
            from src.artcb.crypto.pqc import pqc_available
            from src.artcb.crypto_policy import (
                GENESIS_HASH,
                NETWORK_ID,
                PROTOCOL_VERSION,
                public_health_block,
            )
            from src.artcb.release import release_identity
            _pqc = pqc_available()
            from src.artcb.security.hardware_identity import public_machine_view
            from src.artcb.p2p.seed_discovery import public_directory_payload
            identity = release_identity()
            pqc_block = public_health_block(_pqc)
            directory = public_directory_payload(
                live=False,
                data_dir=state.settings.data_dir,
            )
            return {
                "status": "bootstrap",
                "service": "ARTCB API",
                "version": identity["version"],
                "git_sha": identity["git_sha"],
                "git_branch": identity["git_branch"],
                "release_integrity": identity.get("release_integrity"),
                "pin_sha": identity.get("pin_sha"),
                "bootstrap_mode": True,
                "network_id": NETWORK_ID,
                "protocol_version": PROTOCOL_VERSION,
                "genesis_hash": GENESIS_HASH,
                "machine": public_machine_view(state.device_identity),
                "seeds": directory.get("seeds"),
                "message": (
                    "Nœud non configuré. "
                    "Appelez POST /setup/init-node avec {node_name, password} pour initialiser. "
                    "L'annuaire GET /api/v1/network/nodes fonctionne sans wallet."
                ),
                "setup_url": "/setup/init-node",
                "pqc": pqc_block,
            }

        @app.get("/live")
        async def live_bootstrap():
            return {"status": "alive", "bootstrap_mode": True}

        @app.get("/ready")
        async def ready_bootstrap():
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "bootstrap_mode": True,
                    "reason": "node_identity_missing",
                    "setup_url": "/setup/init-node",
                },
            )

        @app.get("/health")
        async def health_bootstrap():
            return _bootstrap_health_response()

        # Alias /api/v1/health — le frontend DashboardLayout appelle cette URL
        @app.get("/api/v1/health")
        async def health_bootstrap_api():
            return _bootstrap_health_response()

        @app.get("/api/v1/chain/verify")
        async def chain_verify_bootstrap():
            return {
                "valid": False,
                "bootstrap_mode": True,
                "reason": "node_not_initialized",
                "message": "POST /setup/init-node before chain verify is meaningful.",
            }

        @app.get("/")
        async def root_bootstrap():
            dist_index = os.path.join(
                os.path.dirname(__file__), "..", "..", "frontend", "dist", "index.html"
            )
            if os.path.isfile(dist_index):
                return FileResponse(dist_index)
            return JSONResponse(
                status_code=200,
                content={
                    "status": "bootstrap",
                    "service": "ARTCB API",
                    "version": "0.3.0",
                    "message": "API prête. Initialisez le nœud via POST /setup/init-node.",
                    "health_url": "/health",
                    "setup_url": "/setup/init-node",
                },
            )

        _dist_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
        )
        _dist_assets = os.path.join(_dist_dir, "assets")
        if os.path.isdir(_dist_assets):
            app.mount("/assets", StaticFiles(directory=_dist_assets), name="bootstrap-assets")

        @app.get("/api/v1/p2p/status")
        async def p2p_status_bootstrap():
            from src.artcb.crypto_policy import GENESIS_HASH, NETWORK_ID, PROTOCOL_VERSION
            from src.artcb.p2p.seed_discovery import public_directory_payload
            from src.artcb.security.hardware_identity import public_machine_view

            directory = public_directory_payload(live=False, data_dir=state.settings.data_dir)
            return {
                "bootstrap_mode": True,
                "wallet_initialized": False,
                "network_id": NETWORK_ID,
                "protocol_version": PROTOCOL_VERSION,
                "genesis_hash": GENESIS_HASH,
                "kem_public_key_hex": "",
                "peer_count": 0,
                "machine": public_machine_view(state.device_identity),
                "seeds": directory.get("seeds"),
                "announced": directory.get("announced"),
                "message": "Observer directory only — init-node required for full P2P.",
            }

        @app.get("/api/v1/p2p/peers")
        async def p2p_peers_bootstrap():
            from src.artcb.p2p.seed_discovery import public_directory_payload

            directory = public_directory_payload(live=False, data_dir=state.settings.data_dir)
            return {
                "bootstrap_mode": True,
                "peers": [],
                "count": 0,
                "seeds": directory.get("seeds"),
                "announced": directory.get("announced"),
            }

        # Routes API accessibles pendant le bootstrap (réponse explicite, pas 503 générique)
        _BOOTSTRAP_API_PASSTHROUGH = frozenset({
            "api/v1/health",
            "api/v1/chain/verify",
            "api/v1/network/nodes",
            "api/v1/p2p/status",
            "api/v1/p2p/peers",
        })

        @app.get("/{full_path:path}")
        async def bootstrap_catchall(full_path: str):
            # Routes déjà déclarées — FastAPI les intercepte avant ce catchall
            if full_path in ("", "health", "live", "ready", "setup/status", "setup/init-node",
                             "api/v1/health", "api/v1/chain/verify", "api/v1/network/nodes",
                             "api/v1/p2p/status", "api/v1/p2p/peers"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            # Servir le frontend SPA pour les routes non-API
            if os.path.isfile(os.path.join(_dist_dir, "index.html")) and not full_path.startswith(
                ("api/", "ws", "setup/")
            ):
                return FileResponse(os.path.join(_dist_dir, "index.html"))
            return JSONResponse(
                status_code=503,
                content={
                    "status": "bootstrap_required",
                    "error": "bootstrap_mode",
                    "wallet_initialized": False,
                    "chain_available": False,
                    "mining_available": False,
                    "reason": "wallet_initialization_required",
                    "message": (
                        "Ce nœud ARTCB n'est pas encore configuré. "
                        "Appelez POST /setup/init-node avec {node_name, password} "
                        "pour créer le wallet de nœud et activer toutes les routes. "
                        "Ceci n'est pas une erreur interne (500)."
                    ),
                    "setup_endpoint": "/setup/init-node",
                    "doc": "/setup/status",
                },
            )

        logger.debug("ARTCB API started bootstrap_mode=True")
        return app

    # ── MODE NORMAL — toutes les routes ────────────────────────────────────
    app.include_router(auth_router)
    app.include_router(api_keys_router)
    app.include_router(api_router)
    app.include_router(devnet_router)
    app.include_router(symbols_router)
    app.include_router(groups_router)
    app.include_router(connectors_router)
    app.include_router(mining_router)
    app.include_router(governance_router)
    app.include_router(p2p_router)
    app.include_router(consensus_router)
    app.include_router(pool_router)
    app.include_router(notifications_router)
    app.include_router(dashboard_router)
    app.include_router(economics_router)
    app.include_router(ws_router)
    app.include_router(router_ai)
    app.include_router(router_chain_ext)
    app.include_router(router_webhooks)
    app.include_router(router_security)
    app.include_router(pol_phase11_router)
    app.include_router(bridges_router)
    app.include_router(libp2p_router)
    app.include_router(privacy_router)
    logger.debug("ARTCB API started debug=%s bootstrap_mode=False", state.settings.debug)

    @app.get("/live")
    async def live_check():
        return {"status": "alive", "bootstrap_mode": False}

    @app.get("/ready")
    async def ready_check():
        from src.artcb.crypto.pqc import pqc_available
        from src.artcb.release import release_identity
        ident = release_identity()
        pqc = pqc_available()
        ready = bool(ident.get("git_sha")) and pqc
        payload = {
            "status": "ready" if ready else "not_ready",
            "bootstrap_mode": False,
            "release_sha": ident.get("git_sha"),
            "pqc_available": pqc,
        }
        return JSONResponse(status_code=200 if ready else 503, content=payload)

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        from src.artcb.crypto.pqc import pqc_available
        from src.artcb.crypto_policy import (
            GENESIS_HASH,
            NETWORK_ID,
            PROTOCOL_VERSION,
            public_health_block,
        )
        from src.artcb.release import release_identity
        from src.artcb.devnet_validation import certification_gate
        from src.artcb.security.hardware_identity import public_machine_view
        _pqc = pqc_available()
        identity = release_identity()
        try:
            gate = certification_gate()
            certified = bool(gate.get("certified_distributed_mainnet"))
        except Exception as exc:  # noqa: BLE001 — health must stay 200
            logger.error("certification_gate in /health failed: %s", type(exc).__name__)
            certified = False
        return {
            "status": "healthy",
            "service": "ARTCB API",
            "version": identity["version"],
            "git_sha": identity["git_sha"],
            "git_branch": identity["git_branch"],
            "release_integrity": identity.get("release_integrity"),
            "pin_sha": identity.get("pin_sha"),
            "bootstrap_mode": False,
            "network_id": NETWORK_ID,
            "protocol_version": PROTOCOL_VERSION,
            "genesis_hash": GENESIS_HASH,
            "pqc": public_health_block(_pqc),
            "certified_distributed_mainnet": certified,
            "machine": public_machine_view(state.device_identity),
        }

    # Serve React frontend (built dist/) at root
    _dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    _dist = os.path.normpath(_dist)
    if os.path.isdir(_dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

        @app.get("/")
        async def serve_spa_root():
            return FileResponse(os.path.join(_dist, "index.html"))

        @app.get("/{full_path:path}")
        async def serve_spa_fallback(full_path: str):
            # API routes take precedence — only catch unknown paths
            if full_path.startswith("api/") or full_path.startswith("ws"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            return FileResponse(os.path.join(_dist, "index.html"))

    else:
        # FIX DÉPLOIEMENT : frontend pas encore buildé (dist/ absent).
        # Retourner 200 pour que le healthcheck Replit passe pendant le build en arrière-plan.

        @app.get("/")
        async def serve_spa_loading():
            return JSONResponse(
                status_code=200,
                content={
                    "status": "starting",
                    "service": "ARTCB API",
                    "version": "0.3.0",
                    "note": "Frontend build in progress — API fully operational at /api/v1/"
                }
            )

        @app.get("/{full_path:path}")
        async def serve_spa_loading_fallback(full_path: str):
            if full_path.startswith("api/") or full_path.startswith("ws"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            return JSONResponse(
                status_code=200,
                content={"status": "starting", "note": "Frontend loading..."}
            )

    return app


app = create_app()
