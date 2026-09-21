.PHONY: chain test api frontend demo demo-real \
        env-docker env-replit env-dev env-codespaces \
        docker-build docker-up docker-down docker-logs \
        ssh-setup test-fast deploy-check \
        node-start p2p-status p2p-connect test-p2p \
        install-hooks check-hooks

# ─── Hooks Git (R406) ─────────────────────────────────────────────────────────
# À exécuter après chaque nouveau clone : make install-hooks
# Installe le hook pre-commit R405 (auto-bump MODULE_VERSION) dans .git/hooks/
install-hooks:
	@echo "[R406] Installation du hook pre-commit R405 (auto-bump MODULE_VERSION)..."
	python3 scripts/artcb_r405_install_precommit_hook.py
	@echo "[R406] ✅ Hook installé. Vérification :"
	python3 scripts/artcb_r405_install_precommit_hook.py --check

check-hooks:
	@echo "[R406] Vérification de l'état du hook pre-commit R405..."
	python3 scripts/artcb_r405_install_precommit_hook.py --check

# ─── Build ────────────────────────────────────────────────────────────────────
chain:
	$(MAKE) -C src/c all

# ─── Tests ────────────────────────────────────────────────────────────────────
test:
	doppler run -- python3 -m pytest tests/ -x -q --tb=short

test-fast:
	doppler run -- python3 -m pytest tests/ -x -q --tb=short -m "not slow"

test-mcp:
	doppler run -- python3 -m pytest tests/test_mcp_server.py -v

# ─── API ──────────────────────────────────────────────────────────────────────
api:
	doppler run -- python3 -m uvicorn src.api.main:app \
		--host 0.0.0.0 --port 8000 --reload --log-level info

api-prod:
	doppler run -- python3 -m uvicorn src.api.main:app \
		--host 0.0.0.0 --port 8000 --workers 2 --log-level warning

# ─── Frontend ─────────────────────────────────────────────────────────────────
frontend:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm install && npm run build

# ─── Demo ─────────────────────────────────────────────────────────────────────
demo:
	@echo "Requires API already running: make api  (port 8000)"
	python3 scripts/demo_live.py

demo-real:
	bash scripts/run_real_local.sh

# ─── Environnements (12.3.7) ──────────────────────────────────────────────────
env-dev:
	@echo "=== Environnement local (dev) ==="
	@echo "1. pip install -r requirements.txt"
	@echo "2. doppler run -- make api"
	pip install -r requirements.txt

env-docker:
	@echo "=== Environnement Docker ==="
	docker compose up --build -d
	@echo "API : http://localhost:8000/api/v1/health"

env-docker-down:
	docker compose down

env-replit:
	@echo "=== Environnement Replit ==="
	bash scripts/replit_start.sh

env-codespaces:
	@echo "=== Environnement Codespaces / Gitpod ==="
	bash .devcontainer/setup.sh
	doppler run -- python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# ─── Docker ───────────────────────────────────────────────────────────────────
docker-build:
	docker build -t artcb/node:latest .

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f artcb-api

docker-multinode:
	docker compose --profile multinode up -d

# ─── Phase 13 — libp2p P2P natif ──────────────────────────────────────────────
node-start:
	@echo "=== Démarrage nœud libp2p ARTCB Phase 13 (port 18444) ==="
	doppler run -- python3 -m src.artcb.p2p.libp2p_node --port 18444

node-start-seed:
	@echo "=== Nœud libp2p + seed $(SEED) ==="
	doppler run -- python3 -m src.artcb.p2p.libp2p_node --port 18444 --seed $(SEED)

p2p-status:
	@echo "=== Statut nœud libp2p (API http://localhost:8000) ==="
	curl -s http://localhost:8000/api/v1/p2p/libp2p/status | python3 -m json.tool

p2p-connect:
	@echo "=== Connexion pair libp2p HOST=$(HOST) PORT=$(PORT) ==="
	curl -s -X POST http://localhost:8000/api/v1/p2p/libp2p/connect \
		-H "Content-Type: application/json" \
		-d '{"host":"$(HOST)","port":$(PORT)}' | python3 -m json.tool

p2p-dht:
	@echo "=== Table Kademlia DHT ==="
	curl -s http://localhost:8000/api/v1/p2p/libp2p/dht | python3 -m json.tool

test-p2p:
	doppler run -- python3 -m pytest tests/test_libp2p_p2p.py -v --tb=short

# ─── SSH / Git ────────────────────────────────────────────────────────────────
ssh-setup:
	bash scripts/setup_ssh_git.sh

# ─── Vérification déploiement ─────────────────────────────────────────────────
deploy-check:
	@echo "=== Vérification pré-déploiement ARTCB ==="
	@python3 -c "import src.api.main; print('  API : OK')" 2>/dev/null || echo "  API : ERREUR"
	@python3 -c "import oqs; print('  liboqs PQC : OK')" 2>/dev/null || echo "  liboqs PQC : absent (fallback X25519)"
	@doppler --version 2>/dev/null && echo "  Doppler : OK" || echo "  Doppler : absent"
	@docker --version 2>/dev/null && echo "  Docker : OK" || echo "  Docker : absent"
	@python3 -m pytest tests/ --co -q 2>/dev/null | tail -1

help:
	@echo ""
	@echo "ARTCB — Commandes disponibles"
	@echo "────────────────────────────────────────────────────"
	@echo "  make api              Lancer l'API locale (port 8000)"
	@echo "  make test             Lancer tous les tests"
	@echo "  make test-fast        Tests rapides (sans marquage slow)"
	@echo "  make test-mcp         Tests MCP uniquement"
	@echo "  make test-p2p         Tests libp2p Phase 13 uniquement"
	@echo "  make env-dev          Setup environnement local"
	@echo "  make env-docker       Lancer via Docker Compose"
	@echo "  make env-replit       Lancer sur Replit"
	@echo "  make env-codespaces   Lancer sur Codespaces/Gitpod"
	@echo "  make docker-build     Builder l'image Docker"
	@echo "  make docker-multinode Lancer 2 nœuds ARTCB"
	@echo "  make ssh-setup        Setup SSH Git persistant (Replit)"
	@echo "  make deploy-check     Vérifier l'installation"
	@echo "  ── Phase 13 libp2p ──────────────────────────────"
	@echo "  make node-start       Démarrer le nœud P2P natif (port 18444)"
	@echo "  make node-start-seed SEED=host:port  Nœud + seed bootstrap"
	@echo "  make p2p-status       Afficher statut nœud libp2p"
	@echo "  make p2p-connect HOST=h PORT=p  Connecter un pair"
	@echo "  make p2p-dht          Afficher la table Kademlia DHT"
	@echo "────────────────────────────────────────────────────"
