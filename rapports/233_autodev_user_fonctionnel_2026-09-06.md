# Rapport 233 — Sync origin/main 223–232 + user auto-dev réel

**Date :** 2026-09-06. **Rang 6** (observation) + **rang 3–4** (code/tests auto-dev).  
**Aucune D-0xx.** Certification **non retouchée**. Tip public **non touché**.  
**Ce n’est pas** une certification Byzantine, ni PoUC, ni V-01-B producteur.

Dernier travail agent précédent : `8a751e8` (222).  
`origin/main` au moment de ce rapport : `8d76a23303cb57b4f0d701c3fe796d728ae42567`.  
Live `/health.git_sha` mesuré en bootstrap : `8d76a23303cb57b4f0d701c3fe796d728ae42567` (docs 232 déjà follow-main).

---

## 1. Pushes détectés depuis `8a751e8`

| SHA | Message | Nature |
|---|---|---|
| `477087c` | feat(bob): Doppler MCP + rapport 058 | MCP + install locale Bob |
| `64a5d45` | Expand ARTCB governance… | **223** rang 6 |
| `7e7d2a8` | chat and simulation findings | **224** |
| `fc6a911` | scenario L | **225** |
| `07c0ac9` | distinctions gouvernance / nœuds | **226** |
| `f4723bb` | project analysis | **227** |
| `c0f4534` | GitHub repository state | **228** |
| `0d47bb1` | audit Bob | **229** |
| `ae0364d` | PoL → Proof of Utility | **230** |
| `52634ab` | PoUC | **231** |
| `8d76a23` | modèle ARTCB | **232** |

**12 fichiers ajoutés, 0 fichier de protocole `src/artcb/**` modifié par ces 11 commits.**  
C’est-à-dire : depuis 222, le distant n’a **pas** avancé le code de convergence. Il a poussé des **rapports chat/simulation** et le MCP Doppler de Bob.

---

## 2. Ce que chaque rapport dit — et ce qui est déjà fait

| Rapport | Sujet | Déjà fait (code/live) | À ne pas coder maintenant | À faire plus tard (GO) |
|---|---|---|---|---|
| **058** | Install Mac Bob, 804/30/9 | Machine deyi uniquement | Transformer 96,4 % en certif | PYTHONPATH portable (**fait 233**) |
| **223** | Spec gouvernance ORG | 220 : LEGAL_OWNER / controller / transfer | Multisig 3-of-5, timelock, RCS, merge/split | — |
| **224** | Audit 220 | V-01 partiel mono-nœud ; 221 a fermé le tip 4/4 | Relire 220 comme s’il était encore le trou | — |
| **225** | Scénario L producteur mort | V-01-B **lecture** 222 | L producteur (OVH2 crée pendant OVH1 OFF) | V-01-B.1 |
| **226** | « Créateur » ≠ producteur de bloc | Clarification seulement | Confondre droits Genesis global et L | Audit Genesis global **séparé** |
| **227** | Audit 222 | `decide_public_import` + T-E48 | Receive=pull **transport** (pull encore GET clair) | V-01-B.1/B.2/B.3 |
| **228** | SHA main a bougé | Confirmé : `477087c` puis docs jusqu’à `8d76a23` | Présenter e68563e comme preuve du main actuel | Certification **par SHA** |
| **229** | Audit Bob | Doppler MCP utile ; 30 FAIL classifiés | `ARTCB_ALLOW_INSECURE_HTTP` en prod | Corriger 30 FAIL par catégorie |
| **230** | Utilité ≠ validité | Pipeline PoL existe | KnowledgeID / UsageID | Formaliser **avant** code |
| **231** | PoUC + Challenge/Stake | — | Coder PoUC | Simulation A/B/C/D |
| **232** | KCG graphe | — | Coder le graphe | Modèle formel d’événements |

---

## 3. Questions posées / réponses (inventaire)

### Gouvernance (223–224, déjà tranchées en 220 sauf dit)

| Question | Réponse actuelle |
|---|---|
| Faut-il un transfert d’autorité ORG ? | Oui. Codé 220. Genesis immuable, contrôle transférable. |
| Créer une nouvelle ORG à chaque vente ? | Non. |
| LEGAL_OWNER ≠ AUTHORIZED_CONTROLLER ? | Oui, codé. |
| Multisig / timelock / preuve RCS ? | Non. Hors périmètre. Pas D-0xx. |
| Commitment sur 4 nœuds (220) ? | Non en 220. **Oui en 221** sur ce parcours. |
| V-01 = réseau certifié ? | **Non.** |

### Résilience (225–229)

| Question | Réponse |
|---|---|
| L = droits du fondateur ARTCB ? | **Non.** L = nœud producteur indisponible. |
| OVH1 arrêté, les autres gardent le tip ? | **Oui** (V-01-B lecture, SHA `e68563e`). |
| OVH2 produit un bloc pendant l’arrêt ? | **Non démontré.** |
| Receive et pull même verdict ? | **Oui** (222). |
| Receive et pull même transport ? | **Non** (pull GET clair). |
| `append_block` est-il BFT ? | **Non** (`not_block_append_bft`). |
| 96,4 % tests = protocole certifié ? | **Non.** |
| Live 222 a-t-il exécuté le code 222 ? | **Non.** Live = `e68563e`. |

### PoL / utilité (230–232)

| Question | Réponse |
|---|---|
| Validité du travail = utilité ? | **Non.** |
| Deux Genesis ? | **Non.** Global Genesis reste constitution. |
| Popularité = utilité ? | **Non.** |
| Coder Proof of Utility / PoUC / KCG maintenant ? | **Non.** Formaliser + simuler d’abord. |

### Auto-dev (cette demande)

| Question | Réponse avant 233 | Après 233 |
|---|---|---|
| L’agent Cursor est-il un user ARTCB réel ? | Non : clé opérateur `artcb_` | Session `sess_` + `X-ARTCB-Agent-Id` |
| MCP grave-t-il au nom d’un humain ? | Non (et envoyait `text` au lieu de `content`) | `content=` + session |
| Un agent peut-il créer une ORG ? | 403 (déjà 220) | Toujours 403 (T-E49) |

---

## 4. Ce que tu n’avais pas précisé — protocole / autoprompt

1. **Hiérarchie des rangs** : 223–232 sont rang 6. Les écrire un jour ne les implémente pas.
2. **Ne pas inventer de D-0xx** (PoUC, KCG, L producteur).
3. **Ne pas déployer `main` sur OVH1** pour un mémo public. Auto-dev = **privé**.
4. **Ne pas wiper** `blocks.jsonl`. Tip live reste 5 blocs / `27350024…` (mesuré 222 ; 233 ne le change pas).
5. **D-029** : ne pas envoyer la clé OVH1 aux Doppler 2/3/4. Operator sync 4/4 reste rouge.
6. **D-024** : le prompt MCP parlait encore d’un « halving dynamique » — retiré.
7. **D-032** : Ed25519 temporaire jusqu’au 2026-12-31. 9 FAIL liboqs de Bob = attendu.
8. **Contact officiel** : `official@artcb.space`.
9. **Certification par SHA** (228–229) : distinguer code exécuté / commit documentaire / main actuel.
10. **from_node_id** n’est pas une preuve d’identité producteur.

---

## 5. User auto-dev — comment ça se produit bout-en-bout

```text
humain (wallet artcb-autodev + mot de passe)
        │
        ▼
POST /auth/login  →  sess_…   (jamais imprimé)
        │
        ▼
X-ARTCB-Agent-Id: cursor-autodev
        │
        ├─ GET  /auth/me     → kind=agent, is_user=true, address=artcb1…
        ├─ POST /ai/memo     → visibility=private, actor=cette adresse
        └─ POST /authz/orgs  → 403  (l'agent n'administre pas)
```

**Avant :** MCP + bootstrap parlaient à `/api/v1/api-keys/me` avec `ARTCB_API_KEY`.  
C’est-à-dire : **le nœud**, pas un utilisateur.

**Après 233 :**

| Couche | Fichier |
|---|---|
| Rôles | `src/artcb/autodev/user.py` |
| Session user | `GET /api/v1/auth/me` |
| Mémo / think | `require_write_actor` accepte `sess_` |
| MCP | `artcb_whoami`, `artcb_login`, `artcb_autodev_record` |
| PYTHONPATH Bob | `${workspaceFolder}` (plus `/Users/deyi/...`) |
| Tests | T-E49 `tests/test_e2e233_autodev_user.py` |
| Script | `scripts/artcb_autodev_user.py --self-test` |

**Non fait (volontaire) :** créer un wallet auto-dev **sur OVH1**, graver un mémo **live**, créer l’ORG officielle ARTCB. Cela toucherait le livre ou exigerait un humain sans agent.

---

## 6. Matrice protocole (233)

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| Opérateur ≠ user | autoprompt / 216 | 233 | `auth/me` + `require_write_actor` | T-E49 | `/auth/me` pas encore sur SHA live au commit |
| Agent sous session | 216 / 220 | 219 | `X-ARTCB-Agent-Id` | T-E49 403 ORG | — |
| Mémo auto-dev privé | 233 | — | MCP + AutodevUser | T-E49 | non (privé local) |
| PoUC / KCG | non (rang 6) | 230–232 | non | non | non |
| V-01-B producteur | non | 225 / 227 | non | non | non |

---

## 7. Prochain verrou (pas V-02)

Toujours rouge, **dans cet ordre** :

1. V-01-B.1 producteur (OVH1 OFF → OVH2 commitment → 4/4) — **fork possible, GO explicite**
2. Partition + rejoin (N / Z)
3. Operator sync 4/4 (clés Doppler isolées)
4. Formalisation 232 (événements) **sans code**
5. Puis seulement V-02…V-07
