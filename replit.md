# ARTCB — AI Reasoning Trace & Cognitive Blockchain

Persistent AI memory system: each thought becomes a signed node in a graph, compressible without loss and reconstructible identically. Built for LLM context continuity across sessions.

## Stack

- **Backend**: Python 3.11 / FastAPI (93 endpoints) — `src/`
- **Frontend**: React 18 + Vite (TypeScript) — `frontend/`
- **Blockchain**: Custom C library (`src/c/libartcb_chain.so`) + Python fallback
- **Crypto**: Ed25519 + ML-DSA-65 post-quantum signatures (liboqs optional, Ed25519 fallback active)

## How to run

The workflow `Start application` handles the fast boot path:
1. Keeps the published snapshot and does not clone GitHub during Autoscale boot
2. Reuses Replit's `.pythonlibs` runtime (never creates a venv in Autoscale)
3. Starts uvicorn on **port 5000** before optional work
4. Leaves PQC source compilation disabled by default; the API uses the documented fallback

For a fresh clone or an explicit dependency refresh, run:

```bash
bash install.sh
bash scripts/verify_installation.sh
```

The installer is idempotent. It installs all runtime requirements from the
single inventory, uses `npm ci` when a lockfile exists, and never creates a
wallet or calls `POST /setup/init-node`.

The React frontend is pre-built into `frontend/dist/` and served as static files by the FastAPI app at `/`.

To rebuild the frontend after changes:
```bash
cd frontend && npm run build
```

## Environment variables

See `.env.example` for all options. Key variables already set in `.replit`:

| Variable | Value | Purpose |
|---|---|---|
| `ARTCB_LLM_ENABLED` | `false` | LLM off by default (no key needed) |
| `ARTCB_ANTI_SYBIL_AI_BYPASS` | `true` | Relaxed rate-limits for dev |
| `ARTCB_ENCODE_MODE` | `rule-based` | IR engine mode |

Optional LLM keys (none required to run): `OPENROUTER_API_KEY`, `WATSONX_API_KEY`, `KAGGLE_KEY`, etc. — see `.env.example` for the full list.

### Required node identity secrets

For a Replit instance operating as an ARTCB node, add these values in the Replit Secrets panel before starting the workflow:

| Secret | Purpose |
|---|---|
| `ARTCB_NODE_WALLET_ADDRESS` | The node's `artcb1...` wallet address; anonymous node identities are rejected |
| `ARTCB_NODE_PUBLIC_URL` | The public HTTPS URL advertised by this node |

The current Replit environment has both secrets configured. Their values must never be committed to the repository.

## Replit-specific notes

- **pip installs must use `--no-user`** (or `PIP_USER=false`). Replit's global pip.conf sets `user = yes`, which breaks venv installs.
- **liboqs-python remains listed as a protocol dependency but is excluded from the runtime critical path** because its cmake build can take more than 10 minutes. The app automatically falls back to Ed25519/X25519. To attempt PQC without blocking the API: `ARTCB_INSTALL_PQC=1 ARTCB_PQC_TIMEOUT=300 bash install.sh`.
- **C library paths** (hardcoded in `scripts/replit_start.sh` for fast startup):
  - GCC: `/nix/store/a0d7m3zn9p2dfa1h7ag9h2wzzr2w25sn-gcc-wrapper-14.2.1.20250322/bin/cc`
  - OpenSSL (64-bit): `/nix/store/2cwpdm6fcc53f8jgxmagransrfp0igbl-openssl-3.4.1`

## User preferences

- Keep `liboqs-python` out of the runtime critical path; keep it in the complete dependency inventory and install it only through the bounded optional path
- Always pass `--no-user` to pip inside venvs
