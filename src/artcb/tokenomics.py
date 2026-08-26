"""ARTCB tokenomics constants — single source of truth.

Decisions (D-014, D-024 — 2026-08-26) :
  - Supply max      : 21 000 000 ARTCB (hard cap immuable, D-014)
  - Reward initial  : 50 ARTCB/bloc  (R_0, ancre R(H=1M)=50)
  - Emission live   : R_block = min(R(H), remaining_21M)  — geopopulation
  - R(H)            : 50 × (H / 1_000_000)^(-α), α = ln(50)/ln(64)
  - HBP(H)          : 10 % → 60 % → 20 %
  - P_owner(n)      : 100 % (n=1), puis 50 % → 10 % en continu
  - Anti-Sybil      : conserve pour securite anti-malveillants uniquement
  - Pas de rate-limit : l'IA fonctionne en temps reel sans file d'attente

REMOVED from live emission (D-024, rapports 158–159–161) :
  - Halving fixe tous les 210 000 blocs (ex D-016)
  - extra_epochs / epoch_dyn = floor(log2(velocity_24h / 144))
  - identity 50 × 210_000 × 2 as the emission *schedule*
    (21M stays the hard cap; exhaustion date now depends on H(t))

CONSTANTES IMMUABLES (rapports 112 + 106 — 2026-08-04, revise 124, 161) :
  Ces valeurs NE PEUVENT PAS etre modifiees via .env / Doppler / Replit secrets.
  Elles sont utilisees directement par le code (IMMUTABLE_*).
  Tout changement necessite un vote de gouvernance + nouveau deploiement de code.
  Doppler et .env sont reserves a l'usage personnel du fondateur et phase de dev.
  Ils ne contiennent JAMAIS de parametres affectant le protocole en production.

  IMMUTABLE_CREATOR_VOTE_WEIGHT_MULTIPLIER :
    Poids createur = MULTIPLIER x nombre de votes communaute emis.
    Ratio constant = 20/21 = 95.24% quel que soit le nombre d'utilisateurs.
    Jamais depuis .env — grave dans le genesis block.
    Modifier cette valeur sans vote = violation du protocole ARTCB.
"""

# ── Unité monétaire ────────────────────────────────────────────────────────
# 1 ARTCB = 10^8 satoshi (meme granularite que Bitcoin)
SATOSHI_PER_ARTCB = 100_000_000

# ── Reward initial ─────────────────────────────────────────────────────────
# 50 ARTCB = ancre R(H=1M)=50. Plus un calendrier Bitcoin.
INITIAL_BLOCK_REWARD_ARTCB    = 50.0
INITIAL_BLOCK_REWARD_SATOSHI  = int(INITIAL_BLOCK_REWARD_ARTCB * SATOSHI_PER_ARTCB)

# ── Calendrier 210 000 — RETIRÉ du chemin d'émission (D-024) ───────────────
# Conservé uniquement comme archive pour les helpers deprecated et les
# anciennes chaînes / genesis v3.0. Ne PAS l'utiliser pour calculer R_block.
DEPRECATED_HALVING_INTERVAL = 210_000
# Alias transitoire : imports historiques ne cassent pas ; valeur non utilisée
# par issued_reward_satoshi / ChainManager._calculate_block_reward.
HALVING_INTERVAL = DEPRECATED_HALVING_INTERVAL

# Nombre maximal de halvings de l'ANCIEN calendrier (helpers deprecated only)
MAX_HALVINGS = 64

# ── Supply max (hard cap absolue) ─────────────────────────────────────────
# 21 000 000 ARTCB — decision de design immuable (D-014).
# Le reseau rejette tout bloc qui ferait depasser ce plafond.
# Les frais collectés reviennent au budget restant (rapport 161).
MAX_SUPPLY_ARTCB    = 21_000_000.0
MAX_SUPPLY_SATOSHI  = int(MAX_SUPPLY_ARTCB * SATOSHI_PER_ARTCB)

EMISSION_MODEL = "R(H)"  # min(population_reward, remaining_hard_cap)

# ── CONSTANTES IMMUABLES DU PROTOCOLE ─────────────────────────────────────
IMMUTABLE_POL_THRESHOLD    = 0.6           # Jamais depuis .env — gravé genesis
IMMUTABLE_MAX_SUPPLY_ARTCB = 21_000_000    # Jamais depuis .env — gravé genesis
IMMUTABLE_SATOSHI_PER_ARTCB = 100_000_000  # Jamais depuis .env — granularite fixe

# ── Multiplicateur de poids du vote createur ───────────────────────────────
IMMUTABLE_CREATOR_VOTE_WEIGHT_MULTIPLIER = 20

# ── Vélocité — RETIRÉE du reward (D-024) ───────────────────────────────────
# Conservée comme métrique d'observation uniquement, plus comme extra_epochs.
VELOCITY_REFERENCE = 144  # blocs/jour — métrique, PAS un halving
VELOCITY_WINDOW_SECONDS = 86_400  # 24 heures
