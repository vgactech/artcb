# Rapport 161 — Réponses protocole (bootstrap, Finder, HBP, frais) + retrait du halving 210 000

**Date :** 2026-08-26  
**Branche :** `cursor/tokenomics-21m-hbp-owner-decay-3fcb`  
**Décision nouvelle :** **D-024**  
**Expertises :** tokenomics, mechanism design, identité / liveness (recherche vendeurs), consensus pré-blocs, frais blockchain.

**Avancement de cette passe :**  
- Décisions utilisateur enregistrées : **100 %** des points auxquels tu as répondu  
- Explications des questions non comprises : **100 %** (ci-dessous)  
- Retrait halving 210k + extra_epochs du **chemin live** : **100 % code**  
- Finder / PartitionMap / UsefulWork : **0 % code** (spec seulement, comme demandé)

Aucun mock. Les blocs déjà gravés **gardent** leur `block_reward` historique.

---

## 1. Ce que tu as tranché (je ne réinterprète pas)

### 1.1 Bootstrap : H0=100, pas Genesis=101 auto-certifié par un comité

- **Le créateur est déjà considéré vérifié à 100 %.** C’est lui le premier HumanID. Il n’attend pas 100 Finders.
- **Tu peux**, quand tu l’estimes nécessaire pour coller au règlement général et **donner l’exemple**, demander toi-même une vérification 100/100.
- **Ensuite** le régime normal **H0=100** s’applique : les suivants ont besoin de 100 validations de Finders déjà vérifiés.

Ce n’est **pas** « le 101e humain débloque le premier ». C’est : **1 créateur bootstrap** → puis file d’attente Q=100.

À ne pas oublier (détail que tu n’as pas tranché) : si tu te fais vérifier 100/100 plus tard, est-ce **cosmétique / exemplaire** (tu restais déjà VERIFIED) ou est-ce que ça **remplace** le bootstrap créateur dans le ledger ? Suggestion : **exemplaire**, sans réécrire le Genesis.

### 1.2 HBP : 10 → 60 → 20 % — **déjà validé**

Pas 50 % au lancement. Le code `hbp.py` suit déjà cette trajectoire (bornes 4,15e9 / 8,3e9 encore provisoires côté adultes 18+).

### 1.3 Finder par défaut, activation volontaire

Tous les **VERIFIED** sont **Finder par défaut** (éligibles).  
Ils **activent** la demande pour valider des gens qui veulent être validés.  
**C’est à eux d’accepter quand ils sont en ligne.**  
Pas d’obligation de rester « Finder actif 24/7 ».

### 1.4 272,16 attestations/jour = simulation, pas capacité réelle

Tu confirmes : c’est l’utilisateur qui accepte ou refuse, et le débit réel = ce qu’**il** arrive à valider.  
Tu estimes plutôt **20 à 30 validations réussies par jour** par Finder, mesurable seulement **une fois la chaîne en ligne**.

Conséquence : les tables 70 185 Finders @ 8,3 Md (hypothèse 20/h → 272/j) **surestiment** fortement la capacité. Avec 25/jour :

```
attestations/j nécessaires à 191 014 nouveaux/j × 100 = 19,1 M
Finders actifs ≈ 19 100 000 / 25 ≈ 764 000
```

≈ **11× plus** de Finders que 70k. Ce n’est pas un bug de ta règle ; c’est la sim 135–141 qui était trop optimiste.

### 1.5 Randomness non manipulable

Tu ne spécifies pas un algo (VRF, etc.). Tu as choisi **Q=100** pour **diminuer** ce comportement, et tu **ajusteras** Q (ou ajouteras une règle) **après les premières données**.  
C’est une décision de **gouvernance empirique**, pas une formule cryptographique figée. Je la note ainsi.

### 1.6 Frais TX

- Tu **ne voulais aucune taxe** à la base.
- Compromis : frais **dynamiques selon le flux de pointe**.
- **Maximum** = le **minimum déjà vu** sur les blockchains existantes (ordre de grandeur bas de marché).
- **Minimum** = le plus bas possible, **mais pas trop trop bas** (anti-spam).
- **Tout frais collecté revient au supply restant** (voir 1.7).

### 1.7 21 M intouchable + frais → restant

Hard cap **21 000 000**. Les frais **ne créent pas** de tokens. Ils **réduisent ce qui sort** ou **ré-alimentent le budget restant** pour que le cap reste strict.

Formulation protocolaire que je retiens :

```
émis_ce_bloc = min(R(H), remaining)
remaining   -= émis_ce_bloc
remaining   += fees_collected_this_block   # jamais au-dessus de 21M − already_held
```

Détail oublié : « remaining » = 21M − (tout ce qui a déjà été émis et est encore en circulation) ? Ou 21M − émis brut même si brûlé ? Tu as dit supply 21 intouchable. Suggestion : **fees → unspent emission budget**, pas un deuxième pool.

### 1.8 Halving 210 000 blocs : **retiré**

Géopopulation uniquement. Voir §8 pour la liste exacte de ce qui a été retiré du code.

---

## 2. Questions que tu n’avais pas comprises — reformulées avec exemples

### 2.1 « Combien de temps dure la maturation avant FinderEligible ? »

**Ce n’était PAS « 10 ans d’âge du réseau ».**

Dans les dumps 134, un humain passe par :

```
INSCRIT → FINDER_PENDING → VERIFIED → MATURED → (peut transférer ses ARTCB)
```

Et un Finder a parfois `Finder_maturity > T` avant de **valider les autres**.

**Traduction concrète :**

Imagine B vient d’être validé par 100 Finders. Il est VERIFIED.  
Question : **peut-il immédiatement** être tiré au sort pour valider C, ou doit-il **attendre** (1 jour, 7 jours, 30 jours) pour qu’un attaquant ne crée pas 100 faux comptes qui se valident en chaîne le même après-midi ?

**Ce n’est pas 10 ans.** 10 ans bloquerait tout bootstrap.

**Suggestions (à choisir) :**

| Option | Délai avant de pouvoir *valider autrui* | Transfert des ARTCB | Commentaire |
|--------|------------------------------------------|---------------------|-------------|
| A — immédiat | 0 | dès VERIFIED | Simple ; plus risqué en Sybil |
| B — courte quarantaine | **7 jours** | 7 jours | Souvent utilisé en réputation |
| C — moyenne | **30 jours** | 30 jours | Compromis |
| D — longue | **90 jours** | 90 jours | Lourd pour l’adoption |
| E — deux horloges | Valider autrui après **7 j** | Argent transférable après **30 j** | Sépare « pouvoir Finder » et « cash-out » |

Tu as dit Finder **par défaut** dès VERIFIED + acceptation en ligne. Ça colle surtout à **A ou B**.  
**Ma suggestion :** **E** — éligible Finder après **7 jours**, ARTCB transférables après **30 jours**, ajustable après données réelles. **Pas 10 ans.**

Si tu voulais dire autre chose par « 10 ans » (ex. maturité d’une *preuve d’âge 18+*, ou durée d’un certificat), dis-le : ce serait un **autre** T.

### 2.2 Corrélations, coercition, géographie, collusion, refus coordonnés

**De quoi je parlais :** Q=100 protège si les 100 Finders sont **indépendants**. Dans la vraie vie ils ne le sont pas.

**Exemples :**

1. **Corrélation** — 80 Finders dans la même usine / le même village / le même FAI. Un patron les influence tous d’un coup. Ce n’est plus `0,01^100`, c’est plutôt « 1 groupe ».
2. **Coercition** — on force B à valider un faux humain (« valide mon cousin ou tu perds ton job »).
3. **Géographie** — un pays entier capture le pool Finder local.
4. **Collusion** — 100 amis se valident en rond.
5. **Refus coordonnés** — les Finders honnêtes refusent tous les dossiers d’une minorité (censure), ou refusent tout le monde pour saturer l’onboarding.

**Q=100 réduit** le cas « 1 inconnu malveillant ». **Q=100 ne suffit pas** si les 100 sont le même clan.

**Suggestions (combinables, pas toutes obligatoires) :**

- **Diversité géographique** : parmi 100 Finders, au plus N% d’une même région / AS réseau.
- **Anti-cercle** : interdiction de valider quelqu’un qui t’a validé dans les K derniers dossiers.
- **Tirage que le candidat ne choisit pas** (tu l’as déjà : sélection aléatoire).
- **Preuve de présence en ligne réelle** (session liveness **du Finder**, pas seulement du candidat) — tu l’as déjà en 134.
- **Après données** : si on mesure des grappes, **augmenter Q** ou ajouter la contrainte de diversité — exactement ta politique empirique.

Rien de tout ça n’est encore dans le code. Ce n’est pas urgent pour le MVP local.

### 2.3 Qui calcule et ratifie la Partition Map ?

**De quoi je parlais :** un bloc de travail n’est pas « 3 pré-blocs au hasard ».  
Le **travail** (transactions, PoL, attestations HBP) est une **liste d’items**. On les **découpe** en pré-blocs **sans recouvrement**.

La **Partition Map** = le **plan de découpage** : « l’item n°7342 va dans le pré-bloc TX-02 ».

**Exemple cuisine :** 10 000 commandes. Tu ne fais pas 3 cuisiniers qui recuisent **les mêmes** 10 000 plats (ça créerait 3× l’argent). Tu fais un **planning** : plats 1–5000 = fourneau A, 5001–10000 = fourneau B. Ce planning **écrit et signé**, c’est la Partition Map.

**Qui l’écrit ?** Si n’importe qui peut dire « le plat 7342 est à moi », deux pré-blocs réclament le même WorkID → double paye ou chaos.

**Suggestions :**

| Option | Qui produit la map | Qui l’accepte | Risque |
|--------|--------------------|---------------|--------|
| 1. Déterministe | Personne : `PartitionID = Hash(WorkID, Epoch, ParentRoot) mod N` | Tous recalculent le même résultat | Simple ; N doit être connu avant |
| 2. Proposeur de bloc | Le mineur du bloc propose la map | Les validateurs vérifient disjoint + couverture | Standard blockchain |
| 3. Comité | Un petit set signe la map d’abord | Le bloc ne passe que si la map est dans le header | Plus lourd |

**Suggestion ARTCB :** **option 1** (hash déterministe) + le bloc **contient** N et ParentRoot. Personne n’a à « voter » la map ; tout nœud honnête obtient la même.

### 2.4 Que devient le bloc si un pré-bloc obligatoire manque ou échoue ?

**Exemple :** la map dit « il faut PB-TX-01 … PB-TX-20 ».  
Le réseau n’a reçu que 19 pré-blocs. PB-TX-07 n’est jamais arrivé (panne, censure, timeout).

**Question :** on **attend** ? on **publie un bloc incomplet** ? on **refait** le découpage sans le lot 7 ?

**Suggestions :**

| Option | Comportement | Argent | Travail du lot manquant |
|--------|--------------|--------|-------------------------|
| A. Bloc refusé | Pas de bloc tant que 20/20 | 0 émis | Tout reste en file |
| B. Bloc partiel | On scelle 19 PB ; le lot 7 **repasse** à l’époque suivante | R_block **inchangé**, réparti sur 19 (leurs WorkIDs seulement) | Lot 7 non payé cette époque |
| C. Vague | On n’exige jamais « tous les lots du monde » : Vague 1 = PB 1–100 max, on scelle, Vague 2 ensuite | Chaque vague a son R_block **ou** un seul R_block pour la vague de l’époque | C’est le lien avec N_max ci-dessous |
| D. Timeout | Après T secondes, les PB présents sont scellés ; les absents = échec | Comme B | |

**Suggestion :** **C + B** — on ne rend jamais un pré-bloc « obligatoire pour l’univers entier ». On fixe un **plafond de PB par époque**. Ce qui n’entre pas **attend la vague suivante**. Le bloc sort **toujours** avec `somme rewards = R_block` sur le travail **présent**. Un PB manquant **n’annule pas** le bloc ; il **reporte** son WorkID.

Ça évite qu’un attaquant bloque la chaîne en « oubliant » exprès un pré-bloc.

### 2.5 N_max,d , vagues, disponibilité des données

**De quoi je parlais :**

- `N_d = ceil(demande / capacité d’un PB)` peut exploser : 10⁹ micro-pré-blocs = attaque (métadonnées infinies).
- `N_max,d` = **plafond** : « pas plus de 1 000 pré-blocs TX par époque ».
- **Vague** = si la demande > N_max × capacité, on traite **par fournées** (vague 1, vague 2…).
- **Disponibilité des données** : les octets du pré-bloc doivent être **téléchargeables** par les nœuds (sinon ils votent à l’aveugle).

**Exemple :** 2 millions de TX, 5 000 TX/PB → 400 PB. Si N_max=100, on fait **4 vagues** de 100 PB. Chaque vague = un assemblage. Les TX de la vague 4 **attendent**.

**Suggestions de plafonds de départ (provisoires, à mesurer) :**

| Dimension | Capacité/PB (illustratif 145) | N_max proposé | TX/PoL max par époque |
|-----------|-------------------------------|---------------|------------------------|
| TX | 5 000 | 100 | 500 000 |
| PoL | 4 000 | 50 | 200 000 |
| HBP | 2 000 | 50 | 100 000 |

Disponibilité : chaque PB a un `PreBlockRoot` ; le bloc final **ancre** les roots ; les corps se téléchargent (comme les transactions Bitcoin ne sont pas toutes dans le header).

### 2.6 Comment répartir frais TX et revenus externes ?

**Deux choses différentes :**

**A. Frais de transaction (gas)** — l’utilisateur paie pour que son transfert / son Job passe.

Tu as répondu : dynamique selon **pointe du réseau**, min bas mais pas spam, max = plancher du marché crypto, **et le produit revient au 21 M restant**.

**Exemple dynamique simple (suggestion, pas encore codé) :**

```
fee = fee_min * (1 + congestion^k)
congestion = (file_d_attente / file_cible)
fee_max = min_observé_sur_BTC_ou_L2   # ordre de grandeur, pas une copie BTC
```

Bitcoin aujourd’hui : frais souvent **très bas** hors pointe, **très hauts** en congestion. Ethereum L2 : souvent **fractions de centime**.  
« Maximum = le minimum déjà vu » : je lis ça comme **un plafond bas** (ARTCB ne doit pas devenir une machine à taxes).  
Chiffre exact **non fixé** (ex. 1 à 100 satoshi, ou 0,0001 ARTCB). À calibrer en testnet.

**B. Revenus externes** — un client paie **en euro / API** pour un Job IA. Ça n’est **pas** le block reward.  
Question ouverte restante : ces euros restent **hors chaîne** (contrat privé) ou une partie est **convertie** en ARTCB ? Tu n’as pas répondu. Suggestion : **hors chaîne** au début (JobFee commercial déjà « hors scope » en 146).

### 2.7 UsefulWork sans convertir les tokens en PoL

**De quoi je parlais :** en 142–143, un run Cursor consomme **des millions de tokens LLM**.  
Si on dit « 1 token LLM = 1 PoL », alors **celui qui spam ChatGPT** mine tout le 21 M.

**Exemple mauvais :** U3 envoie « Bonjour » × 10 millions de tokens → 10 M PoL → presque tout le bloc.

**Exemple bon :** on mesure **le travail utile vérifiable** :

- compression IR réelle (Δtaille),
- validation par le Critique,
- retrieval qui retrouve le bon nœud,
- un Job **accepté** par un Provider humain,

et **ensuite seulement** on donne un poids PoL. Les tokens LLM sont un **coût**, pas une **preuve**.

**Suggestions de métriques (déjà dans TOKENOMICS §5, à relier au Job) :**

```
PoL = 0.4*Δcompression + 0.3*validation_rate + 0.3*retrieval
```

plus : Job rejeté / spam → PoL = 0.  
Les 6,975 M tokens Cursor **ne rentrent pas** dans cette formule.

### 2.8 Normaliser les workloads Cursor (run / jour / user / type de token)

**De quoi je parlais :** tes 8 runs font 2,4 M à 13,9 M tokens. On ne peut pas dire « un utilisateur ARTCB = 6,975 M tokens/jour ».

**Quatre dénominateurs différents :**

| Base | Exemple | Piège |
|------|---------|--------|
| **Par run** | 1 conversation agent = 6,6 M | Un user peut faire 0 ou 20 runs |
| **Par jour** | 10,3 M le 22 août | Journée de dev intense ≠ moyenne mondiale |
| **Par utilisateur** | toi ≠ 8 Md d’humains | Extrapolation interdite (143 l’a dit) |
| **Par type de token** | input vs output vs cache | Les vendeurs facturent différemment |

**Suggestion :** garder **trois profils** dans les sims, jamais une moyenne unique :

- Humain chat léger : ~5k–50k tokens/j  
- Agent quotidien : ~0,5–2 M  
- Agent intensif (toi, Cursor) : ~2–14 M **par tâche**, pas par humain mondial  

Le protocole **n’a pas besoin** de normaliser Cursor pour miner. Cursor sert à **calibrer le coût réel du UsefulWork**, pas l’émission.

### 2.9 Rentabilité quand reward/work diminue

**De quoi je parlais :** si le bloc paie toujours **50 ARTCB** (ou moins via R(H)) mais qu’il y a **100× plus de travail** dans le bloc, chaque WorkID reçoit **100× moins**.

**Exemple 145 :**  
5 000 works / 50 ARTCB → 0,01 ARTCB/work.  
500 000 works → 0,0001 ARTCB/work.

Les mineurs peuvent **perdre de l’argent** (élec, GPU, API LLM) alors que le réseau « marche ».

**Ce n’est pas un bug du cap 21 M.** C’est la question : **qui paie le coût réel** quand l’émission devient petite ?

**Suggestions :**

1. **Frais Job (fiat ou ARTCB) du Provider** — le client du raisonnement paie le Worker ; le block reward n’est qu’un **bonus**.
2. **Plafond de WorkIDs par bloc** (lié à N_max) pour ne pas diluer à l’infini.
3. **R(H) déjà** réduit l’émission quand H explose — la rentabilité **doit** alors venir des frais utiles, pas de l’émission.
4. Ne **pas** augmenter le 21 M pour « payer les GPU ».

Tu as déjà séparé JobFee commercial (hors scope) et block reward. La rentabilité long terme = **surtout les Jobs payants**, pas le halving.

---

## 3. Recherche liveness — débit 5 / 10 / 20 / 50 / 100 par heure

Tu as demandé de **chercher en ligne**. Chiffres **vendeur** (moteur de décision, pas forcément la session humaine complète) :

| Plateforme | Temps annoncé | Source |
|------------|---------------|--------|
| Veriff | **~6 s** décision IDV ; liveness passive | veriff.com (moyenne commerciale) |
| Sumsub | **~20–30 s** | comparatifs 2026 |
| Onfido / Jumio | **~30–60 s** moteur ; jusqu’à **~5 min** si revue humaine | Veriff vs Onfido / Jumio |
| Worldcoin Orb | scan **~10 s–1 min** ; parcours total souvent **quelques minutes** (+ file) | world.org / retours utilisateurs |

**Ce que ça implique pour un Finder ARTCB** (session **avec** challenge : tourner la tête, dire un nombre — plus long qu’un selfie passif) :

| Hypothèse session Finder | Sessions/heure théoriques | /jour (8 h attentives) | /jour (réaliste 2–3 h) |
|--------------------------|---------------------------|------------------------|------------------------|
| 60 s (proche KYC auto) | 60 | 480 | ~120–180 |
| 2–3 min (challenge + échecs) | 20–30 | 160–240 | **40–90** |
| 5 min (revue / réseau pourri) | 12 | 96 | **20–40** |
| **Ta fourchette 20–30 / jour** | — | — | **cohérente avec 5–15 min/session utile + pauses** |

**Verdict honnête :**  
- **100/h** = presque seulement du **passif 6–30 s sans challenge**, irréaliste pour 134 (challenge dynamique).  
- **20/h** (sim 135) = 3 min/session **en continu**, plausible en labo, **pas** une soirée normale.  
- **5–10/h** = 6–12 min, plus proche d’un humain fatigué.  
- **20–30 / jour** (toi) = **~2–4/h** sur une plage courte, ou 5 min × 25 = **~2 h de Finder par jour**. C’est **crédible**.  
La sim **272/j** suppose ~11 h × 25/h. **À jeter comme capacité réelle.**

On mesurera en mainnet. En attendant je fige dans la spec : **paramètre `FinderAttestationsPerDay` = observé, défaut de sim 25, pas 272.**

---

## 4. D-024 — ce qui a été **retiré** du code live (liste exacte)

Formule live maintenant :

```
R_block = min(R(H), remaining_21M)
```

`block_index` **ne divise plus** le reward. `extra_epochs` **ignoré** (warning si quelqu’un le passe encore).

### 4.1 Retiré du chemin d’émission

| Élément | Avant | Après |
|---------|-------|-------|
| `issued = min(schedule 50>>epoch, R(H), remaining)` | actif | **min(R(H), remaining)** |
| `schedule_reward_satoshi` dans `ChainManager` | actif | **plus appelé** (fonction deprecated + warning) |
| `HALVING_INTERVAL` pour couper R | 210_000 | **DEPRECATED_HALVING_INTERVAL** archive |
| `epoch = index // 210_000` | 50→25 au bloc 210k | **bloc 210k reste 50 si H≤1M** |
| `extra_epochs` / `epoch_dyn = log2(v/144)` | soupape reward | **return 0** ; vitesse = **métrique** `_observe_velocity_per_day` |
| Identité `50×210k×2` comme **calendrier** | TOKENOMICS / API / tests | **21 M = cap seulement** |
| `GET /economics/params` `halving_interval=210000` | oui | `null` + `halving_removed: true` |
| `GET /economics/emission extra_epochs=` | query | **paramètre supprimé** |
| Dashboard `next_halving_at`, `epoch_fixe` | nombres | `null` + remaining supply |
| `ai_routes` `/block-sizes` formule 210k + dyn | oui | `min(R(H), remaining)` |
| Genesis `halving_interval: 210_000`, v3.0 | oui | `null`, **genesis_version 4.0**, archive 210k |
| `scripts/mine_learning_simple.py` `>> index//210k` | oui | `issued_reward_satoshi` |
| Tests « bloc 210k = 25 ARTCB » | T-E01/T-E02 | **210k = 50 ARTCB** |
| Reliquat ~0,023 ARTCB du `>> k` | artefact calendrier | **N/A** (plus de `>>` live) |

### 4.2 Volontairement **pas** détruit (pour ne rien casser)

| Élément | Pourquoi |
|---------|----------|
| Constantes `HALVING_INTERVAL` alias | anciens imports ne crashent pas |
| `schedule_reward_satoshi` deprecated | archive + warning, pas le live |
| `scripts/etude_eco_complete.py` | étude 100 ans historique ; bandeau ARCHIVE |
| Blocs déjà minés | `block_reward` inchangé |
| R(H), HBP, OwnerDecay, binding, settlement, satoshi conservation | intacts |
| Anti-Sybil, PoL split legacy mining | intacts |
| Rapports 124–160 | jamais écrasés |

### 4.3 Pas encore fait (hors de « retirer le 210k »)

- Settlement `P(N_A)` commun (159)  
- Bornes HBP adultes 18+  
- Frais dynamiques + recycle vers remaining (**spec 1.6–1.7, pas de module fee encore**)  
- Finder / PartitionMap  

---

## 5. Autres questions auxquelles tu **n’as pas** répondu

Toujours ouvertes (rapport 160 + cette passe). Une ligne = j’ai besoin de toi.

1. **M1 après M2+** : 100 % pour toujours, ou le taux courant P(N_A) s’applique aussi à M1 ?  
2. **H_adult,max** : extraction ONU 18+ datée ; gelée au genesis ou mise à jour ?  
3. **HBP à H=0** : 5 ARTCB sans bénéficiaire — burn / restant / bloc interdit ? (tes frais→restant suggère **burn vers remaining**, à confirmer)  
4. **HBP équiparti vs pondéré Finder W_i**  
5. **Part Provider / Worker** dans le pool travail  
6. **Courbe OwnerDecay** : garder 38 % @ 1k (code) ou l’autre formule 159 ?  
7. Un humain bindé chez A peut-il binder **un autre owner** ? N_A **peut-il baisser** (vente machine) ?  
8. **1 wallet / device** vs N machines / 1 owner  
9. Si tu te fais vérifier 100/100 plus tard : cosmétique ou remplacement Genesis ?  
10. **Délai Finder** : 0 / 7 / 30 jours (pas 10 ans) — voir §2.1  
11. **Diversité géographique** des 100 Finders : oui/non au lancement  
12. Partition Map : OK pour **hash déterministe** (option 1) ?  
13. PB manquant : OK pour **reporter le WorkID** sans tuer le bloc ?  
14. N_max provisoires du tableau §2.5 : OK pour testnet ?  
15. Revenus **fiat** des Jobs : hors chaîne au début ?  
16. Ordre de grandeur **fee_min / fee_max** en satoshi (même une fourchette)  
17. GO pour **coder** Finder Q=100 / HumanID, ou plus tard ?

---

## 6. Tests

Commande : `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line`  

```
534 passed, 20 skipped in 184.54s (0:03:04)
```

0 échec. Logs : `logs/20260826_pytest_d024_full.txt`, `logs/20260826_economics_protocol.json`.  
Un test de moins qu’en 124 (535) : les assertions « 210k → 25 ARTCB » et la table calendrier 600 s ont été **remplacées** par « 210k → 50 » et « extra_epochs ignoré ».

Cibles T-E01 / T-E02 : l’index 210 000 **ne produit plus** 25 ARTCB.
