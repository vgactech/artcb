"""
ARTCB — Étude économique complète 100 ans
Cible : totalité des utilisateurs IA mondiaux (3 milliards d'ici 2030)
Données sources : TechCrunch 2026, Searchlab, AICPB

ARCHIVE — ce script simule encore un calendrier 210 000 blocs.
Le protocole live (D-024, 2026-08-26) n'utilise PLUS ce calendrier :
R_block = min(R(H), remaining_21M). Ne pas copier ces constantes dans le code.
Voir rapports/161_reponses_bootstrap_hbp_halving_geopop_2026-08-26.md.
"""
from __future__ import annotations
import math

# ── Constantes de base ──────────────────────────────────────────────────────
HALVING_INTERVAL   = 210_000
BLOCS_ACTUELS      = 520
ARTCB_MINES        = 814.0

# ── Données marché IA mondial (sources TechCrunch/Searchlab juin 2026) ──────
USERS_IA_2026  =  3_400_000_000   # total propriétaires estimés
USERS_OS_2026  =  3_210_000_000   # total open source (téléchargements/usages)
USERS_2026     =  3_400_000_000   # base conservative (propriétaires)
USERS_2030     =  3_000_000_000   # projection utilisateurs actifs quotidiens
CAGR_IA        =  0.375            # CAGR moyen 35-40%

# ── Hypothèse : 1 session PoL / utilisateur actif / jour = 1 bloc potentiel ─
# (Conservative : les utilisateurs ne mémorisent pas 100% de leurs échanges)
# Taux d'activation ARTCB = fraction des utilisateurs IA qui adoptent PoL

def supply_epuisee(blocs_jour: float, init_reward: float,
                   supply_max: float) -> float:
    """Retourne le nombre de jours pour épuiser la supply."""
    total = ARTCB_MINES
    jours = 0.0
    for epoch in range(200):
        reward = init_reward / (2 ** epoch)
        if reward < 1e-12:
            break
        artcb_ep = reward * HALVING_INTERVAL
        if total + artcb_ep >= supply_max:
            restant = supply_max - total
            jours += (restant / reward) / blocs_jour
            return jours
        total += artcb_ep
        jours += HALVING_INTERVAL / blocs_jour
    return jours

def fmt_duree(jours: float) -> str:
    if jours < 1/1440:
        return f"{jours*86400:.0f}sec"
    if jours < 1/24:
        return f"{jours*1440:.1f}min"
    if jours < 1:
        return f"{jours*24:.1f}h"
    if jours < 365:
        return f"{jours:.0f}j"
    if jours < 3650:
        return f"{jours/365:.1f}ans"
    if jours < 36500:
        return f"{jours/365:.0f}ans"
    return f"{jours/365:.0f}ans"

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 — SCÉNARIOS PAR TAUX D'ADOPTION (supply 21M, reward 1 ARTCB)
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 90)
print("SECTION 1 — IMPACT DU TAUX D'ADOPTION (supply=21M, reward=1 ARTCB/bloc)")
print("Base : 3.4 milliards d'utilisateurs IA (TechCrunch juin 2026)")
print("=" * 90)
print(f"{'Taux adoption':>14} {'Users ARTCB':>14} {'Blocs/j':>12} {'1er halving':>14} "
      f"{'Supply épuisée':>16} {'ARTCB/an 1':>12}")
print("-" * 90)

taux_list = [
    0.000_001,  # 0.0001%  → 3 400 users
    0.000_01,   # 0.001%   → 34 000 users
    0.000_1,    # 0.01%    → 340 000 users
    0.001,      # 0.1%     → 3.4M users
    0.01,       # 1%       → 34M users
    0.05,       # 5%       → 170M users
    0.10,       # 10%      → 340M users
    0.25,       # 25%      → 850M users
    0.50,       # 50%      → 1.7B users
    1.00,       # 100%     → 3.4B users
]

for taux in taux_list:
    users = int(USERS_2026 * taux)
    bj = float(users)  # 1 bloc/user/jour
    j_h1 = (HALVING_INTERVAL - BLOCS_ACTUELS) / bj
    se = supply_epuisee(bj, 1.0, 21_000_000)
    artcb_an1 = min(bj * 365, 21_000_000 - ARTCB_MINES)
    print(f"{taux*100:>13.4f}%  {users:>14,} {bj:>12,.0f} "
          f"{fmt_duree(j_h1):>14} {fmt_duree(se):>16} {artcb_an1:>12,.0f}")

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 — SCÉNARIO RÉALISTE SUR 10 ANS (croissance proportionnelle IA)
# ═══════════════════════════════════════════════════════════════════════════
print()
print("=" * 90)
print("SECTION 2 — SCÉNARIO RÉALISTE 10 ANS (croissance IA × ARTCB)")
print("Hypothèse adoption ARTCB = 0.1% des utilisateurs IA actifs")
print("Croissance IA : ×1.375/an (CAGR 37.5%) jusqu'à saturation 3B en 2030")
print("=" * 90)

users_ia_par_an = {
    1: 3_400_000_000,
    2: 3_600_000_000,
    3: 3_000_000_000,  # 2030 plateau
    4: 3_000_000_000,
    5: 3_200_000_000,
    6: 3_500_000_000,
    7: 4_000_000_000,
    8: 4_500_000_000,
    9: 5_000_000_000,
    10: 5_500_000_000,
}
TAUX_ADOPTION = 0.001  # 0.1%

cumul = ARTCB_MINES
blocs_cumul = BLOCS_ACTUELS
supply_done = False

print(f"{'An':>4} {'Users IA':>14} {'Users ARTCB':>14} {'Blocs/j':>10} "
      f"{'ARTCB année':>12} {'Cumul ARTCB':>14} {'% Supply':>10}")
print("-" * 90)

for an, users_ia in users_ia_par_an.items():
    if supply_done:
        break
    users_artcb = int(users_ia * TAUX_ADOPTION)
    bj = float(users_artcb)
    artcb_annee = min(bj * 365 * 1.0, 21_000_000 - cumul)
    cumul = min(cumul + artcb_annee, 21_000_000)
    blocs_cumul += bj * 365
    pct = cumul / 21_000_000 * 100
    if cumul >= 21_000_000:
        supply_done = True
    print(f"{an:>4}  {users_ia:>14,} {users_artcb:>14,} {bj:>10,.0f} "
          f"{artcb_annee:>12,.0f} {cumul:>14,.0f} {pct:>9.2f}%"
          + (" ← ÉPUISÉ" if supply_done else ""))

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 — HYPOTHÈSES TOKENOMICS : 6 CONFIGURATIONS SUR 100 ANS
# ═══════════════════════════════════════════════════════════════════════════
print()
print("=" * 90)
print("SECTION 3 — 6 CONFIGURATIONS TOKENOMICS × 3 SCÉNARIOS UTILISATEURS")
print("Durée supply épuisée (ou 'jamais' si > 100 ans)")
print("=" * 90)

configs = [
    # (label, supply_max, init_reward, halving_interval)
    ("Supply 21M  | Reward 1.0 | Halving 210K",   21_000_000, 1.0,   210_000),
    ("Supply 21M  | Reward 0.1 | Halving 210K",   21_000_000, 0.1,   210_000),
    ("Supply 21M  | Reward 0.01| Halving 210K",   21_000_000, 0.01,  210_000),
    ("Supply 210M | Reward 1.0 | Halving 210K",  210_000_000, 1.0,   210_000),
    ("Supply 210M | Reward 0.1 | Halving 210K",  210_000_000, 0.1,   210_000),
    ("Supply 21B  | Reward 1.0 | Halving 210K", 2_100_000_000, 1.0,  210_000),
    ("Supply 21M  | Reward 1.0 | Halving 2.1M",   21_000_000, 1.0, 2_100_000),
    ("Supply 21M  | Reward 1.0 | Halving 21M",    21_000_000, 1.0,21_000_000),
]

# 3 scénarios utilisateurs
scenarios_users = [
    ("1% adoption / 3.4B users (34M users)",   34_000_000),
    ("10% adoption / 3.4B users (340M users)", 340_000_000),
    ("100% adoption / 3.4B users (3.4B users)",3_400_000_000),
]

header = f"{'Configuration':<46}"
for label, _ in scenarios_users:
    header += f" {label[:22]:>22}"
print(header)
print("-" * 115)

for cfg_label, supply, reward, halving in configs:
    row = f"{cfg_label:<46}"
    for _, bj in scenarios_users:
        # recalculer avec ce halving
        total = ARTCB_MINES
        jours = 0.0
        for epoch in range(200):
            r = reward / (2 ** epoch)
            if r < 1e-14:
                break
            artcb_ep = r * halving
            if total + artcb_ep >= supply:
                restant = supply - total
                jours += (restant / r) / bj
                break
            total += artcb_ep
            jours += halving / bj
        else:
            jours = 99999 * 365
        duree = fmt_duree(jours)
        if jours > 36500:
            duree = ">100ans"
        row += f" {duree:>22}"
    print(row)

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 — MÉCANISMES D'AJUSTEMENT (analyse conceptuelle)
# ═══════════════════════════════════════════════════════════════════════════
print()
print("=" * 90)
print("SECTION 4 — MÉCANISMES D'AJUSTEMENT POSSIBLES")
print("=" * 90)

mecanismes = [
    ("A — Rate-limit global",
     "Max N blocs/heure réseau (ex: 6/h = 144/j comme Bitcoin)",
     "Préserve rareté + halvings, queue d'attente en pic",
     "Faible", "Anti-Sybil existant étendu"),
    ("B — Reward adaptatif",
     "Reward = 1 / (blocs_24h / 144), min 0.000001",
     "Durée ~infinie mais reward quasi nul à grande échelle",
     "Moyenne", "Modif mining_pipeline + tokenomics"),
    ("C — Supply élastique 210M",
     "Hard cap × 10 = 210M ARTCB",
     "×10 plus de tokens, rareté moindre mais > longévité",
     "Faible", "Changer MAX_SUPPLY_ARTCB"),
    ("D — Supply élastique 21B",
     "Hard cap × 1000 = 21 milliards ARTCB",
     "Comme Ethereum (pas de rareté extrême), dure 100+ ans",
     "Faible", "Changer MAX_SUPPLY_ARTCB"),
    ("E — Halving ×10 (2.1M blocs)",
     "Halving tous les 2.1M blocs au lieu de 210K",
     "×10 plus long avant 1er halving",
     "Faible", "Changer HALVING_INTERVAL"),
    ("F — Reward 0.01 ARTCB/bloc",
     "Diviser reward par 100 (micro-récompense PoL)",
     "Supply dure ×100 plus longtemps",
     "Faible", "Changer INITIAL_BLOCK_REWARD_ARTCB"),
    ("G — Combiné : 210M supply + 0.1 reward",
     "×10 supply + reward ÷10 = équivalent ×100 durée",
     "Optimal : rareté maintenue + longévité 100+ ans",
     "Faible", "2 constantes tokenomics"),
    ("H — PoL points non-fongibles",
     "Rewards = points non-transférables (reputation)",
     "Supply infinie en points, ARTCB rare conservé",
     "Haute", "Refonte modèle économique"),
]

for label, desc, avantage, complexite, impl in mecanismes:
    print(f"\n  {label}")
    print(f"    Mécanisme  : {desc}")
    print(f"    Avantage   : {avantage}")
    print(f"    Complexité : {complexite} — {impl}")

print()
print("=" * 90)
print("SECTION 5 — RECOMMANDATION FINALE")
print("=" * 90)
print("""
  Pour absorber 3.4 milliards d'utilisateurs IA sur 100 ans :

  Option RECOMMANDÉE : G (combiné) ou C+E
  ──────────────────────────────────────────────────────────────────────────
  • Supply 210M ARTCB (×10) : suffit pour 100 ans à 10% adoption mondiale
  • Reward 0.1 ARTCB/bloc   : ×10 plus de blocs pour même quantité de tokens
  • Ou conserver 21M + Rate-limit global (Option A) si rareté Bitcoin voulue

  Si l'ambition est de couvrir 100% des utilisateurs IA (3.4B) en 10 ans :
  → Il FAUT soit augmenter la supply (×1000 = 21 milliards) soit rate-limiter
  → Avec supply 21M et 0.1% adoption = supply épuisée en < 1 an

  Validation requise par l'utilisateur avant implémentation.
""")
