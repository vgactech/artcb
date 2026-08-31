# ARTCB — AI Reasoning Trace & Cognitive Blockchain

Persistent AI memory system: each thought becomes a signed node in a graph, compressible without loss and reconstructible identically. Built for LLM context continuity across sessions.

## Stack

- **Backend**: Python 3.11 / FastAPI (93 endpoints) — `src/`
- **Frontend**: React 18 + Vite (TypeScript) — `frontend/`
- **Blockchain**: Custom C library (`src/c/libartcb_chain.so`) + Python fallback
- **Crypto**: Ed25519 + ML-DSA-65 post-quantum signatures (liboqs optional, Ed25519 fallback active)

## How to run

The workflow `Start application` handles everything:
1. Creates/reuses a Python venv at `$HOME/venv`
2. Installs Python deps (`requirements.txt`) with `PIP_USER=false`
3. Patches oqs.py to prevent blocking auto-installs
4. Injects Doppler secrets if `DOPPLER_TOKEN_REPLIT` is set
5. Starts uvicorn on **port 5000** (Replit webview)

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

### Node identity (optional for startup)

The workflow can start without wallet secrets. In that case ARTCB runs in
**bootstrap mode**: `/health` and `/setup/*` remain available, while routes
that require a configured node identity return `503` until initialization.

To enable the full P2P node, initialize it through `POST /setup/init-node`
with a node name and an operator password. The endpoint creates the wallet,
stores the local node configuration, and returns the `seed_hex` only once.
Save that seed securely; it is the private signing key.

For a persistent deployment, the resulting `ARTCB_NODE_WALLET_ADDRESS` may
optionally be added to Replit Secrets. `ARTCB_NODE_PUBLIC_URL` is optional
because the startup script detects the Replit public URL automatically.
Never commit wallet addresses together with private seeds or passphrases.

## Replit-specific notes

- **pip installs must use `--no-user`** (or `PIP_USER=false`). Replit's global pip.conf sets `user = yes`, which breaks venv installs.
- **liboqs-python is excluded from `requirements.txt`** on Replit because its cmake build takes >10 minutes. The app automatically falls back to Ed25519/X25519. To enable full post-quantum crypto: `pip install liboqs-python` manually.
- **C library paths** (hardcoded in `scripts/replit_start.sh` for fast startup):
  - GCC: `/nix/store/a0d7m3zn9p2dfa1h7ag9h2wzzr2w25sn-gcc-wrapper-14.2.1.20250322/bin/cc`
  - OpenSSL (64-bit): `/nix/store/2cwpdm6fcc53f8jgxmagransrfp0igbl-openssl-3.4.1`

## User preferences

- Keep `liboqs-python` excluded from `requirements.txt` (use Ed25519 fallback on Replit)
- Always pass `--no-user` to pip inside venvs
