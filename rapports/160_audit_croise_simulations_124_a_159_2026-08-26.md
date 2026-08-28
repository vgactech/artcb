# Rapport 160 — Audit croisé ligne à ligne des rapports 124 à 159 et de la branche de simulation

**Date :** 2026-08-26  
**Branche lue et à jour :** `cursor/tokenomics-21m-hbp-owner-decay-3fcb`  
**HEAD au moment de l’audit :** `73efd0d` (`Rename conversation chat et simulation to artcb`)  
**Base `main` :** `0edabb6` — les modifications économiques **ne sont pas** sur `main`  
**Commit d’implémentation code :** `25b832f` (`feat: tokenomics 21M coherente (R0=50, 210k) + R(H) HBP OwnerDecay`)  
**Rapports 125–159 ajoutés ensuite** sur la même branche (`25b832f..73efd0d`, +72 387 lignes de dumps de conversation)

**Expertises mobilisées :** audit de protocole, tokenomics, mechanism design, lecture intégrale des dumps 124–159 (72 595 lignes), inventaire du code `src/artcb/economics/` + `chain/manager.py` + `mining/pipeline.py` + identité matérielle, croisement conversationnel (ordre des discussions, pas ordre de création des fichiers).

**Avancement de CETTE tâche (audit) : 100 %**  
**Avancement de la couche économique par rapport à la spec 153–155 / rapport 124 : ~100 % de ce qui a été demandé alors**  
**Avancement de la même couche par rapport à la spec FINALE des rapports 158–159 : ~35–45 %** (math OwnerDecay et binding encore proches ; émission, HBP, settlement, identité, Finder, WorkID : non conformes ou absents)  
**Avancement Finder Q=100 / Mode A-B-C / DDPBA WorkID / HumanID 18+ : 0 % dans le code**  
**535 tests verts ≠ protocole complet** (rapport 156 §19 — confirmé par lecture du code)

**Ordre explicite de cette passe :** relire, recoller l’ordre de conversation, identifier questions / réponses / restes, croiser avec le code. **Aucun patch 158–159 n’a été écrit.** AUTO_PROMPT interdit le développement sans ordre. La spec 159 contredit volontairement D-023 / rapport 124.

---

## 0. Méthode — ce qui a été lu, ce qui n’a pas été inventé

### 0.1 Périmètre lu

| Fichier | Lignes | Nature réelle |
|---------|-------:|---------------|
| `rapports/124_tokenomics_21m_rh_hbp_ownerdecay_2026-08-25.md` | 208 | **Seul vrai rapport d’implémentation Cursor** |
| `rapports/125 conversation chat et simulation artcb.md` … `159 conversation chat et simulation artcb.md` | 72 387 | **Dumps de réponses ChatGPT** (messages utilisateur souvent absents, inférés par « Tu demandes / Tu veux / Tu viens de ») |
| Code `src/artcb/economics/*`, `tokenomics.py`, `chain/manager.py`, `mining/pipeline.py`, `api/economics_routes.py`, `security/hardware_identity.py`, `security/wallet_device_binding.py`, `tests/test_economics_protocol.py` | — | État réel de la branche |

Les dumps **ne sont pas** dans l’ordre de conversation. Tu l’as dit : copier-coller. Ce rapport **reconstruit l’ordre des discussions**, pas l’ordre de création Git.

### 0.2 Doublons binaires (md5 identiques)

| Paire | md5 | Conséquence |
|-------|-----|-------------|
| `140` ≡ `141` | `d8bcaa014d2fd50c7558290c601ebaad` | Un seul document : simulation 365 jours Mode A/B/C |
| `154` ≡ `155` | `a532909629c0d52614934ea2d2e49e52` | Un seul document : audit #2 / spec d’implémentation. `155` n’ajoute rien (typo « conversatin » dans le nom) |

### 0.3 Typos de noms de fichiers (ne pas chercher l’orthographe exacte)

- `127 conversatin chat et simulation artcb.md`
- `136 conversation char et simulation artcb.md`
- `155 conversatin chat et simulation artcb.md`

### 0.4 Corruption / duplicatas internes

- **125** : bloc Market Cap / FDV dupliqué (≈ L745–927 ≈ L930–1113)
- **126** : sections A/B répétées (fichier de 13 126 lignes, plusieurs « Oui. Je lance… » collés)
- **127** : texte tronqué / corrompu vers L1103 (certificat EK)
- **152** : 10 695 lignes = plusieurs chapitres concaténés (simulation + audit GitHub + TPS + Universal Workload + OwnerDecay)
- **159** : 4 300 lignes = **trois sessions ChatGPT collées** dans un seul fichier (reset démographique → taux humain global → audit Cursor vs spec)

### 0.5 Règle de lecture des « verrouillages »

Une phrase « je verrouille » dans un dump **n’est pas** une décision D-xxx du dépôt tant qu’elle n’est pas reprise dans `DECISIONS_UTILISATEUR_ARTCB`.  
À ce jour :

- **D-014** (21 M) : toujours valide
- **D-016** (halving 210 000 blocs) : **codé et acté**, **abandonné dans 158–159** — contradiction documentaire ouverte
- **D-023** (50 / 210k / R(H) / HBP 4.15e9–8.3e9 / P_owner par index) : **codé**, **partiellement caduc** après 158–159

Je ne choisis pas à ta place. Je documente le conflit.

---

## 1. Ordre de conversation reconstitué (pas l’ordre des numéros)

```
FIL PARALLÈLE (hors ARTCB)
  125  éducation crypto générale (wallets, market cap, fraudes) — aucune mention ARTCB

FIL MATÉRIEL
  127  audit TPM Dell Vostro 5481 / EK Nuvoton  (avant la synthèse 126)

FIL FONDATION ARTCB (notes manuscrites 01/08/2026)
  126  synthèse « quelle solution a émergé » + A/B + TPM + rareté humaine
  128  séparer 21 M PoL / reward PoL / Revenue Universel ; R0=1 ; tranches 100k
  129  1 ARTCB ≠ 1 € ; UBI indexé sur prix marché
  130  dividende complémentaire non cumulatif (S-UBI-COMP)
  131  abandon halving pur 1/2^n ; courbe R(S,H) ; valorisation 10 ans (réf. 19/08/2026)
  132  ajout HBP sans supply extra ; 10→60→20 expérimental ; Finder Block
  133  Bitcoin × H : R0=50 ; pas de plancher à 1 ; B = rôle pas statut ; dépôt vgactech/artcb

FIL SÉCURITÉ FINDER (après 133)
  134  Q=100 (100/100, pas 51/100) ; bootstrap Q(H)=min(100,H-1)
  135  capacité Finder Block ; W_i = N·Q·U·C
  136  Architecture A vs B ; simulation combinée 1M→8,3 Md
  137  correction Finders ~20 → ~36 à 1M
  138  bootstrap Genesis ; ~123 782 Finders (ensuite corrigé)
  139  double comptage 70 % ; 70 184 actifs / ~100 263 enregistrés ; Mode A vs B
  140 = 141  simulation 365 jours Mode B + Mode C hybride
  142  calibration Cursor réelle 21–22 août 2026 (55,8 M tokens / 8 runs)
  143  tokens → Useful Work → PoL (η_PoL) ; R(H) déjà sous forme 50·(H/1M)^(-α)
  144  correction DDPBA : pas « 3 pré-blocs par dimension » ; WorkID disjoints
  145  économie DDPBA : Σ Reward(PB_i) = Reward(Block)

FIL TOKENOMICS QUI A PRODUIT LE CODE
  146  JOB PAYMENT ≠ BLOCK REWARD
  147  Job Provider = matière première IA, pas client qui paie le Worker
  148  R0=50 ; 10→60→20 = part HBP de l’enveloppe, fonction de H (pas du temps)
  149  capacité PoL/TX/HBP dynamique (mesure → plan → bloc)
  150  sim 5 users / 6 jobs ; 30/70 Provider/Worker EXPÉRIMENTAL
  151  binding A2→B ; table DISCRÈTE 50/40/30/20/10 (plus tard abandonnée)
  152  méga-simulation + audit GitHub intercalé + Universal Workload
  153  AUDIT #1 dépôt AVANT sim : code = 210 000 ARTCB max, pas 21 M
  154 = 155  AUDIT #2 spec d’implémentation (R(H), HBP 4.15e9/8.3e9, P_owner continu)

IMPLÉMENTATION CURSOR (entre 155 et 156)
  124  code réel sur la branche (25b832f) — D-023

FIL POST-CODE
  156  audit ChatGPT de la branche 25b832f : 535 tests ≠ protocole complet
  157  simulation complète ENCORE sur l’ancien modèle (8,3 Md, taux par machine)
  158  RESET utilisateur : adultes 18+ ; SUPPRIMER calendrier 210k ET vélocité
  159  RESET + taux humain COMMUN P_H(N_A) + 4 corrections Cursor demandées
```

**Conséquence pour lire les fichiers :**  
Si tu lis 124 puis 125, tu sautes **toute** la conversation.  
Si tu lis 159 puis 124, tu prends une spec **plus récente** que le code.  
L’ordre utile pour comprendre « ce qui a été dit puis codé puis invalidé » est exactement la liste ci-dessus.

---

## 2. Fichier par fichier — ce qui a été dit (rôle, pas dump)

### 2.1 Rapport 124 — seul livrable d’implémentation

Ce que Cursor a **réellement** mis dans Git (pas une simulation) :

- `R0=50`, `HALVING_INTERVAL=210_000`, identité `50×210k×2=21M`
- `issued = min(schedule, R(H), remaining)`
- HBP linéaire 10 % → 60 % @ 4,15e9 → 20 % @ 8,3e9
- `P_owner(n)` continu : P(1)=100 %, P(2)=50 %, 38 % @ 1 000, 11,85 % @ 100 000, plancher 10 %
- Binding n≥2, humain distinct ; C1 indépendant de C-sur-A3
- Pré-blocs : somme des rewards = R_block (poids de capacité, pas WorkID)
- Job Provider JSON local (payload string)
- Settlement owner/humain/HBP ; HBP **équiparti** entre humains uniques du bloc
- API `/api/v1/economics/*`
- Mining **sans** champs machine → split PoL legacy 100 %
- Tests : 535 passed, 20 skipped
- Limites honnêtes déjà écrites au §6 du 124 (pipeline, H non on-chain, Job Provider sans virement auto, pas d’UI HBP)

**D-023 actée.** D-014 et D-016 « restaurés ». Le 1/105k des rapports 045/080 déclaré obsolète.

### 2.2 125 — hors sujet ARTCB

Questions (inférées) : 10 blockchains, wallets illimités, fraudes, market cap, premier prix d’un token.  
Aucune formule ARTCB. Ne pas l’utiliser comme spec.

### 2.3 127 — TPM / identité machine (LVX)

Machine réelle : Dell Vostro 5481, serial J1S7KT2, TPM 2.0 Nuvoton NPCT75x, `/dev/tpm0`, certificat EK Nuvoton TPM Root CA 2111 (RSA 2048, 2019–2039).  
Question : un clone Replit peut-il utiliser le wallet ? Réponse : pas si l’identité est ancrée EK/attestation, **pas encore démontré dans ARTCB**.  
Le code `hardware_identity.py` existe (rapport 114) mais **n’est pas branché** sur `economics/settlement.py`.

### 2.4 126 — découverte fondatrice

Idée centrale : pas « une équation Einstein », mais un **système** (humain rare + machine + PoL).  
A/B : machine 2 d’A exige un humain B distinct, payé par le protocole.  
Rejet de 50/50 figé et de 20/80 figé au profit d’une courbe 50 %→10 %.  
Confusion « double supply 21 M + 8 Md humains » **rejetée** → double rareté (S, H).  
Simulations paliers 100 000 ARTCB = 210 paliers.

### 2.5 128 — séparation des supplies

Verrouillé alors : `S_PoL,max=21M` ≠ Revenue Universel.  
R0=**1** ARTCB (ensuite contredit par 133/148).  
Tranches 100k : 100k+50k+25k+… = 200k ≠ 21 M → **impossibilité démontrée**.  
Halving = diminution du **taux**, PoL nécessaires = variable qui **augmente**.

### 2.6 129 — prix

`1 ARTCB = 1 €` **rejeté**. Prix = marché. UBI = budget réel / (H × prix).  
Simulation demandée H × prix (0,01 € → 10 000 €) — **jamais entièrement exécutée comme protocole**.

### 2.7 130 — S-UBI-COMP

`P_i = max(0, D_i - M_i - U_i)` : plus on mine, moins le protocole verse de dividende.  
Ne résout pas le **financement** (5 Md × 1 000 €/mois = 5 000 Md€/mois théorique).

### 2.8 131 — abandon du halving pur comme fonction finale

Halving jusqu’au palier 210 → R ≈ 10⁻⁶³.  
Proposition `R(S,H)=(1-S/21M)^{β(H)}` et `∂R/∂PoL = 0` (PoL n’est pas la variable monétaire).  
Valorisation 10 ans conditionnelle (Bittensor etc.) — **pas une promesse de prix**.

### 2.9 132 — HBP naît

`R_PoL = R_M + R_H` (pas `R_PoL + R_H` : pas d’inflation).  
Hybride 10 %→60 %→20 % testé. Finder Block dynamique. Hmax encore 8,3 Md.

### 2.10 133 — R0 passe à 50 ; plancher à 1 retiré

Halving **piloté par H** (première version : H double → reward ÷ 2).  
50 ARTCB × 5 000 PoL/bloc = 250 000 ARTCB/bloc → 21 M en ~84 blocs : ** explosif**, donc reward est **par bloc**, pas par PoL.  
B = **rôle**, pas caste. UBI artificiel **remis en cause** si A/B redistribue.  
Benchmark dépôt : 533 blocs, 22,6 TPS. « Nonce humain » ouvert. 210k blocs/palier déjà **questionné** (« héritage Bitcoin artificiel »).

### 2.11 134–141 — Q=100 Finder (entierement hors code actuel)

- Mature : 100/100 HumanID distincts, pas 51/100
- États : `INSCRIT → FINDER_PENDING → VERIFIED → MATURED`
- Reward earned dès le travail, **transferable = 0** jusqu’à MATURED
- Bootstrap : premier humain **ne s’auto-vérifie pas** ; tension H0=100 vs Genesis 101
- `P_false = p^Q` sous i.i.d. ; hypergéométrique plus rigoureux
- À 99 % de Finders hostiles, `0.99^100 ≈ 36,6 %` : Q=100 **ne sauve pas** un pool capturé
- Capacité : hypothèse 20 attestations/h × 56,7 % → 272,16/j/Finder
- 8,3 Md, croissance 0,84 %/an → 191 014 nouveaux/j → ~70 185 Finders actifs
- Mode B pur : backlog max ~884k jour 5, rattrapage jour 8, puis sur-capacité ~1000× → **rejeté en régime permanent**
- Mode C hybride recommandé ; 143 préfère Mode A à maturité

**Dans le code aujourd’hui : zéro module Finder, zéro HumanID, zéro MATURED.**

### 2.12 142–143 — tokens Cursor ≠ PoL

8 runs 21–22 août 2026 : **55,8 M tokens**, 104,66 $, moyenne **6,975 M tokens/run**.  
5 000 tokens/jour comme moyenne mondiale = **insuffisant**.  
6,975 M = scénario « agent intensif réel », **pas** moyenne de 8,3 Md humains.  
Chaîne : Tokens → Useful Work → qualité → vérif → PoL. Conversion automatique tokens→récompense **rejetée**.  
R(H) déjà tabulé (50 / 5,73 / 0,657 / 0,075 / 0,010 à 8,3 Md). Conclusion : **R(H) seul ne garantit pas 21 M**.

### 2.13 144–145 — DDPBA

Correction utilisateur : **pas** 3 pré-blocs concurrents par dimension.  
`W = ⊔ W_i`, un WorkID → un seul PreBlock.  
`N_d = ceil(Demand_d / Capacity_PB,d)` indépendamment TX / PoL / HBP.  
**PartitionMap** manquante (pièce essentielle).  
Σ Reward(PB_i) = Reward(Block). 50 ARTCB **par** pré-bloc = inflation cachée, **rejeté**.  
Exemple : 100k TX / 5k cap → 20 PB TX + 10 PB PoL + 4 PB HBP = 34 PB, toujours 50 ARTCB.

**Code actuel :** `preblocks.py` splitte un entier `r_block_satoshi` selon des **poids float**. Pas de WorkID, pas de PartitionMap, pas de dimensions TX/PoL/HBP.

### 2.14 146–151 — acteurs et premières sims chiffrées

- 146 : qui paie le Job ? Réponse : le **block reward**, pas un JobFee commercial (hors scope)
- 147 : Provider apporte le raisonnement IA (ChatGPT/Cursor/Claude) ; n’est pas le client
- 148 : 10→60→20 n’est **pas** Provider/Worker/HBP simultanés ; c’est **HBP(H)**
- 149 : « aujourd’hui 7 000 PoL » comme constante = à abandonner
- 150 : 30 % Provider / 70 % Worker = **paramètre de test**, total 50 ARTCB
- 151 : A2 liée à B ; table 50/40/30/20/10 encore utilisée ; B=19,482143 demandé « pourquoi »

### 2.15 152 — consolidation avant code

Confusion récurrente corrigée : « A possède A2 donc A prend tout, B n’a que du HBP » = **faux**.  
B sur A2 = **human binding** + éventuellement Provider + HBP.  
« B=50 %, C=40 %, D=30 % parce que ce sont des humains différents » = **faux** (c’est l’index machine d’A).  
« B déjà bénéficiaire ⇒ B ne peut plus être propriétaire » = **faux** (C1 indépendant).  
TPS 22,6 ≠ ARTCB = consensus de Bitcoin.  
Universal Workload / bridges : texte IR, pas règlement.

### 2.16 153 — audit #1 (ce que Cursor a dû corriger en premier)

```
Code main alors :
  INITIAL_BLOCK_REWARD_ARTCB = 1
  HALVING_INTERVAL = 105_000
  1 × 105_000 × 2 = 210_000 ARTCB   ≠ 21_000_000
```

Simulation A = code. Simulation B = 50 / 210k → 21 M.  
Settlement discret A/B/C/D à 100 M humains (A3=40/60).

### 2.17 154=155 — spec que le rapport 124 a implémentée

Trois fonctions simultanées :

1. `R_block = R(H)` (encore combiné au calendrier dans le code)
2. `HBP(H): 10 % → 60 % @ 4,15e9 → 20 % @ 8,3e9`
3. `P_owner(1)=100 %, P_owner(n≥2): 50 % → 10 % continu`

Binding n≥2, pré-blocs conservatifs, Job Provider.  
Paliers 50/40/30/20/10 **abandonnés pour le protocole**.  
Calibration 38 % @ 1k et 11,85 % @ 100k.

### 2.18 156 — audit post-code (ChatGPT lit 25b832f)

Certifie : 21 M cohérents, R(H), HBP, binding, conservation.  
**Refuse** de certifier « protocole complet ».  
Demandes de correction déjà : dynamic halving, HumanProof, TPM dans settlement, biométrie, WorkID, Job Provider incomplet, HBP non pondéré Finder, **EconomicRoot hors du hash de bloc**.

### 2.19 157 — simulation encore sur le modèle pré-pivot

Ledger 50 ARTCB A/B/C/D avec taux **par machine**.  
HBP encore 8,3 / 4,15 Md.  
Dynamic halving **exclu de la sim** mais encore dans le code.  
§28 : Provider %, Finder weights, EconomicRoot **non verrouillés**.

### 2.20 158 — premier reset utilisateur

- Unité = adultes, pas 8,3 Md total
- **Calendrier de blocs SUPPRIMÉ**
- **Dynamic halving SUPPRIMÉ**
- OwnerDecay continu, pas 50/40/30/20/10, pas de cap 100k machines
- Interprétation OwnerDecay encore **partiellement par machine** (corrigée en 159)
- Contradiction numérique 49,01 / 49,02 / 49,03 (A remonterait) — à rejeter

### 2.21 159 — spec finale actuelle de la conversation (pas du code)

Trois sessions dans un fichier :

1. Reset 8,3 / 4,15 / calendrier / vélocité
2. **Pivot : P_H(N_A) identique pour TOUS les humains liés à A**
3. Audit : 4 patches Cursor demandés

Formule HBP proposée (ChatGPT, **pas votée D-xxx**) :

```
x = H_adult / H_adult,max
P_HBP = 10% + 100x     si 0 ≤ x ≤ 0.5     → pic 60 % à x=0.5
P_HBP = 100% - 80x     si 0.5 < x ≤ 1     → 20 % à x=1
```

`H_adult,max ≈ 5,82 Md` = **estimation de travail**, définition 18+ ONU WPP **verrouillée**, chiffre **non**.  
Pic HBP provisoire ≈ 2,91 Md.

Émission cible :

```
R_block = min(R(H_adult), remaining_21M)
```

plus de `schedule`, plus de `extra_epochs`.

Settlement cible : `P_A(N_A)` et `P_H(N_A)` appliqués à **toutes** les machines de A pour les règlements **futurs**. Historique non réécrit.

---

## 3. Catalogue des questions — posées, répondues, restantes

Légende : **R** = réponse donnée à un moment (peut avoir été invalidée ensuite) · **O** = encore ouverte · **INV** = invalidée par un tour ultérieur · **CODE** = tranchée seulement dans le code 124, pas dans 159.

### 3.1 Questions de cadrage / éducation (125)

| # | Question | Statut |
|---|----------|--------|
| Q125.1 | Combien de wallets / coins / tx par jour sur les 10 blockchains ? | **R** (illimité on-chain, limites CEX/KYC) — hors ARTCB |
| Q125.2 | Qui fixe le premier prix d’un token ? Market cap vs FDV ? | **R** — marché, pas protocole |

### 3.2 Identité / TPM (126–127)

| # | Question | Statut |
|---|----------|--------|
| Q127.1 | Clone Replit ⇒ vol du wallet ? | **R** partielle : seed serveur ≠ TPM ; attestation distante **non démontrée** |
| Q126.1 | 1 matériel → 1 wallet suffisant anti-Sybil humain ? | **R** : non (1 TPM ≠ 1 humain) |
| Q126.2 | Biométrie = clé privée ? | **R** : **non** (irréversible) — verrouillé |
| Q126.3 | Inscription dès la naissance ? | **O** (nouveau-né sans authenticator) |
| Q126.4 | Preuve de personhood exacte (ZK, vendor, liveness) ? | **O** |

### 3.3 Supply / émission

| # | Question | Statut |
|---|----------|--------|
| Q128.1 | Comment 21 M avec tranches 100k qui halvent ? | **R** puis **INV** : 100k+50k+…=200k impossible |
| Q128.2 | R0 = 1 ARTCB ? | **R** (128–132) puis **INV** (133/148 → 50) |
| Q131.1 | Halving 1/2^n comme fonction finale ? | **INV** ( palier 210 microscopique) |
| Q131.2 | PoL dans R(S,H,Q) ? | **INV** : ∂R/∂PoL=0 |
| Q133.1 | R0=50, halving quand H double ? | **R** sim puis **INV** (forme puissance α=ln50/ln64) |
| Q133.2 | Plancher à 1 ARTCB ? | **INV** (50→1→0,99→…) |
| Q133.3 | 210 000 blocs/palier garder ? | **R** dans 153–155/124/D-016 puis **INV** en 158–159 |
| Q148.1 | Reward 1 ou 50 ? | **R** : 50 |
| Q153.1 | Le code atteint-il 21 M ? | **R** : non (210k) — corrigé 124 |
| Q156.1 | Reliquat ~0,023 ARTCB : accepter <21 M ou dernier bloc absorbe ? | **O** |
| Q158.1 | Le calendrier de blocs reste-t-il ? | **R 158–159 : non** · **CODE : encore oui** |
| Q158.2 | Dynamic halving vélocité ? | **R 158–159 : supprimer** · **CODE : encore actif** |
| Q159.1 | H0=1M et R(64M)=1 restent-ils en unité adultes ? | **O** |
| Q159.2 | Date d’épuisement des 21 M sans calendrier ? | **R** : plus fixe, dépend de H(t) |

### 3.4 H / démographie / HBP

| # | Question | Statut |
|---|----------|--------|
| Q132.1 | HBP sans inflation ? | **R** : R_PoL = R_M + R_H |
| Q132.2 | HBP décroissant, croissant ou 10→60→20 ? | **R** : 10→60→20 (trajectoire) |
| Q148.2 | 10→60→20 = trois pools Provider/Worker/HBP ? | **INV** : c’est HBP(H) seul |
| Q148.3 | Plus d’humains ⇒ plus d’ARTCB créés ? | **INV** |
| Q158.3 | 8,3 Md comme Hmax ? | **INV** (population totale) |
| Q158.4 | 4,15 Md comme pic HBP ? | **INV** (moitié de 8,3) |
| Q159.3 | Unité = 18+ ONU WPP ? | **R définition : oui** · **chiffre : non** (5,82 Md provisoire) |
| Q159.4 | H_adult,max gelé au genesis ou mis à jour ? | **O** (oublié) |
| Q156.2 | HBP à H=0 (5 ARTCB) sans bénéficiaire ? | **O** (burn / trésor / interdire bloc) |
| Q156.3 | HBP équiparti vs pondéré Finder (W_i) ? | **O** · **CODE : équiparti** |

### 3.5 OwnerDecay / A-B-C-D

| # | Question | Statut |
|---|----------|--------|
| Q126.5 | Machine 2 d’A sans humain B ? | **R** : interdit |
| Q128.3 | B payé via A ou par le protocole ? | **R** : protocole → B |
| Q133.4 | B = statut inférieur permanent ? | **INV** : B = rôle, C1 possible |
| Q151.1 | A2 = deuxième instance économique de A (A prend 100 %) ? | **INV** |
| Q152.1 | B=50 C=40 D=30 parce que humains différents ? | **INV** |
| Q152.2 | Table 50/40/30/20/10 protocole ? | **INV** (154 : continu) |
| Q152.3 | 100 000 machines = cap protocolaire / 10 % exact ? | **INV** (158 : asymptote, pas cap) |
| Q154.1 | P(1)=100, P(2)=50, 38%@1k, 11,85%@100k ? | **R** pour 124 · **O** si voté définitif après 159 |
| Q158.5 | Taux historique figé par machine au settlement ? | **INV** 159 : taux courant N_A |
| Q159.5 | Tous les humains liés à A ont le même % ? | **R 159 : oui** · **CODE : non** (index) |
| Q159.6 | M1 reste 100 % après M2+ ? | **O — contradiction 159** (texte M1=100 % vs exemple P(5) sur 5 machines) |
| Q159.7 | Un humain peut-il binder des machines de **plusieurs** owners ? | **O** |
| Q159.8 | Vente / retrait de machine ⇒ N_A diminue ? | **O** |
| Q159.9 | Binding rompu (B part) ? | **O** |

### 3.6 Job Provider / pré-blocs / WorkID

| # | Question | Statut |
|---|----------|--------|
| Q146.1 | Qui paie le Job du mineur ? | **R** : block reward (pas JobFee) |
| Q147.1 | Parts Provider / Worker / HBP ? | **O** (30/70, 20/60/20, score = tests) |
| Q144.1 | 3 pré-blocs concurrents par dimension ? | **INV** → DDPBA disjoint |
| Q145.1 | N_PB × R_block ? | **INV** → somme = R_block |
| Q149.1 | Capacité PoL/TX/HBP fixe (ex. 7 000) ? | **INV** → dynamique |
| Q156.4 | PartitionMap / WorkID on-chain ? | **O** · **CODE : absent** |
| Q150.1 | Formule TX fee ? | **O** |

### 3.7 Finder Q=100 (134–141)

| # | Question | Statut |
|---|----------|--------|
| Q134.1 | Q=100 obligatoire 100/100 ? | **R** dans la conversation · **CODE : 0 %** |
| Q134.2 | Genesis auto-vérifié ? | **INV** |
| Q138.1 | H0=100 vs cohorte Genesis 101 ? | **O** |
| Q140.1 | Mode A, B ou C ? | **R tendance : C bootstrap / A maturité** · pas D-xxx |
| Q134.3 | Durée challenge period avant MATURED ? | **O** |
| Q134.4 | Finder_maturity > T, T= ? | **O** |

### 3.8 Consensus / hash / mining

| # | Question | Statut |
|---|----------|--------|
| Q156.5 | EconomicRoot dans le block hash ? | **O** · **CODE : hash = index/ts/prev/graph/merkle/pol seulement** |
| Q133.5 | PoL+nonce vs PoL only difficulty ? | **O** |
| Q133.6 | Unité « Wailly » de travail ? | **O** |
| Q124.1 | Pipeline mining attache machine_index ? | **R 124 §6 : pas encore** — toujours vrai |

### 3.9 UBI (128–131 vs 133)

| # | Question | Statut |
|---|----------|--------|
| Q128.4 | Supply UBI séparé des 21 M ? | **R** puis **affaibli** en 133 (émergent via A/B+HBP) |
| Q129.1 | Oracle de prix pour UBI ? | **O** |
| Q130.1 | D (objectif €/mois) = ? | **O** |

**Aucune de ces questions UBI n’est dans le code economics.**

---

## 4. Ce qui a été simulé (chiffres à ne pas reconfondre)

Les tables ci-dessous ont **toutes existé** dans les dumps. Beaucoup sont **obsolètes** pour la spec 159. Je les range par génération.

### 4.1 Génération « code cassé » (153 Simulation A) — historique

`R0=1`, `H=105k` → plafond **210 000 ARTCB**. 1 an = 52 596 ARTCB. 100 ans ≈ 210 000.

### 4.2 Génération « Bitcoin-like 50/210k » (153 B + 124) — **CODÉE**

| Horizon (600 s/bloc, H≤1M, pas de R(H) ni vélocité) | Supply |
|--:|--:|
| 1 an (52 596 blocs) | 2 629 800 |
| 5 ans | 11 824 500 |
| 10 ans | 17 074 500 |
| 20 ans | 20 346 750 |
| 100 ans | ≈ 21 000 000 |

Poussière satoshi `>> k` : ~0,023 ARTCB sous le cap. Test `test_asymptotic_schedule_hits_hard_cap`.

**159 dit : ce calendrier n’est plus le modèle**, seulement un outil de sim historique. 21 M reste le hard cap.

### 4.3 R(H) — **stable depuis 143/154, encore dans le code**

`α = ln(50)/ln(64) ≈ 0,94064`  
`R = 50 × (max(H,1e6)/1e6)^(-α)`

| H | R(H) |
|--:|--:|
| ≤ 1 M | 50 |
| 10 M | 5,7323 |
| 64 M | 1,0000 |
| 100 M | 0,6572 |
| 1 Md | 0,07534 |
| 8,3 Md (ancien Hmax) | ≈ 0,01029 |

Pas de plancher à 1. **Ancres H0 et 64M non revalidées en adultes 18+.**

### 4.4 HBP génération 154/124 — **CODÉE, caduque selon 159**

| H | HBP code |
|--:|--:|
| 0 | 10 % |
| 100 M | 11,2048 % |
| 1 Md | 22,048 % |
| 4,15e9 | 60 % |
| 8,3e9 | 20 % |

### 4.5 HBP génération 159 — **NON CODÉE**, H_adult,max≈5,82 Md provisoire

| H adultes | R | HBP | Pool HBP | Travail |
|--:|--:|--:|--:|--:|
| 0 | 50 | 10 % | 5,00 | 45,00 |
| 1 M | 50 | 10,02 % | 5,009 | 44,991 |
| 1 Md | 0,07534 | ≈27,2 % | 0,0205 | 0,0548 |
| 2,91 Md | ≈0,0276 | **60 %** | ≈0,0166 | ≈0,0110 |
| 5,82 Md | ≈0,0144 | **20 %** | ≈0,00287 | ≈0,0115 |

Blocs pour 21 M si H constant : 420 000 (H≤1M) … ≈ 1,46 Md blocs (H=5,82 Md).

### 4.6 OwnerDecay continu Cursor (τ≈2733,93, β≈0,84079) — **CODÉ, math OK, usage settlement NON conforme 159**

| n | P_owner code |
|--:|--:|
| 1 | 100 % |
| 2 | 50 % |
| 3 | 49,948 % |
| 1 000 | 38 % exact |
| 10 000 | 20,06 % |
| 100 000 | 11,85 % exact |
| ∞ | 10 % |

### 4.7 Settlement 100 M humains, R=50, 4 machines — **deux tables**

**Discret 153 (A3=40/60) — abandonné :** A=22,4895 · B=6,9503 · C=8,0602 · D=12,5000  
**Continu 124 (A3≈49,948 %) — CODÉ :** A=23,5937 · B=6,9503 · C=6,9560 · D=12,5000  

Les deux somment à 50. L’écart A/C vient uniquement d’A3.

**159 N_A=5 taux commun (NON CODÉ) :** A≈22,44 · chaque humain ≈4,51 — **autre architecture**.

### 4.8 150 — 30/70 Provider/Worker (expérimental, NON verrouillé)

U1 7,425 · U2 11,025 · U3 15,750 · U4 10,800 · U5–U7 HBP 5,000 · total 50.

### 4.9 151 — A2→B (HBP 50 %, 25/25) — génération mixte, ne pas réutiliser comme spec

A=8,732 · B=19,482 · C=18,214 · D=3,571.

### 4.10 Finder (134–141) — simulations capacité, **zéro code**

Q=100, 70 185 Finders actifs @ 8,3 Md sous 20 attestations/h.  
Mode B 365 j : backlog 883 777 j5, 0 j8.  
`W=113` → A 88,50 % / B 8,85 % / C 2,65 % d’un pool Finder.

### 4.11 Tokens (142–143)

55,8 M tokens / 8 runs. 600 M actifs × 6,975 M = 4,185 P tokens/jour (scénario extrême agent, pas moyenne mondiale).

---

## 5. Timeline des règles : ce qui est resté, ce qui a été cassé, ce qui est final conversation

### 5.1 Invariants qui ont survécu 126 → 159

1. Hard cap **21 000 000 ARTCB** (D-014)
2. 1 ARTCB = 10^8 satoshi
3. Conservation : somme des legs = R_block (aucune création par pré-bloc)
4. H (humains) et n_A (machines d’un owner) sont **deux index distincts**
5. Machine 1 seule : pas d’humain tiers obligatoire
6. Machine n≥2 : humain distinct obligatoire, ≠ owner, ≠ déjà liés chez le même owner
7. C1 indépendant de « C est bound sur A3 »
8. B payé par le protocole, pas par A
9. HBP est un **split** de R, pas une deuxième émission
10. PoL ≠ UBI comme deuxième supply obligatoire (UBI jamais codé)
11. 1 ARTCB ≠ 1 €
12. Biométrie brute **interdit** on-chain
13. P_owner → 10 % asymptotique, pas un saut à n=100 000

### 5.2 Abandonnés (ne plus réimplémenter comme « le » protocole)

| Abandon | Où | Remplacé par |
|---------|-----|--------------|
| Enveloppes 100k→50k→25k sommant à 21 M | 128 | (puis calendrier 210k, puis R(H) seul) |
| R0=1 comme ancre finale | 128–132 | R0=50 |
| Halving pur jusqu’au palier 210 | 131 | R(H) |
| Plancher R=1 | 133 | décroissance continue |
| UBI 500/1000 € garanti comme règle | 129–130 | ouvert / dé-priorisé |
| 50/40/30/20/10 | 151–153 | courbe continue |
| 8,3 Md = Hmax ARTCB | 158–159 | H_adult,max 18+ |
| 4,15 Md = pic HBP | 158–159 | ≈ 50 % × H_adult,max |
| 210 000 blocs comme décroissance | 158–159 | **supprimé** |
| `50×210k×2=21M` comme **justification d’émission** | 159 | 21 M = cap seulement |
| extra_epochs / velocity 144 blocs/j | 158–159 | **supprimé** |
| 100 000 = cap machines | 158 | point de courbe |
| Taux settlement figé à l’index de création | 159 | N_A courant |
| Taux humain différent B≠C≠D | 159 | P_H(N_A) commun |
| 3 PB concurrents / 50 ARTCB par PB | 144–145 | DDPBA + somme = R |
| Quorum Finder 51/100 | 134 | 100/100 (spec, pas code) |
| Mode B pur permanent | 140 | C puis A |
| Tokens → reward automatique | 143 | Useful Work |

### 5.3 Encore dans le code alors que 159 les a tués

1. `schedule_reward_satoshi` + `HALVING_INTERVAL=210_000`
2. `issued_reward_satoshi = min(schedule, R(H), remaining)`
3. `ChainManager._compute_dynamic_epoch` / `extra_epochs`
4. `HBP_PEAK_HUMANS=4_150_000_000`, `HBP_END_HUMANS=8_300_000_000`
5. `settle_block` → `owner_share(machine.machine_index)`
6. HBP `{human: 1.0}` équiparti, owners inclus dans le pool HBP
7. `verified_humans: float` générique (pas 18+, pas preuve)
8. Tests T-E01/T-E02 qui **figent** 210k et le split par index
9. `DECISIONS` D-016 et D-023
10. `TOKENOMICS_ARTCB` §4.1 calendrier 10 min / 210k
11. Commentaire AI routes `src/api/ai_routes.py` (50 >> epoch_fixe+epoch_dyn)
12. `scripts/mine_learning_simple.py` : `INITIAL >> (index // HALVING)` **sans R(H)**

---

## 6. Inventaire code — module par module, fonction par fonction

Légende statut vs **spec 159** (conversation finale) :  
**OK-159** conforme · **MATH-OK USAGE-KO** formule bonne, branchement faux · **KO-159** contraire · **ABSENT** · **HORS-SPEC** (existe, pas demandé comme règle ARTCB 159) · **LEGACY** (pré-124, non recâblé)

### 6.1 `src/artcb/tokenomics.py` — source unique des constantes

| Symbole / fait | Valeur actuelle | vs 159 |
|----------------|-----------------|--------|
| `SATOSHI_PER_ARTCB` | 100_000_000 | OK-159 |
| `INITIAL_BLOCK_REWARD_ARTCB` | 50.0 | OK-159 (R0) |
| `HALVING_INTERVAL` | 210_000 | **KO-159** (abandonné) |
| `MAX_HALVINGS` | 64 | HORS-SPEC (sert le calendrier) |
| `MAX_SUPPLY_ARTCB` | 21_000_000 | OK-159 |
| `VELOCITY_REFERENCE` | 144 | **KO-159** |
| `VELOCITY_WINDOW_SECONDS` | 86_400 | **KO-159** |
| Commentaire D-016 / D-023 | présent | **documentairement caduc vs 159** |

### 6.2 `src/artcb/economics/emission.py`

| Fonction | Lignes | Fait | vs 159 |
|----------|-------:|------|--------|
| `population_reward_artcb(H)` | 39–55 | R(H) puissance, clamp H≥1e6, pas de floor 1 | MATH-OK ; H n’est pas H_adult prouvé |
| `schedule_reward_satoshi(index, extra_epochs)` | 58–67 | `R0 >> (index//210k + extra)` | **KO-159** |
| `issued_reward_satoshi(...)` | 70–98 | min(schedule, R(H), remaining) | **KO-159** doit être min(R(H_adult), remaining) |
| `asymptotic_schedule_supply_satoshi` | 101–115 | somme epochs jusqu’au cap | HORS-SPEC 159 |
| `cumulative_schedule_artcb` | 118–133 | table 600 s/bloc | HORS-SPEC 159 |
| constantes `H_REF`, `REWARD_POPULATION_ALPHA` | 34–36 | 1e6, ln50/ln64 | OK-math ; ancre 64M **O** |

### 6.3 `src/artcb/economics/hbp.py`

| Symbole / fonction | Valeur | vs 159 |
|--------------------|--------|--------|
| `HBP_START/PEAK/END` | 0.10 / 0.60 / 0.20 | trajectoire OK |
| `HBP_PEAK_HUMANS` | 4_150_000_000 | **KO-159** |
| `HBP_END_HUMANS` | 8_300_000_000 | **KO-159** |
| `hbp_rate(H)` | linéaire 2 segments | forme OK, **bornes KO** |

Manque : `x = H_adult/H_adult,max` ; gel/ maj de H_adult,max ; source ONU datée.

### 6.4 `src/artcb/economics/owner_decay.py`

| Fonction | Fait | vs 159 |
|----------|------|--------|
| `_fit_tau_beta` | ancre 38 % et 11,85 % exactes à l’import | MATH-OK (159 réutilise la courbe Cursor) |
| `owner_share(n)` | P(1)=1, n≥2 formule Hill | MATH-OK **si n = N_A courant**, KO si n = index de la machine |
| `human_share(n)` | 1 - P | idem |

**Le bug 159 n’est pas τ,β. C’est settlement qui passe `machine_index` au lieu de `N_A`.**

### 6.5 `src/artcb/economics/human_binding.py`

| Élément | Fait | vs 159 |
|---------|------|--------|
| `MachineRecord` | id, owner, index, bound_human, fingerprint optionnel | structure OK ; pas HumanID, pas âge 18+, pas TPM obligatoire |
| `MachineRegistry.register` | index auto 1-based / owner ; n=1 refuse humain tiers ; n≥2 exige distinct | **OK-159** pour la règle de binding |
| `next_index` | max+1 | OK ; **pas de decrement** si machine retirée (**O**) |
| `verified_human_addresses` | owners ∪ bounds | **n’est pas** H_adult réseau (pas de preuve) |
| Persistance | JSON `data/economics/machines.json` | stub, pas consensus |

Manque : un humain bindé chez A **et** owner chez C (autorisé en sim, pas testé comme règle multi-owner côté humain). `device_fingerprint` optionnel, jamais vérifié contre `hardware_identity`.

### 6.6 `src/artcb/economics/preblocks.py`

| Fonction | Fait | vs 144–145 / 159 |
|----------|------|------------------|
| `normalize_weights` | poids ≥0, somme >0 | OK conservation |
| `partition_block_reward` | largest-remainder, somme = R | conservation **OK** |
| WorkID / PartitionMap / dimensions TX-PoL-HBP | **ABSENT** | **KO DDPBA** |
| Plafond N_max anti-explosion micro-PB | **ABSENT** | **O** |

### 6.7 `src/artcb/economics/job_provider.py`

| Méthode | Fait | vs spec Job→PoL→settle |
|---------|------|------------------------|
| `submit(provider, payload: str)` | status=submitted | payload **string**, pas graphe IR / prompt canonique |
| `measure_capacity` | somme capacités | OK local |
| `partition` | appelle preblocks | pas de WorkIDs |
| `mark_settled` | partitioned → settled | **pas d’API HTTP** pour settle ; **pas de virement wallet** |
| R_Provider dans settlement | **ABSENT** | **O** (grosse inconnue 159 §29) |

Cycle complet demandé 154 : Prompt → IA → Job → WorkPool → PB → Worker → PoL → Validation → Block → Wallets : **tronqué après JSON**.

### 6.8 `src/artcb/economics/settlement.py`

| Élément | Fait | vs 159 |
|---------|------|--------|
| `MachineContribution` | machine_id, owner, index, bound_human, work_weight | manque N_A, HumanID, DeviceID, WorkID |
| `settle_block` | HBP pool + work pool | OK split 2 pools |
| n=1 | 100 % owner, ignore bound | OK si N_A=1 ; **KO si N_A≥2** selon exemple 159 §27 |
| n≥2 | `owner_share(index)` / `human_share(index)` | **KO-159** (devrait être P(N_A) pour toutes) |
| humain manquant n≥2 | ValueError | OK |
| HBP | unique(owner ∪ bound), poids 1.0 | **KO** Finder-weighted ; **inclut les owners** comme « humains HBP » |
| HBP>0 et liste vide | ValueError | ne couvre pas genesis H=0 sans machines |
| conservation satoshi | RuntimeError si ≠ | OK |

### 6.9 `src/artcb/economics/satoshi.py`

| Fonction | Fait | vs spec |
|----------|------|---------|
| `allocate_satoshi` | largest remainder, somme exacte | OK (utilisé partout) |
| `artcb_to_satoshi` | round half-up | OK |
| `satoshi_to_artcb` | / 1e8 | OK |

### 6.10 API `src/api/economics_routes.py`

| Route | Fonction | Écart |
|-------|----------|-------|
| `GET /params` | expose 210k + HBP 4.15e9/8.3e9 | **documente le modèle 124, pas 159** |
| `GET /emission` | `issued_reward_satoshi` + `extra_epochs` query | KO-159 |
| `GET /hbp` | `hbp_rate` | bornes KO |
| `GET /owner-share?machine_index=` | P(n) par index | sémantique KO si on voulait N_A |
| `POST /settle` | preview `settle_block` | même bug index |
| `POST /preblocks/partition` | poids | pas WorkID |
| `POST /machines` | `MachineRegistry.register` | pas TPM/HumanID |
| `GET /machines/{owner}` | liste | OK stub |
| `POST /jobs` | submit | OK stub |
| `POST /jobs/{id}/partition` | partition | pas `mark_settled` HTTP |

Pas de route : Finder, HumanID, EconomicRoot, H_adult oracle, Provider share.

### 6.11 `src/api/deps.py`

`MachineRegistry(data/economics/machines.json)` + `JobProvider(data/economics/jobs.json)` instanciés au boot.  
**Pas** de `DeviceIdentityStore` branché sur register_machine.

### 6.12 `src/artcb/chain/manager.py`

| Méthode | Fait | vs 156/159 |
|---------|------|------------|
| `append_block` | calcule reward, settle si tous ont `machine_index`+`owner_address`, sinon PoL 100 % | mining actuel → **toujours legacy** |
| `_calculate_block_reward` | `issued_reward_satoshi` + `epoch_dyn` | **KO-159** |
| `_compute_dynamic_epoch` | log2(velocity/144) | **KO-159** |
| `_issued_so_far_satoshi` | somme `block_reward` | OK cap |
| `ffi.build_block_hash(index, ts, prev, graph, merkle, pol)` **avant** d’écrire economics/contributors | hash **ignore** settlement | **bug protocole 156 §14** |
| `ChainBlock.economics` | dict optionnel JSON | présent mais **non haché** |
| `_machine_contributions` | None si un contributeur sans champs machine | mélange = 100 % PoL **sans HBP** |

### 6.13 `src/artcb/chain/ffi.py`

`build_block_hash` : 6 champs. Pour EconomicRoot il faudrait étendre le canonique C (`artcb_build_canonical`) — **changement consensus**.

### 6.14 `src/artcb/mining/pipeline.py`

`build_contributors` : address, pol_score, signature, role (`learner`/`reasoner`).  
**Aucun** `machine_id`, `machine_index`, `owner_address`, `bound_human_address`.  
Donc **tout bloc miné par le pipeline réel contourne HBP et OwnerDecay**.

### 6.15 Identité matérielle — existe, **non branchée economics**

`hardware_identity.py` : `DeviceIdentity`, `_read_machine_id`, `_read_tpm_ek_cert`, `compute_device_fingerprint`, `collect_device_identity`, `DeviceIdentityStore`.  
`wallet_device_binding.py` : **1 wallet / fingerprint** (anti multi-wallet sur la même machine).  

**Tension non spécifiée :** 1 wallet/device **vs** un owner A avec N machines (N wallets ? N devices ? 1 wallet A + N MachineID ?). Tu ne l’as pas tranché. Le binding wallet actuel **empêche** plusieurs wallets sur un PC, ce qui n’est pas la même règle que « N machines / owner ».

### 6.16 Sécurité déjà là (LEGACY, pas Finder)

Anti-Sybil + slashing sur contributeurs PoL. **Ce n’est pas** Q=100 HumanID. Ne pas les confondre.

### 6.17 Tests `tests/test_economics_protocol.py`

| Classe | Ce qu’elle fige | Risque 159 |
|--------|-----------------|------------|
| `TestEmissionIdentity` | 50×210k×2, table 600 s, epoch 210k→25 ARTCB | **cassera** si on applique 159 |
| `TestPopulationReward` | ancres R(H) | plutôt stable |
| `TestHBP` | 4.15e9 / 8.3e9 | **cassera** |
| `TestOwnerDecay` | P(n) par n | math ok ; sémantique settlement non testée N_A |
| `TestHumanBinding` | n≥2, C1 | OK |
| `TestPreblocks` | conservation | OK mais insuffisant DDPBA |
| `TestJobProvider` | submit/partition/settle JSON | OK stub |
| `TestSettlementABCD` | table 23,5937… par **index** | **cassera** si taux commun |
| `TestChainIntegration` | 50 ARTCB + settle on-chain | partiel |
| `TestEconomicsAPI` | /params /settle | documente 124 |

**535 verts valident le modèle 124, pas le modèle 159.**

### 6.18 Frontend / genesis / scripts

- `frontend/.../ChainPage.tsx` : fallback affichage 50 ARTCB — cosmétique
- `scripts/init_genesis.py` : genesis v3.0, 50, 210k — **KO-159** sur l’intervalle
- `scripts/simulate_economics.py` : replay modèle 124
- `scripts/mine_learning_simple.py` : halving index **sans** R(H) ni settlement
- Bridges BTC/ETH/SOL/… → `ir_text` : **pas** dans `settle_block` (156 §15)

### 6.19 Modules **entièrement absents** (simules, 0 fichier)

| Module conversation | Rapports | Code |
|---------------------|----------|------|
| HumanID + âge 18+ + liveness + nullifier ZK | 126, 134, 156, 159 | ABSENT |
| Finder protocol Q=100, états PENDING/VERIFIED/MATURED | 134–141 | ABSENT |
| RandomFinderSelection / VRF | 134 | ABSENT |
| Finder Block dynamique B_F(t) | 135 | ABSENT |
| Mode A/B/C onboarding | 136–141 | ABSENT |
| WorkID + PartitionMap + Used(WorkID) | 144–145 | ABSENT |
| EconomicRoot / Merkle settlement dans le hash | 156–157 | ABSENT |
| Oracle H_adult (WPP) | 159 | ABSENT |
| Provider pool dans settle_block | 147–150, 159 | ABSENT |
| UBI / S-UBI-COMP | 128–130 | ABSENT |
| TX fee formula | 150 | ABSENT |
| Nonce humain / difficulté PoL+nonce | 133 | ABSENT |

---

## 7. Point par point — inclus dans la branche vs manquant

### 7.1 Inclus (commit `25b832f` et suivants docs)

1. Restaurer 21 M atteignable via 50 × 210k × 2 (contre le bug 1×105k)
2. R(H) sans floor 1
3. HBP 10-60-20 sur bornes 4.15e9 / 8.3e9
4. OwnerDecay continu calibré 38 % / 11,85 %
5. Binding n≥2 + C1 indépendant
6. Conservation satoshi (allocate + settle + preblocks)
7. API preview economics
8. Branchement optionnel `append_block` si champs machine
9. Tests T-E01–E03, 535 passed
10. Docs TOKENOMICS / AUTO_PROMPT (état 124) / D-023 / LISTE_TESTS
11. Dumps 125–159 **stockés** sur la branche (mémoire de conversation, pas du code exécutable)
12. Identité matérielle **préexistante** (rapport 114), non recâblée
13. Pipeline mining / PoL / wallets / PQC / groupes : inchangés

### 7.2 Manquant par rapport à 153–155 **déjà au moment du code** (124 §6 + 156)

1. Mining n’envoie pas les champs machine
2. H n’est pas un compteur vérifié
3. Job Provider ne paie pas on-chain
4. Pas d’UI HBP
5. HumanProof réel
6. TPM/EK dans settlement
7. Wallet↔machine crypto imposé au settle (distinct du 1-wallet-per-device)
8. WorkID disjoints
9. HBP pondéré Finder
10. EconomicRoot dans le hash
11. Universal Workload dans le règlement
12. Décision reliquat 0,023 ARTCB

### 7.3 Manquant **supplémentaire** après 158–159 (nouveau delta)

1. Retirer schedule 210k de l’émission
2. Retirer extra_epochs / velocity
3. Remplacer HBP anchors par H_adult / H_adult,max
4. Extraire WPP 18+ (pas 5,82 Md inventé dans le code)
5. Settlement `P(N_A)` commun, y compris politique M1
6. Genesis HBP sans humains
7. Recalibrer ou confirmer α, H0, point R=1
8. Mettre à jour D-016 / D-023 / TOKENOMICS / tests pour ne plus figer 210k
9. Tout le fil Finder 134–141
10. DDPBA 144–145
11. Tranchage Provider %

### 7.4 Inclus dans les dumps mais **volontairement pas du protocole** (ne pas coder sans GO)

- Valorisation prix 90–100 € (131) — scénario, pas règle
- 30/70 et 20/60/20 Provider
- Pondération Finder 100:50:25 (157)
- 5 000 WorkItems/PB (illustratif)
- 20 attestations Finder / heure
- Mode B croissance 3,7216× par jour
- S-UBI-COMP
- Analogie E=mc² (126, rejetée)

---

## 8. Ce que tu aurais oublié de préciser (liste opérationnelle)

Sans ces réponses, un agent **ne doit pas inventer** le patch 159.

### 8.1 OwnerDecay — le trou le plus dangereux

1. **M1 après M2+** : reste 100 % pour toujours, ou entre dans P(N_A) comme les autres ?  
   159 dit les deux à des endroits différents. L’exemple §27 applique P(5) aux **5** machines.
2. Si M1 entre dans P(N_A), A est-il **pénalisé sur sa première machine** dès qu’il aide B ? (incitation inverse possible)
3. Le taux s’applique-t-il aux machines d’A **absentes du bloc courant** (pas de travail ce bloc) ?  
   Si non : un owner peut miner seulement M1 pour garder 100 %.
4. N_A = machines **enregistrées** ou machines **actives/attestées** ce bloc ?
5. N_A peut-il **baisser** (vente, mort machine, unbinding) ? Les humains déjà liés gardent-ils un droit ?
6. Courbe : garder τ,β Cursor (38 % / 11,85 %) ou la variante 159 `0.10+0.40/(1+(n-2)/1000)` (30 % @ 1000, pas 38 %) ?

### 8.2 Démographie

7. Extraction **exacte** UN WPP 18+ : millésime, fichier, pays inclus, 18+ vs 15+.
8. H_adult,max **immuable au genesis** ou mis à jour (ONU révise) ?
9. H réseau = humains **MATURED** seulement, ou VERIFIED, ou inscrits ?
10. Mort, majorité d’un mineur, révocation, jumeaux, tuteurs.
11. Recalibrer α si H0 n’est plus « 1 M d’humains quelconques ».

### 8.3 HBP

12. Bénéficiaires : tous les humains du bloc, tous les MATURED mondiaux, seulement Finders, pondéré W_i ?
13. Owners A comptent-ils dans le pool HBP ? (le code actuel **oui**)
14. H=0 : 10 % × 50 = 5 ARTCB → burn, trésor, fondateur, ou bloc interdit ?
15. Formule piecewise 10+100x / 100-80x : **tu ne l’as pas votée** ; ChatGPT l’a proposée.

### 8.4 Émission

16. Confirmer par écrit : **plus aucun** halving d’index de bloc (cela **abroge D-016**).
17. Confirmer suppression velocity (rapport 080 héritage).
18. Reliquat satoshi : dernier règlement absorbe vs cap strict inférieur.
19. Si H redescend (révocation massive), R(H) **remonte-t-il** ? (le code actuel oui)

### 8.5 Provider / Worker

20. Pourcentage ou fonction (qualité, originalité, anti-spam « Bonjour » × 10 M).
21. Provider rémunéré seulement si PoL du Job est **accepté** ?
22. Un même humain Provider+Worker+Bound+Finder : ordre des legs, anti double comptage (151 §28).

### 8.6 Identité / machines / wallets

23. HumanID : quel prover (ZK, vendor, self-sovereign) **sans** biométrie on-chain.
24. TPM obligatoire mainnet vs optionnel (127 machine Dell ≠ tous les nœuds).
25. 1 wallet/device (code 114) vs N machines / 1 owner : **schéma d’identifiants**.
26. Un humain bindé chez A peut-il miner sa propre C1 **et** rester B chez A ? (oui en 152 — confirmer)

### 8.7 Consensus

27. Canonique EconomicRoot : champs, ordre, encoding, fork si on change `artcb_build_canonical`.
28. Blocs historiques 1 ARTCB : déjà conservés ; blocs 50+210k déjà minés sur cette branche : politique.

### 8.8 Finder (si tu veux encore Q=100)

29. H0=100 vs Genesis 101 vs Q(H)=min(100,H-1).
30. Mode A / C. Productivité réelle Finder (5 vs 20 vs 100 attestations/h).
31. T maturité, durée challenge, credential age juridique.

### 8.9 DDPBA

32. Qui produit la PartitionMap (consensus pré-affectation).
33. Capacity_PB par dimension. N_max. Vagues.
34. Lien Job Provider payload → WorkIDs.

### 8.10 UBI

35. Mort ou vivant ? 133 a quasi enterré le supply B. Si vivant : oracle prix, budget, D.

### 8.11 Gouvernance documentaire

36. D-016 / D-023 : **amender explicitement** ou garder 210k comme « option expérimentale flag ».  
    156/158/159 disent de ne **pas** traiter velocity comme règle ARTCB. Le code le fait quand même.

---

## 9. Contradictions internes encore vivantes (ne pas « corriger » sans toi)

| ID | Pôle A | Pôle B | Où |
|----|--------|--------|-----|
| C1 | D-016 / D-023 / code / tests : 210k | 158–159 : calendrier mort | décisions vs dumps |
| C2 | M1 toujours 100 % (code + 156 OK + 159 texte N=1) | 159 §27 P(N_A) sur M1 aussi | **intérieur de 159** |
| C3 | Courbe Cursor 38 % @ 1k | Formule simple 159 30 % @ 1k | 159 utilise les deux |
| C4 | HBP équiparti (code) | Finder W_i (134–135, 156 « CORRECTION ») | jamais tranché |
| C5 | 1 wallet / device | N machines / owner | 114 vs economics |
| C6 | UBI supply B (128–130) | UBI émergent A/B+HBP (133) | pas de D-xxx UBI |
| C7 | Q=100 « verrouillé » conversation | 0 % code, 0 D-xxx Finder | spec vs dépôt |
| C8 | `verified_humans=0` ⇒ R=50 et HBP=10 % | 159 genesis 5 ARTCB HBP sans tête | 124 vs 159 |
| C9 | Rapport 124 « avancement couche 100 % » | 156 « je ne certifie pas protocole complet » | honnêteté 156 gagne |
| C10 | Identity 50×210k×2 « preuve » 21 M | 159 : 21 M cap, identité Bitcoin **n’est plus** l’émission | 124 vs 159 |

---

## 10. Travail restant — fonction par fonction (plan, pas d’implémentation)

Ordre suggéré **après tes réponses 8.x**, pas avant.

### 10.1 Si tu confirmes la spec 159 (GO écrit)

1. `emission.py` : supprimer (ou flag off) `schedule_reward_satoshi` / `extra_epochs` du chemin chaud  
2. `manager.py` : `_calculate_block_reward` = min(R(H_adult), remaining) ; **supprimer** `_compute_dynamic_epoch` du reward  
3. `hbp.py` : bornes × H_adult,max (constante genesis datée, pas un float magique 5.82e9 non sourcé)  
4. `settlement.py` : grouper par owner, `N_A = max(index enregistré ou courant selon 8.4)`, appliquer P(N_A) selon ta réponse **M1**  
5. `human_binding` : source de N_A, pas l’index de la ligne du bloc  
6. `tokenomics.py` + D-016/D-023 + TOKENOMICS + `/params` + tests T-E01 : **réécrire** pour ne plus figer 210k  
7. Pipeline mining : attacher machine fields **ou** HBP ne se déclenchera jamais en prod  
8. EconomicRoot dans hash : changement C FFI + replay policy  
9. Genesis HBP : selon 8.14  
10. Recalculer tests ABCD : la table 23,5937 **doit** changer si taux commun

### 10.2 Identité (indépendant, déjà demandé 156)

11. HumanID 18+ + liveness + nullifier (off-chain)  
12. Relier `device_fingerprint` obligatoire à EK/TPM quand dispo  
13. Trancher 1 wallet/device vs multi-machine  

### 10.3 Finder (fil 134–141 entier)

14. États, Q=100, sélection aléatoire, Finder Block, W_i, MATURED avant transfert  

### 10.4 DDPBA (fil 144–145)

15. WorkID, PartitionMap, Used, dimensions, N_d dynamique, N_max  

### 10.5 Job Provider réel

16. Payload canonique, qualité, **% Provider**, virement via settle_block, anti-spam  

### 10.6 Ce que je ne ferai pas tout seul

- Inventer H_adult,max  
- Trancher M1  
- Remettre UBI  
- Coder Q=100 « en silence »  
- Merger `main`  
- Présenter 535 tests comme « protocole fini »

---

## 11. Questions **nouvelles** nées du croisement (pas posées telles quelles dans les dumps)

Ces questions n’apparaissent pas mot pour mot ; elles tombent dès qu’on superpose 159 et le code.

1. Un bloc qui ne contient **que M1 d’A** alors que A a 1 000 machines enregistrées : P(1) ou P(1000) ?  
2. Deux owners dans le même bloc : N_A et N_C indépendants — OK conceptuel, **non testé** multi-owner dans `test_economics_protocol` au-delà de A+C.  
3. HBP code ajoute **owners** dans `humans[]` : A reçoit du HBP **en plus** de P_owner. 159 parle de Finder/humains. Double casquette non chiffrée.  
4. `work_weight` actuel = `pol_score` si on passe par `_machine_contributions`. PoL et capacité machine **fusionnés** sans le dire.  
5. `verified_humans` est un **float passé à la main** à `append_block`. N’importe quel nœud peut mentir H pour changer R et HBP. Sans oracle / consensus H, **toute** la tokenomics 159 est bypassable.  
6. Flags `ARTCB_ALLOW_MULTI_WALLET` et `ARTCB_BOOTSTRAP_NODE` cassent 1-device-1-wallet en dev : politique mainnet ?  
7. Historique chaînes 1 ARTCB + future chaînes 50+R(H) : deux économies sur le même fichier JSONL.  
8. Rapport 157 a simulé **après** 156 mais **avant** le reset 158 : ses ledgers 15,04 / 12,19 / 22,05 / 0,71 **ne sont plus** la référence 159.  
9. `ai_routes.py` explique encore le triple halving aux utilisateurs de l’API IA.  
10. PR GitHub : l’agent n’est pas collaborateur ; compare URL seulement.

---

## 12. Verdict

### 12.1 Sur la branche

La branche **contient bien tout le travail de simulation** (fichiers 125–159) **et** l’implémentation 124.  
HEAD `73efd0d` est à jour avec `origin`. `main` n’a **pas** ces changements.

### 12.2 Sur l’ordre de vérité

```
conversation 158–159  >  conversation 153–155  =  code 124  >  dumps 128–132 (R0=1)
```

Lire les fichiers dans l’ordre numérique **inverse** la chronologie (ex. 126 est une synthèse fondatrice, 125 est hors sujet, 159 est le dernier mot conversationnel).

### 12.3 Phrase unique à retenir

**Le code implémente l’audit 153–155 (Bitcoin-like 50/210k + R(H) + HBP 8,3 Md + P_owner par index machine). Les rapports 158–159 ont ensuite abrogé le calendrier, la vélocité, les 8,3 Md et le settlement par index — sans que le code ait bougé. Les fils Finder Q=100, DDPBA WorkID, HumanID 18+ et Job Provider réel n’ont jamais été codés. 535 tests verts prouvent le modèle 124, pas le protocole 159.**

### 12.4 Pour la suite

Dès que tu tranches **§8** (surtout M1, D-016, H_adult,max, HBP bénéficiaires, Provider %), un agent peut implémenter 159 **sans réinventer**. Tant que C2 (M1) et C1 (210k) restent ouverts, tout patch serait une **supposition**.

---

## 13. Annexes rapides

### 13.1 Identité Git de cette passe

- Branche : `cursor/tokenomics-21m-hbp-owner-decay-3fcb`
- Implémentation : `25b832f`
- Docs conversation : `25b832f..73efd0d`
- Ce rapport : `rapports/160_audit_croise_simulations_124_a_159_2026-08-26.md`

### 13.2 Fichiers economics (rappel chemins)

```
src/artcb/economics/__init__.py
src/artcb/economics/emission.py
src/artcb/economics/hbp.py
src/artcb/economics/owner_decay.py
src/artcb/economics/human_binding.py
src/artcb/economics/preblocks.py
src/artcb/economics/job_provider.py
src/artcb/economics/settlement.py
src/artcb/economics/satoshi.py
src/api/economics_routes.py
tests/test_economics_protocol.py
```

### 13.3 Ce rapport n’écrase pas 124

124 reste l’historique d’implémentation. 160 est l’audit croisé. 154≡155 et 140≡141 ne doivent pas être « fusionnés » sur disque (tu as demandé de ne pas écraser les anciens rapports).
