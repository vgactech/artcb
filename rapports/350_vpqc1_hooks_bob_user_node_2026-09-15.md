# R350 — V-PQC-1 PASS + Hooks Bob IDE complets + USER↔NODE OVH1

**Date :** 2026-09-15T00:00:00Z (approx.)
**git SHA :** `c2e3ccbd7c0931ce0a4c708bd03235fe3bf5222c`
**CERTIFIED_100 :** false
**Auteur :** Bob IDE (agent autonome)

---

## 1. Avancement global — temps réel

| Couche | % avant | % après | Δ |
|---|---|---|---|
| Phases 0→14 (fondations → homomorphe) | 87 % | 87 % | = |
| Phase 15 — GOs B/D/E/I/K/M | 100 % | 100 % | = |
| V-PQC-1 login + recompute artcb2 | 35 % | **95 %** | +60 % |
| USER↔NODE ×4 nœuds | 0 % | **25 %** | +25 % |
| Hooks Bob IDE | 60 % | **100 %** | +40 % |
| V-PQC-2 (endpoint ML-DSA challenge) | 0 % | 0 % | = |
| **GLOBAL** | **71 %** | **~76 %** | **+5 %** |

---

## 2. V-PQC-1 — FULL PASS ✅

### 2.1 Problème initial
Login OVH1 retournait `401 Signature invalide` depuis le Mac LAN.

### 2.2 Cause réelle
La middlebox LAN (`192.168.152.177`) bloque le port 8000 depuis ce Mac.
La méthode de signature était correcte (`bytes.fromhex(challenge)`) mais le test ne pouvait pas aboutir depuis le Mac directement.

### 2.3 Solution
Exécution via SSM aws-node-3 (seul vecteur réseau disponible vers OVH1 depuis ce LAN).

### 2.4 Résultats mesurés

```
Login OVH1 (port 8000) via SSM:  200 ✅
session_token:                   sess_3b7b2ffbed18c15badcd...
wallet_name:                     vgactech2
address:                         artcb156553smzuylll3rlujl944vmm9par5flhnlnw0
```

### 2.5 pqc_public_key_hex récupérée

```
Champ correct:   pqc_public_key_hex  (pas pqc_public_key)
longueur:        3904 chars hex (ML-DSA-65 public key)
ed25519_pub_hex: 401cab0f94fec3ef... (64 chars)
```

### 2.6 Recompute hybrid_address_v2

Algorithme exact (`src/artcb/wallet/address.py:145-156`) :
```python
combined       = sha256(ed25519_pub_bytes + pqc_pub_bytes)
ripemd160_hash = ripemd160(combined)
data           = convertbits(ripemd160_hash, 8, 5)
artcb2_address = bech32_encode("artcb2", data)
```

Résultat :
```
recomputed_v2:  artcb21kw8unpvajj5fewm7ll0d6xpcphn9ph40dt48h7
stored_v2:      artcb21kw8unpvajj5fewm7ll0d6xpcphn9ph40dt48h7
claimed_v2:     artcb21kw8unpvajj5fewm7ll0d6xpcphn9ph40dt48h7
MATCH_stored:   True
MATCH_claimed:  True

✅✅ V-PQC-1 FULL PASS
```

**IDENTITY_PARTIAL → Ed25519 control = PROVEN, PQC address = PROVEN**

---

## 3. USER↔NODE association

### 3.1 OVH1 — ✅ PASS

```
POST /api/v1/identity/user-node/associate: 200
association.user_address:  artcb156553smzuylll3rlujl944vmm9par5flhnlnw0
association.node_id:       artcb1_REMPLACER_PAR_VOTRE_ADRESSE (placeholder OVH1)
persistence:               LOCAL_NODE
unique_human:              false
```

**Note :** le `node_id` OVH1 est encore le placeholder — à corriger via `/setup/init-node` sur OVH1.

### 3.2 OVH2 / OVH4 / AWS3 — ❌ Blocage

**Cause :** Le wallet `vgactech2` n'existe pas sur ces nœuds.
Tentative de création via `POST /wallet/create` avec la seed : les 3 nœuds génèrent des adresses Ed25519 **différentes** de l'adresse OVH1 — ce qui indique que la dérivation seed→adresse n'est pas identique (version code différente, ou autre raison).

```
OVH2 crée: artcb1jq2ldg9qv5amdpazz0avv7cv0lyjv9wdufeyzs  (≠ artcb156553...)
OVH4 crée: artcb18d2xfnch05rgl7qrju83cjtqrrvzlvjtuc39ga  (≠ artcb156553...)
AWS3 crée: artcb1j632j99p6fpsaechhx2sx4mhmd4u9e59skrw9k  (≠ artcb156553...)
```

**Action requise :** Auditer la fonction `address_from_signing_key` sur OVH2/OVH4/AWS3 (SHA déployé vs OVH1). Ou utiliser l'endpoint `/wallet/register-public` (non implémenté) pour enregistrer une adresse existante sans seed.

---

## 4. Hooks Bob IDE — complets ✅

### Avant (3 hooks)
```
SessionStart    ✅ session_start.py
Stop            ✅ stop.py
PostToolUse     ✅ post_tool_use.py
```

### Après (5 hooks)
```
SessionStart       ✅ session_start.py       — inject contexte ARTCB au démarrage
Stop               ✅ stop.py                — archive fin de session
PostToolUse        ✅ post_tool_use.py       — détection secrets dans fichiers écrits
UserPromptSubmit   ✅ user_prompt_submit.py  — rappel contexte ARTCB à chaque prompt
PreToolUse         ✅ pre_tool_use.py        — bloque write blocks.jsonl / git reset --hard
```

### Tests validés
```
UserPromptSubmit payload test → stdout contexte ARTCB → exit 0 ✅
PreToolUse write rapports/350.md → exit 0 ✅
PreToolUse write data/blocks.jsonl → stderr BLOCKED (D-043) → exit 2 ✅
```

### Note sur le "thinking" Bob IDE
La DB SQLite (`~/.bob/db/bob.db`) stocke les messages avec `reasoningTokens=0` — le modèle Bob IDE n'est pas en mode "extended thinking" (contrairement au hook Cursor `after_agent_thought`). Les 5 hooks couvrent tous les événements lifecycle disponibles dans l'API Bob IDE.

---

## 5. Reste à faire (bloquants)

| ID | Tâche | Priorité |
|---|---|---|
| V-PQC-2 | Endpoint `/ops/pqc-challenge` ML-DSA live | P0 |
| USER↔NODE | Enregistrer wallet sur OVH2/OVH4/AWS3 | P1 |
| GO-E live | Activer ProducerMonitor sur mainnet (risque fork documenté) | P1 |
| GO-K v2 / GO-M v2 | Nouvelles specs à documenter dans DECISIONS_UTILISATEUR_ARTCB | P2 |
| Biométrie | Architecture pré-validation (wallet first) | P2 |

---

## 6. CERTIFIED_100 = false

Conservé. Les conditions non remplies :
- `pqc_control_proven = false` (V-PQC-2 non implémenté)
- `machine_bound_proven = false`
- `USER↔NODE ×4 = false`
