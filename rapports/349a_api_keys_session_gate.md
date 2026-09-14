# R349a — API keys session gate (UX + client fix)

**UTC:** 2026-09-14T18:10:00Z  
**CERTIFIED_100:** false

## Accord R348b

Accepté : LOCAL_NODE · REPLICATED_PROTOCOL = cible · UNIQUE_HUMAN=false.

## Bug corrigé

1. `listApiKeys` / `generate` / `revoke` **n’envoyaient pas** `Authorization: Bearer sess_…` → 401 systématique possible même connecté.
2. UI montrait « 0 clé » après 401 (état initial `[]`).

## Fix

- `sessionHeaders()` sur les 3 appels
- Gate UI : pas de session → pas de formulaire génération ; liste = « non chargées » ≠ 0
- Lien Portefeuilles ; TTL défaut 7 j ; wording Cursor assoupli (accès API ≠ humain)

## Non fait ce tour

R349 USER↔WALLET ownership · REPLICATED_PROTOCOL multi-nœud · ne pas recréer vgactech2
