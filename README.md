# ARTCB — AI Reasoning Trace & Cognitive Blockchain

**Mémoire persistante pour agents IA** : chaque pensée devient un nœud signé dans un graphe, compressible sans perte, retrouvable à l'identique.

[![Tests](https://img.shields.io/badge/tests-519%2F519%20passing-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-Proprietary-red)](LICENSE)

---

## Problème résolu

> *« Quand je travaille longtemps avec une IA, elle oublie tout. Je dois réexpliquer l'historique à chaque session. »*

ARTCB résout la perte de contexte des LLM via :
- **IR réversible** : Texte → Graphe → Texte (100 % identique)
- **Blockchain post-quantique** : ML-DSA-65 + Ed25519, 520 blocs actifs
- **Proof-of-Learning (PoL)** : récompense = Δ compression + validation sémantique
- **Dual-agent** : Explorer (génère) + Critic (valide) à chaque bloc
- **API Keys** : connecter Cursor, ChatGPT, LangChain via `Bearer artcb_xxx`
- **Multi-LLM** : OpenAI, Anthropic, Google AI (Gemini), Ollama, Cursor

---

## Démarrage rapide

```bash
git clone https://github.com/vgactech/artcb.git && cd artcb
bash install.sh
bash scripts/verify_installation.sh
uvicorn src.api.main:app --port 8000 --reload
cd frontend && npm install && npm run dev
```

- Frontend : http://localhost:5173
- API docs : http://localhost:8000/docs

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend React + Vite                     │
│  GraphViewer │ AgentPanel │ PolGauge │ Wallet │ API Keys    │
└──────────────────────────────┬──────────────────────────────┘
                               │ REST + WebSocket
┌──────────────────────────────▼──────────────────────────────┐
│               API FastAPI (93 endpoints)                     │
│  /ai/think  /ai/memo  /ir/rules  /pol/nft  /pol/transfer    │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌─────────┐ ┌────────┐ ┌──────────────┐
│ IR   │ │ RT-LEG │ │ Dual    │ │ PoL    │ │ Blockchain C │
│Engine│ │ Engine │ │ Agents  │ │ Scorer │ │ ML-DSA-65    │
└──────┘ └────────┘ └─────────┘ └────────┘ └──────────────┘
```

---

## Stack technique

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| Backend | Python 3.11 + FastAPI | 93 endpoints REST + WebSocket |
| Blockchain | C + ML-DSA-65 + Ed25519 | Post-quantique NIST 2024 |
| IR Engine | Python + spaCy | Texte → graphe réversible |
| Agents | Python asyncio | Explorer + Critic dual-agent |
| PoL | NumPy | Compression + validation + retrieval |
| Wallet | Ed25519 + Bech32 | Adresses `artcb1q…` + balance |
| Memory | FAISS | Recherche vectorielle sémantique |
| Smart contracts | IR v0.2 Rules | Règles SI…ALORS déclaratives |
| Frontend | React + Vite + Cytoscape | Graphe interactif, 7 langues |
| Tests | pytest | 519/519 passent |

---

## Installation

### Prérequis

- Python 3.11+
- Node.js 18+
- GCC (compilation lib C)

### Backend

```bash
git clone https://github.com/vgactech/artcb.git && cd artcb
bash install.sh
bash scripts/verify_installation.sh
uvicorn src.api.main:app --port 8000 --reload
```

### Frontend

```bash
cd frontend && npm install && npm run dev
```

`install.sh` installe le socle runtime sans compiler liboqs dans le chemin
critique. Le mode PQC est optionnel et borné :

```bash
ARTCB_INSTALL_PQC=1 ARTCB_PQC_TIMEOUT=300 bash install.sh
```

Un échec ou un timeout PQC laisse l'API opérationnelle avec le fallback
Ed25519/X25519 documenté par D-032. L'installation ne crée aucun wallet,
seed ou passphrase et n'appelle jamais `/setup/init-node`.

---

## Fonctionnalités disponibles

| Fonctionnalité | Endpoint | État |
|----------------|----------|------|
| Mémoriser un texte | `POST /api/v1/store` | ✅ |
| Explorer le graphe | `GET /api/v1/graph/{id}` | ✅ |
| Poser une question (IA pense) | `POST /api/v1/ai/think` | ✅ |
| Graver une observation | `POST /api/v1/ai/memo` | ✅ |
| Recherche sémantique | `GET /api/v1/chain/search` | ✅ |
| Vérifier la chaîne | `GET /api/v1/chain/verify` | ✅ |
| Wallet + rewards | `GET /api/v1/wallets` | ✅ |
| Générer une clé API | `POST /api/v1/api-keys/generate` | ✅ |
| Smart contracts PoL | `POST /api/v1/ir/rules` | ✅ |
| NFT sémantiques | `POST /api/v1/pol/nft/mint` | ✅ |
| Transactions PoL | `POST /api/v1/pol/transfer` | ✅ |
| Webhooks | `POST /api/v1/webhooks/register` | ✅ |
| Interface 7 langues | FR/EN/ZH/ES/PT/IT/RU | ✅ |

---

## Connexion via clé API (Cursor, ChatGPT, LangChain)

```bash
# 1. Générer une clé
curl -X POST http://localhost:8000/api/v1/api-keys/generate \
  -H "Content-Type: application/json" \
  -d '{"label": "mon-agent", "scopes": ["read","write","mining"]}'
# → {"token": "artcb_xxxx…"}  — copier UNE SEULE FOIS

# 2. Utiliser
curl -H "Authorization: Bearer artcb_xxxx" \
  http://localhost:8000/api/v1/ai/think \
  -H "Content-Type: application/json" \
  -d '{"question": "Comment corriger ce bug ?", "inject_context": true}'
```

Dans **Cursor** : Settings → Features → Rules for AI → ajouter l'endpoint et le header.

---

## Tests

```bash
python3 -m pytest tests/ -q         # 303/303 PASS
python3 -m pytest tests/ --tb=short # avec détail erreurs
```

---

## Tokenomics

Source de vérité : `DECISIONS_UTILISATEUR_ARTCB` (D-014, D-024, D-025) puis `TOKENOMICS_ARTCB` §4 / §14, puis le code (`src/artcb/tokenomics.py`, `emission.py`). Ce tableau ne fait que les refléter — voir `docs/PROTOCOL_SOURCE_OF_TRUTH.md`.

| Paramètre | Valeur (D-024 / D-025) |
|-----------|--------|
| Supply max | 21 000 000 ARTCB (D-014, `IMMUTABLE_MAX_SUPPLY_ARTCB`) |
| Émission par bloc | `min(R(H) × Δt / 600 s, remaining_21M)` — R(H) décroît avec la population humaine vérifiée H |
| Halving | **Aucun.** Le palier 210 000 blocs est retiré (D-024) ; `velocity` est une métrique, pas un halving |
| Seuil bloc | PoL ≥ 0.60 (`IMMUTABLE_POL_THRESHOLD`) |
| Partage | HBP 10 % → 60 % → 20 % ; M1 = 100 % permanent, OwnerDecay sur machines supplémentaires (D-025) |
| Frais | → `UniversalDividendVault`, jamais vers le supply restant (D-025) |
| Fondateurs | Pas d’allocation fixe « 5 × 210 000 » dans le chemin actif ; créateur bootstrap 100 % puis H0 = 100 (D-025) |

---

## Sécurité

| Mesure | Implémentation |
|--------|----------------|
| Signature bloc | ML-DSA-65 (post-quantique NIST 2024) + Ed25519 |
| Clés API | Stockées hash SHA-256 uniquement |
| Wallets | AES-256-GCM chiffré |
| Anti-Sybil | Validator + Slashing |
| Blockchain | Hash chaîné SHA-256, détection tampering |

---

## Documentation

| Fichier | Description |
|---------|-------------|
| [CAHIER_DES_CHARGES_ARTCB](CAHIER_DES_CHARGES_ARTCB) | Spécification complète |
| [PROTOCOLE_ARTCB](PROTOCOLE_ARTCB) | Règles de développement |
| [DECISIONS_UTILISATEUR_ARTCB](DECISIONS_UTILISATEUR_ARTCB) | Décisions D-0xx — source de vérité protocolaire |
| [docs/PROTOCOL_SOURCE_OF_TRUTH.md](docs/PROTOCOL_SOURCE_OF_TRUTH.md) | Hiérarchie décision → spec → code → tests → live |
| [TOKENOMICS_ARTCB](TOKENOMICS_ARTCB) | Supply 21 M, émission R(H) géopopulation, HBP, PoL |
| [ROADMAP_GENERAL_ARTCB](ROADMAP_GENERAL_ARTCB) | Phases 0–11 |
| [API_REFERENCE_ARTCB.md](API_REFERENCE_ARTCB.md) | 93 endpoints documentés |
| [FAQ_NON_EXPERTS_ARTCB.md](FAQ_NON_EXPERTS_ARTCB.md) | Questions non-techniques |
| [INDEX_ARTCB](INDEX_ARTCB) | Cartographie complète du projet |
| [CONFIGURATION_ARTCB](CONFIGURATION_ARTCB) | Variables d'environnement |
| [LICENCE_ARTCB.md](LICENCE_ARTCB.md) | Politique de licence |
| [GOUVERNANCE_ARTCB.md](GOUVERNANCE_ARTCB.md) | Gouvernance et vote |
| [rapports/](rapports/) | 98 rapports d'audit |

---

## Roadmap

- [x] Phase 0–4 : IR Engine, Backend, Blockchain C, Frontend
- [x] Phase 5 : Optimisations (+250% performance)
- [x] Phase 6 : Connecteurs LLM (OpenAI, Anthropic, Google AI, Ollama…)
- [x] Phase 7 : Pipeline minage apprentissage
- [x] Phase 8 : P2P ML-KEM + gouvernance + Anti-Sybil
- [x] Phase 9 : Pool E2E + CLI + API complet
- [x] Phase 10 : Tokenomics 21 M — émission géopopulation R(H), sans halving (D-024 / D-025)
- [x] Phase 11 : IR v0.2 smart contracts + PoL NFT + PoL Transfer
- [ ] Phase 12 : libp2p natif
- [ ] Phase 13 : Wikipedia connector

---

## Licence

**Titulaire : ARTCB (Société)**

| Réseau | Licence |
|--------|---------|
| Privé + Groupe | [Propriétaire](LICENSE-PROPRIETAIRE.md) — tous droits réservés |
| Public | [BSL 1.1](LICENSE-PUBLIC-BSL.md) — R&D, non-production |
| Dépôt (défaut) | [LICENSE](LICENSE) |

Politique complète : [LICENCE_ARTCB.md](LICENCE_ARTCB.md)  
Contact : contact@artcb.io

---

## Liens

- Dépôt : https://github.com/vgactech/artcb
- API Docs : http://localhost:8000/docs
- Frontend : http://localhost:5173
