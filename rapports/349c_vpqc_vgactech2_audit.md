# V-PQC audit — `vgactech2` (IDENTITY_PARTIAL)

**UTC:** 2026-09-14T18:31:00Z (approx.)  
**Live code SHA:** `612691f3103d2ce94ec1983f007e95a987a0aa89`  
**CERTIFIED_100:** false  
**Artefact:** `logs/R349b/vpqc_vgactech2_audit.json`  
**Secrets:** Doppler `artcb-1`/`prd` names only — **never** values in this file.

## Clarifications (operator / auditor)

| Chaîne fournie | Rôle réel |
| --- | --- |
| `586bc9d6…` (64 hex) | **Seed Ed25519** — **pas** un commit Git (`git cat-file` = not a valid object) |
| `artcb156553…` | Adresse classique (`artcb1…`) |
| `artcb21kw8…` | Adresse hybride v2 (`artcb2…`) — format OK |
| `artcb_546b…` | **Clé API** (`/api-keys/me`) — **pas** l’identité wallet |

## Matrice de contrôles (mesurée)

| Contrôle | Statut |
| --- | --- |
| Format adresse classique (préfixe + checksum) | **PASS** |
| Format adresse PQC v2 (`artcb2` + checksum) | **PASS** |
| Seed → pubkey → adresse classique = claim | **PASS** |
| Signature Ed25519 live (`/auth/challenge`+`/verify` → `sess_`) | **PASS** (`wallet_name=vgactech2`) |
| Clé API `artcb_` acceptée (`/api-keys/me` 200, scopes r/w/m/admin) | **PASS** (accès API seulement) |
| Liaison cryptographique classique ↔ PQC (`hybrid_address_v2(ed,pqc)`) | **NOT_PROVEN** (pas de `pqc_public_key` exposée sur endpoints audités) |
| Contrôle de la clé privée PQC (signature ML-DSA) | **NOT_PROVEN** |
| Liaison machine / TPM / EK | **NOT_PROVEN** |
| UNIQUE_HUMAN | **false** |
| Hex64 = commit Git | **FAIL_AS_GIT** (correctement refusé) |

## Verdict

```text
IDENTITY_PARTIAL
  ed25519_control_proven = true
  pqc_control_proven     = false
  machine_bound_proven   = false
  wallet_certified       = false
```

Présence d’une adresse `artcb2` **≠** preuve de contrôle PQC.  
SHA code ×4 (R349b) **≠** réplication d’état wallet/USER↔NODE.

## Suite utile (sans secrets)

1. Endpoint (ou export signé) de `pqc_public_key_hex` + recompute `address_v2`.  
2. Challenge ML-DSA signé pour `address_v2`.  
3. USER↔WALLET ownership layer (R349) distinct de USER↔NODE (R348b LOCAL_NODE).  
4. Ne plus coller seed / `artcb_` dans le chat.
