"""Environment configuration loader — secrets from .env only (never committed).

REGLES D'USAGE (rapport 112 — 2026-08-04) :
  .env et Doppler sont EXCLUSIVEMENT pour l'usage personnel du fondateur
  et les phases de developpement. Ils ne contiennent JAMAIS de parametres
  affectant les regles du protocole en production.

  Parametres dans .env/Doppler (OK) :
    - Cles API tierces (BOB_API_KEY, GITHUB_TOKEN, GRADIUM_API_KEY, etc.)
    - Parametres d'infrastructure (ports, chemins, mode debug)
    - Coefficients PoL alpha/beta/gamma (dev uniquement)

  Parametres INTERDITS dans .env/Doppler (protocole immutable) :
    - ARTCB_POL_THRESHOLD  -> remplace par IMMUTABLE_POL_THRESHOLD dans tokenomics.py
    - Supply max           -> IMMUTABLE_MAX_SUPPLY_ARTCB dans tokenomics.py
    - Droits createur      -> graves dans genesis block, jamais dans .env
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv

load_dotenv()

# Well-known HTTP seeds — consumed at process start (D-045). Extra URLs via
# ARTCB_BOOTSTRAP_NODES (comma-separated). Old Replit host kept as alias.
REPLIT_PUBLIC_URL = "https://artcb--vgac42371.replit.app"
BOOTSTRAP_NODES: list[str] = [
    "http://152.228.144.34:8000",
    "http://151.80.107.29:8000",
    "http://51.44.222.232:8000",
    "http://91.134.45.8:8000",
    REPLIT_PUBLIC_URL,
    "https://artcb--vgacofficiel.replit.app",
]


def bootstrap_nodes() -> list[str]:
    extra = [x.strip().rstrip("/") for x in os.getenv("ARTCB_BOOTSTRAP_NODES", "").split(",") if x.strip()]
    seen: list[str] = []
    for url in [*BOOTSTRAP_NODES, *extra]:
        cleaned = url.rstrip("/")
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen

ARTCB_GITHUB_REPO = "https://github.com/vgac2025/artcb"
ARTCB_DOMAIN = "artcb.space"


@dataclass(frozen=True)
class ArtcbSettings:
    debug: bool
    encode_mode: str
    llm_enabled: bool
    bob_api_key: str | None
    bob_api_base: str
    bob_model: str
    bob_team_id: str | None
    bob_instance_id: str | None
    gradium_api_key: str | None
    gradium_api_url: str
    github_token: str | None
    ionos_api_key: str | None   # Clé API IONOS DNS (rapport 116)
    data_dir: Path
    log_dir: Path
    reports_dir: Path
    demo_book_pdf: Path
    pol_alpha: float
    pol_beta: float
    pol_gamma: float
    # NOTE : pol_threshold est RETIRE de ArtcbSettings.
    # Utiliser IMMUTABLE_POL_THRESHOLD depuis src/artcb/tokenomics.py.
    # La variable ARTCB_POL_THRESHOLD dans .env est ignoree par le scorer.


def load_settings() -> ArtcbSettings:
    def _bool(name: str, default: str = "true") -> bool:
        return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}

    return ArtcbSettings(
        debug=_bool("ARTCB_DEBUG", "true"),
        encode_mode=os.getenv("ARTCB_ENCODE_MODE", "rule-based"),
        llm_enabled=_bool("ARTCB_LLM_ENABLED", "false"),
        bob_api_key=os.getenv("BOB_API_KEY") or os.getenv("OPENROUTER_API_KEY") or None,
        bob_api_base=os.getenv("BOB_API_BASE", "https://api.us-east.bob.ibm.com"),
        bob_model=os.getenv("BOB_MODEL", "ibm/granite-3-8b-instruct"),
        bob_team_id=os.getenv("BOB_TEAM_ID") or None,
        bob_instance_id=os.getenv("BOB_INSTANCE_ID") or None,
        gradium_api_key=os.getenv("GRADIUM_API_KEY") or None,
        gradium_api_url=os.getenv("GRADIUM_API_URL", "https://api.gradium.ai"),
        github_token=os.getenv("GITHUB_TOKEN") or None,
        ionos_api_key=os.getenv("IONOS_API_KEY") or None,
        data_dir=Path(os.getenv("ARTCB_DATA_DIR", "./data")),
        log_dir=Path(os.getenv("ARTCB_LOG_DIR", "./logs")),
        reports_dir=Path(os.getenv("ARTCB_REPORTS_DIR", "./rapports")),
        demo_book_pdf=Path(
            os.getenv(
                "ARTCB_DEMO_BOOK_PDF",
                "data/fixtures/wailly_le_roi_de_l_inconnu.pdf",
            )
        ),
        pol_alpha=float(os.getenv("ARTCB_POL_ALPHA", "0.4")),
        pol_beta=float(os.getenv("ARTCB_POL_BETA", "0.3")),
        pol_gamma=float(os.getenv("ARTCB_POL_GAMMA", "0.3")),
        # pol_threshold SUPPRIME — utiliser IMMUTABLE_POL_THRESHOLD de tokenomics.py
    )
