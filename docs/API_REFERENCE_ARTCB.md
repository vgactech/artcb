# ARTCB — Référence API v0.3.1
## Mise à jour 2026-08-06 — Authentification utilisateur (rapport 107)

Base URL : `http://localhost:8000/api/v1`  
Base URL Replit N1 : `https://lvx--supermicro20238.replit.app/api/v1`  
Base URL Replit N2 : `https://lvx--supermicro20239.replit.app/api/v1`

---

## ⚠️ FLUX D'AUTHENTIFICATION OBLIGATOIRE (nouveau depuis rapport 107)

```
1. Créer un compte   → POST /wallet/create  → reçoit address + seed_hex (SAUVEGARDER — 1 SEULE FOIS)
2. Se connecter      → POST /auth/login      → reçoit session_token (sess_xxx, TTL 30min)
3. Générer API key   → POST /api-keys/generate {Authorization: Bearer sess_xxx}
                      → reçoit token artcb_xxx lié au compte
4. Utiliser API key  → ChatGPT / Claude / n8n → {Authorization: Bearer artcb_xxx}
```

> **Règle absolue :** L'adresse et la clé publique sont PUBLIQUES — elles n'ouvrent rien.
> Seule la `seed_hex` (clé privée) ou le mot de passe permettent d'entrer dans un compte.

---

## Santé

### `GET /health`
```json
{"status": "ok", "debug": true, "chain": {"block_count": 533, "valid": true}}
```

---

## Authentification (NOUVEAU)

### `POST /auth/login`
Connexion classique par nom de wallet + mot de passe.

**Corps :**
```json
{"name": "mon_wallet", "password": "mon_mot_de_passe"}
```

**Réponse :**
```json
{
  "session_token": "sess_a1b2c3...",
  "wallet_name": "mon_wallet",
  "address": "artcb1xxx...",
  "expires_in": 1800,
  "message": "Connecté. Utilisez session_token dans Authorization: Bearer <token>"
}
```

---

### `GET /auth/challenge`
Obtenir un nonce pour l'authentification cryptographique (sans mot de passe).

**Réponse :**
```json
{
  "challenge": "a1b2c3d4...",
  "expires_in": 300,
  "instructions": "Signez ce challenge avec votre clé privée Ed25519..."
}
```

---

### `POST /auth/verify`
Soumettre une signature Ed25519 du challenge.

**Corps :**
```json
{
  "address": "artcb1xxx...",
  "challenge": "a1b2c3d4...",
  "signature": "ed25519_sig_hex..."
}
```

**Réponse :**
```json
{"session_token": "sess_xxx...", "wallet_name": "mon_wallet", "address": "artcb1xxx...", "expires_in": 1800}
```

---

### `POST /auth/logout`
Invalider la session courante.

**Headers :** `Authorization: Bearer sess_xxx`

**Réponse :** `{"logged_out": true}`

---

## Wallet

### `POST /wallet/create`
Crée un nouveau wallet avec clés hybrides Ed25519 + ML-DSA-65.

**Corps :**
```json
{"name": "mon_wallet"}
```

**Réponse :**
```json
{
  "name": "mon_wallet",
  "address": "artcb1...",
  "public_key_hex": "...",
  "public_key_b64": "...",
  "seed_hex": "a1b2c3...",
  "WARNING": "SAUVEGARDEZ votre seed_hex MAINTENANT — elle ne sera plus jamais affichée.",
  "hybrid": true,
  "address_v2": "artcb1pqc..."
}
```

> ⚠️ **`seed_hex` = votre clé privée.** Affichée une seule fois. À stocker en lieu sûr.
> Sans elle, le compte est **définitivement inaccessible**.
>
> - `address` et `public_key_hex` sont publics — partageables librement
> - `address_v2` — adresse PQC (absent si liboqs non installé)

---

### `GET /wallet/list`
Liste tous les wallets du nœud (adresses publiques uniquement, jamais les seeds).

---

### `POST /wallet/balance`
```json
{"address": "artcb1..."}
```

### `GET /wallet/balance/{address}`

---

## API Keys (Connecteurs tiers — ChatGPT, Claude, n8n…)

### `POST /api-keys/generate` ⚠️ AUTHENTIFICATION REQUISE
Crée une clé API `artcb_xxx` pour connecter des plateformes tierces.

**Headers :** `Authorization: Bearer sess_xxx` (token de session obligatoire)

**Corps :**
```json
{"label": "Mon ChatGPT", "scopes": ["read", "write"], "expires_days": 90}
```

**Réponse :**
```json
{
  "token": "artcb_xxxx...",
  "key_id": "kid_xxx",
  "label": "Mon ChatGPT",
  "owner_wallet": "mon_wallet",
  "owner_address": "artcb1xxx...",
  "message": "Conservez ce token — il ne sera plus affiché."
}
```

> `token` affiché **une seule fois**. La clé est liée au wallet authentifié.

---

### `GET /api-keys/list`
Liste les clés actives (tokens masqués).

### `DELETE /api-keys/{key_id}`
Révoquer une clé.

### `GET /api-keys/me`
Info sur la clé Bearer courante.

---

## Encode

### `POST /encode`
Encode un texte en graphe IR sémantique.

**Corps :**
```json
{"text": "mon texte", "session_id": "optionnel", "use_llm": false}
```

**Réponse :**
```json
{"graph_id": "g_abc123", "node_count": 5, "edge_count": 3, "compression_ratio": 0.68}
```

---

## Store

### `POST /store`
Grave un graphe IR dans la blockchain comme un bloc.

**Corps — mode 1 : text direct (encode + grave en 1 appel) :**
```json
{"text": "mon texte à encoder et graver"}
```

**Corps — mode 2 : graph_id existant :**
```json
{"graph_id": "g_abc123", "visibility": "private", "wallet_name": "mon_wallet"}
```

**Champs optionnels :**
| Champ | Type | Défaut | Description |
|-------|------|--------|-------------|
| `graph_id` | `string\|null` | `null` | ID du graphe pré-encodé. Obligatoire si `text` absent |
| `text` | `string\|null` | `null` | Texte à auto-encoder. Obligatoire si `graph_id` absent |
| `visibility` | `string` | `"private"` | `private` \| `group` \| `public` |
| `wallet_name` | `string\|null` | `null` | Wallet pour signature et récompense |
| `actor_address` | `string\|null` | `null` | Adresse du validateur |
| `group_id` | `string\|null` | `null` | Requis si `visibility=group` |

**Réponse :**
```json
{
  "block_index": 532,
  "hash": "48df8cc1...",
  "block_reward": 100000000,
  "pol_score": 0.6,
  "graph_id": "g_abc123",
  "visibility": "private",
  "signature": "hybrid:ed25519:...:mldsa65:..."
}
```

---

## Mining Pipeline

### `POST /mining/pipeline`
Pipeline complet : texte → IR → raisonnement dual-agent → bloc PoL.

**Corps :**
```json
{
  "text": "contenu à miner",
  "wallet_name": "mon_wallet",
  "visibility": "private",
  "store_block": true
}
```

> Route asynchrone — non-bloquante.

---

## Chain

### `GET /chain`
Liste les blocs.

### `GET /chain/block/{index}`
Détail d'un bloc.

### `GET /chain/status`
État de la chaîne (hauteur, validité, PQC).

### `GET /chain/blocks`
Liste paginée des blocs.

### `GET /chain/verify`
Vérification intégrité complète de la chaîne.

---

## IR

### `POST /ir/learn`
Encode + grave un bloc public.

**Corps :**
```json
{"wallet_address": "artcb1xxx...", "content": "texte à apprendre", "visibility": "public"}
```

---

## Node

### `GET /node/status`
État du nœud courant.

```json
{"node_id": "node_57ee00fe2d5b", "version": "0.3.0", "debug": true, "status": "running"}
```

---

## Gouvernance

### `POST /governance/creator-key-rotation`
Rotation de clé créateur — **signature Ed25519 OBLIGATOIRE** (pas de mode dev).

### `POST /governance/user-key-rotation`
Rotation de clé utilisateur — **signature Ed25519 OBLIGATOIRE**.

> Tout appel sans `signature_hex` valide retourne `GovernanceError` immédiatement.
> Il n'existe aucun bypass — ni en dev, ni en prod.

---

## P2P

### `GET /p2p/status`
État du nœud P2P (algorithme ML-KEM-768, pairs, blocs publics).

### `POST /p2p/sync`
Synchronisation avec un pair.

### `POST /p2p/peers`
Ajouter un pair connu.

---

## PoL Score

### `GET /pol/score`
Score Proof-of-Link courant.

```json
{
  "pol_score": 0.6,
  "delta_compression": 0.68,
  "validation_rate": 1.0,
  "retrieval_accuracy": 1.0
}
```

---

## Notes importantes

| Comportement | Description |
|--------------|-------------|
| `seed_hex` affiché une seule fois | À la création uniquement — ne jamais stocker côté serveur |
| Cache encode | Le même texte encodé deux fois retourne le même graphe (cache SHA-256) |
| Anti-Sybil | Rate-limit : 1 bloc par wallet toutes les 60s |
| Signatures hybrides | Chaque bloc signé Ed25519 + ML-DSA-65 simultanément |
| `graph_id` optionnel dans `/store` | Si `text` fourni, l'encode automatique avant gravure |
| `/api-keys/generate` requiert session | POST /auth/login d'abord, puis Bearer sess_xxx |
| Gouvernance sans signature → rejeté | Pas de bypass dev — `GovernanceError` immédiat |

---

## Economics (D-024 — 2026-08-26)

Base : `/api/v1/economics`

### `GET /economics/params`
Constantes : `max_supply_artcb=21000000`, `initial_block_reward_artcb=50`, `emission_model=R(H)`, `halving_removed=true`, `halving_interval=null`.

### `GET /economics/emission?block_index=&verified_humans=`
`issued = min(R(H), remaining_21M)`. `block_index` n’applique plus de halving.

### `GET /economics/hbp?verified_humans=`
HBP 10 % → 60 % → 20 %.

### `GET /economics/owner-share?machine_index=`
`P_owner(n)` continu.

### `POST /economics/settle`
Preview settlement owner / humain lié / HBP. Conservation `sum = R_block`.

### `POST /economics/preblocks/partition`
`sum Reward(PB_i) = R_block`.

### `POST /economics/machines` · `GET /economics/machines/{owner}`
Registre machine + binding humain (n≥2 obligatoire).

### `POST /economics/jobs` · `POST /economics/jobs/{id}/partition`
Job Provider : submit → partition par capacité.

