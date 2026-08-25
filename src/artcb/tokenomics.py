"""ARTCB tokenomics constants — single source of truth.

Decisions validees (D-014, D-016, D-023 — 2026-08-25) :
  - Supply max      : 21 000 000 ARTCB (hard cap immuable)
  - Reward initial  : 50 ARTCB/bloc  (R_0, ancre R(H=1M)=50)
  - Halving fixe    : tous les 210 000 blocs  (50 × 210_000 × 2 = 21M)
  - R(H)            : 50 × (H / 1_000_000)^(-α), α = ln(50)/ln(64)
  - HBP(H)          : 10 % → 60 % → 20 % (0 / 4.15e9 / 8.3e9 humains)
  - P_owner(n)      : 100 % (n=1), puis 50 % → 10 % en continu
  - Halving dyna.   : epoch_dyn = floor(log2(velocity_24h / 144)) — soupape
                      de vitesse, jamais au-dessus du plafond 21M
  - Anti-Sybil      : conserve pour securite anti-malveillants uniquement
  - Pas de rate-limit : l'IA fonctionne en temps reel sans file d'attente

Identite mathematique du plafond :
    R_0 × HALVING_INTERVAL × 2 = 50 × 210_000 × 2 = 21_000_000 ARTCB
Le code 1 ARTCB / 105_000 blocs (rapports 045/080) convergait vers 210_000
ARTCB — divergence corrigee (rapport 124).

CONSTANTES IMMUABLES (rapports 112 + 106 — 2026-08-04, revise 124) :
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
# 50 ARTCB = ancre Bitcoin-compatible : 50 × 210_000 × 2 = 21_000_000.
INITIAL_BLOCK_REWARD_ARTCB    = 50.0
INITIAL_BLOCK_REWARD_SATOSHI  = int(INITIAL_BLOCK_REWARD_ARTCB * SATOSHI_PER_ARTCB)

# ── Halving fixe de base ───────────────────────────────────────────────────
# 210 000 blocs — D-016 d'origine, restaure rapport 124.
# (L'intervalle 105 000 des rapports 080/045 rendait le plafond 21M inatteignable
#  avec R_0=1 : 1 × 105_000 × 2 = 210_000 ARTCB.)
HALVING_INTERVAL = 210_000

# Nombre maximal de halvings (après quoi reward = 0)
MAX_HALVINGS = 64

# ── Supply max (hard cap absolue) ─────────────────────────────────────────
# 21 000 000 ARTCB — decision de design immuable (D-014).
# Le reseau rejette tout bloc qui ferait depasser ce plafond.
MAX_SUPPLY_ARTCB    = 21_000_000.0
MAX_SUPPLY_SATOSHI  = int(MAX_SUPPLY_ARTCB * SATOSHI_PER_ARTCB)

# ── CONSTANTES IMMUABLES DU PROTOCOLE ─────────────────────────────────────
# Ces valeurs sont utilisees DIRECTEMENT dans le code — jamais depuis .env.
# Elles refletent les regles gravees dans le genesis block (protocol_constants).
# Modifier ces valeurs sans vote de gouvernance = violation du protocole ARTCB.
#
# IMMUTABLE_POL_THRESHOLD   : seuil minimum de qualite PoL — aucun bloc en dessous
#                             de ce score n'est jamais accepte dans la chaine.
#                             Correspond a genesis["protocol_constants"]["pol_threshold"].
#
# IMMUTABLE_MAX_SUPPLY_ARTCB : plafond absolu de la supply — identique a MAX_SUPPLY_ARTCB
#                              mais nomme IMMUTABLE pour signaler l'interdiction de le
#                              lire depuis une variable d'environnement.
#
# IMMUTABLE_SATOSHI_PER_ARTCB : granularite monetaire — 1 ARTCB = 10^8 satoshi.
#                               Immuable pour garantir la coherence des calculs
#                               sur toute la duree de vie de la chaine.
IMMUTABLE_POL_THRESHOLD    = 0.6           # Jamais depuis .env — gravé genesis
IMMUTABLE_MAX_SUPPLY_ARTCB = 21_000_000    # Jamais depuis .env — gravé genesis
IMMUTABLE_SATOSHI_PER_ARTCB = 100_000_000  # Jamais depuis .env — granularite fixe

# ── Multiplicateur de poids du vote createur ───────────────────────────────
# Poids createur = max(1, votes_communaute * IMMUTABLE_CREATOR_VOTE_WEIGHT_MULTIPLIER)
# Ratio constant : 20 / 21 = 95.24% quelle que soit la taille de la communaute.
# Jamais depuis .env — immuable par definition du protocole.
# Utilise par governance/manager.py — ne jamais lire depuis une variable d'environnement.
IMMUTABLE_CREATOR_VOTE_WEIGHT_MULTIPLIER = 20

# ── Halving dynamique ──────────────────────────────────────────────────────
# Si la vitesse de minage dépasse VELOCITY_REFERENCE blocs/jour, le reward
# est divisé proportionnellement par un facteur dynamique (soupape).
# Le plafond 21M reste un hard cap : issued = min(schedule, R(H), remaining).
#
# Formule complète du reward pour un bloc à l'index I :
#
#   epoch_fixe    = I // HALVING_INTERVAL
#   epoch_dyn     = floor(log2(max(1, velocity_24h / VELOCITY_REFERENCE)))
#   extra_epochs  = epoch_fixe + epoch_dyn
#   schedule      = INITIAL_REWARD >> min(extra_epochs, MAX_HALVINGS - 1)
#   issued        = min(schedule, R(H), MAX_SUPPLY - issued_so_far)
#
# À faible adoption (devnet, H ≤ 1M, velocity ≤ 144/j) : issued = 50 ARTCB.
#
VELOCITY_REFERENCE = 144  # blocs/jour — référence Bitcoin (ajustable par gouvernance)

# Fenêtre temporelle pour mesurer la vitesse actuelle (en secondes)
VELOCITY_WINDOW_SECONDS = 86_400  # 24 heures
