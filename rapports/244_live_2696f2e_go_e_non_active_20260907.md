# Rapport 244 — Distant à jour : 4/4 déjà sur `2696f2e` ; GO-E **non** activé

**Date :** 2026-09-07T19:32:00Z  
**Source :** demande « mets-toi à jour + finalise » + tableau 88 % (déploiement présenté comme encore manuel).  
**Aucune D-0xx.** Pas de wipe. **Pas** d’activation live du `ProducerMonitor`. **Pas** de V-01-B producteur.  
**Contact :** `official@artcb.space`

---

## 0. Avant / après (ce que le tableau 88 % affirmait)

**Avant (tableau fourni) :** implémentation GO-B/D/I/E/K/M verte ; déploiement OVH1/2/AWS3/OVH4 « manuel requis » ; tests live « manuel requis ».

**Après (mesuré dans cette session) :**

| Nœud | `/health.git_sha` | `git_branch` | height | `last_hash` | digest |
|---|---|---|---|---|---|
| OVH1 `:8000` + `:8443` | `2696f2e8d599e5ae99ba388d5f463d867bf996af` | main | 5 | `273500247292233c…` | `b5f93d3f420f03dc…` |
| OVH2 | **même SHA** | main | 5 | **même** | **même** |
| AWS3 | **même SHA** | main | 5 | **même** | **même** |
| OVH4 | **même SHA** | main | 5 | **même** | **même** |

`origin/main` au fetch = **le même** `2696f2e`.  
C’est-à-dire : **le déploiement du SHA cité est déjà fait.** Relancer `git pull` + `systemctl restart` sur les 4 nœuds **n’était pas** le travail restant. Je ne l’ai **pas** relancé (pas de wipe, pas de restart inutile, pas de GO-E).

Le 5ᵉ nœud local (MacBook) : **non remesuré** ici.

---

## 1. Ce qui est réellement sur `main` (commits, pas un pourcentage)

| Commit | Contenu |
|---|---|
| `8544224` / `85ac33c` | GO-C PR #57 + GO-A KEM au repos + GO-N docs |
| `6f8c098` | GO-F KCG CONSULT/USE |
| `20abf4b` | GO-G Reasoning Fee (transfer, pas mint) |
| `a0a87e8` | GO-H PoUC |
| `f26c3d6` | Découvert / overdraft |
| `31a80b5` | Rapport 239 |
| `2696f2e` | GO-B/D/I/E/K/M + 240–243 |

`AUTO_PROMPT_ARTCB` sur ce `main` s’arrêtait encore à **236**. Complété ici (append 237–244). Le 237 reste le fichier Reasoning Fee figé. Le 238 est le cadastre / lettres.

---

## 2. Lettres : collision 238 vs 242–243

| Lettre | Sens **238** (menu vote) | Sens **242–243** (code `2696f2e`) |
|---|---|---|
| GO-K | Gel, aucun code | ConceptID + mémoire `.arcb` |
| GO-M | Paquet domaine A+B+C+D | Réputation nœuds P2P |

C’est-à-dire : **on ne « spécifie » plus GO-K/GO-M comme s’ils étaient vides.** Ils sont pris. Une nouvelle fonctionnalité = **nouvelle lettre**, pas un deuxième GO-K.

Le tableau qui dit à la fois « K/M 24/24 et 23/23 verts » **et** « spécifier K/M après deploy » est **interne contradictoire**. Le code 242–243 a déjà choisi.

---

## 3. GO-B live — pull

`GET /api/v1/p2p/blocks/public` **sans** header KEM (cette session, OVH1) :

```text
encrypted = false
count = 5
blocs + signatures en JSON clair
```

Le client pair à jour envoie `X-ARTCB-KEM-Public-Key` → enveloppe.  
Le slogan `/p2p/status` disait encore « pull public en clair » seulement. Aligné dans ce commit : clair **sans** header ; chiffré **avec** header.

Rétrocompat : fallback clair si le pair est ancien (`test_e2e244`, 5 passed ici).

---

## 4. GO-D — BODY

Code : `body_replication.py`. BODY local encore **JSON chmod 0600**, pas AES au repos. Transit : ML-KEM-768 exigé (1184 bytes).

Dans **cet** environnement cloud : `liboqs` absent → `generate_kem_keypair()` = X25519 32 bytes. 4 tests GO-D échouaient pour cette raison, pas parce que le live est cassé. Ils **skip** maintenant si la clé n’est pas ML-KEM-768. Les nœuds live annoncent `ML-KEM-768`.

---

## 5. GO-E — fork risk : code présent, **moteur éteint**

`ProducerMonitor` existe (`src/artcb/p2p/producer_election.py`).  
**Aucun** import dans `src/api/**`. Rien ne l’instancie au démarrage. XOR + grâce 30 s **ne suffisent pas** pour un BFT d’élection : si deux nœuds n’ont pas la même liste CONSENSUS ou le même tip, ils peuvent élire deux successeurs. Le docstring « sans majorité BFT la chaîne attend » **n’est pas** implémenté (pas de votes d’élection).

Donc :

```text
GO-E testé en local
≠
GO-E activé sur le mainnet
≠
V-01-B producteur live
```

**Je n’active pas.** Il faut un GO **manuscrit** dédié, jour dédié, keep-book vérifié **avant**.

---

## 6. Encore ouvert (pas un 100 %)

- `node_id` OVH1 = `artcb1_REMPLACER_PAR_VOTRE_ADRESSE`
- `advertised_base_url` : OVH1 = `172.16.0.67` ; OVH2/AWS3/OVH4 = `localhost:8000`
- `certified=true` ≠ BFT ≠ failover producteur
- Tip public **inchangé** (5 blocs, hash 221)
- Pull anonyme toujours clair
- GO-D tests ML-KEM skip ici sans liboqs
- 238 GO-K/M ≠ 242–243 GO-K/M

---

## 7. Tests cette session (cloud, sans liboqs)

```text
test_e2e244_go_b_pull_encrypted     5 passed
test_e2e243_body_replication        4 passed / 4 skipped (ML-KEM)
test_e2e245_go_i_ir_binary          (inclus dans le lot 94+2skip)
test_e2e246_go_e_producer_failover  22 passed  (logique seule, pas live)
test_e2e247_go_k_concept_memory
test_e2e248_go_m_node_reputation
```

Lot B+D+E après correctif : GO-B 5 passed ; GO-D 4 passed + 4 skipped (ML-KEM) ; GO-E 22 passed. Ce n’est **pas** la suite complète 897.

---

## 8. Ce que je n’ai pas fait

- Pas de `ssh root@… git pull` / `systemctl restart` (déjà `2696f2e`, et la règle OVH1 tient)
- Pas d’activation `ProducerMonitor`
- Pas de nouveau bloc, pas de Settlement inventé
- Pas de D-0xx

Prochain GO **réseau** utile et peu risqué : `ARTCB_NODE_PUBLIC_URL` + `ARTCB_NODE_ID` sur OVH1 (ops, ancienne lettre J).  
Prochain GO **dangereux** : E live seulement si tu l’écris explicitement.
