# 273 — Binding NodeID ↔ clé + quorum NEW-VIEW

Horodatage : 2026-09-08T22:57:22Z  
CERTIFIED_100 : **false**  
PRODUCTION_READY : **false**  
N04 50 % : **FAIL** (non recasté)

## Ce que R272 a vraiment corrigé

Même vue + digest distinct = **409 equivocation** (volontaire, pas un bug).  
Prepared X après VIEW-CHANGE = X obligatoire, Y = `must_repropose_prepared`.  
Ce correctif n’est pas du maquillage.

## P0 fermés dans le code (cette PR)

1. **Identité.** `verify_signed` / `verify_view_change` / `verify_new_view` / `verify_attest` vérifient la signature avec la clé **attendue** pour le NodeID (`src/artcb/consensus/official_replica_keys.json`), pas avec `producer_*` fourni par l’émetteur.
2. **NEW-VIEW.** `select_new_view_value()` exige un quorum de VIEW-CHANGE (Q=3) avant de retenir un prepared. Un certificat prepared valide dans **un seul** VC n’est plus sélectionnable.
3. **Fail-closed.** Si un VC vérifié **réclame** un prepared qui n’est pas reconstructible, ou s’il n’y a pas quorum alors qu’un prepared est réclamé → `state_incomplete` (pas de Y silencieux).
4. **Runner.** Les tentatives healthy R272 conservent `attempts[]` + `PASS_AFTER_RECOVERY` au lieu d’un `ok:true` plat.
5. **Artefacts.** `logs/campaigns/<id>/manifest.json` + `MANIFEST.sha256` + dumps nœud.

IP / hostname / `ARTCB_NODE_ID` restent une étiquette de déploiement. Ils ne sont pas l’autorité cryptographique.

## Tests logiciels

`pytest tests/test_e2e273_identity_binding.py tests/test_e2e273_new_view_quorum.py` (+ suites 263/264/265/272) : **PASS**.

- A1 clé correcte → accepté  
- A3/A7 K(ovh-1) + `replica_id=ovh-node-2` → `invalid_replica_key_binding`  
- même attaque sur tip-attest → rejeté  
- 1 VIEW-CHANGE → prepared non sélectionné  
- Q VIEW-CHANGE → prepared le plus haut retenu  
- prepared réclamé non reconstructible → `state_incomplete`

Ces tests utilisent un registre de test. Ils ne certifient **pas** les TPM/clés des 4 VMs.

## Mesure live sur `main` actuel (avant déploiement de 273)

SHA live ×4 : `d9eba2ac2bc8af954e31453da584802394735a69` = `origin/main`  
Hauteur **1130** tip `49dd849a33bd68f4206ad8a4fa4de66faafd36504eed71711e4bcab2bc94d941` view **15**  
Clés publiques tip-attest = registre commité (`key_match` ×4).

Attaque A3 : OVH1 signe `P|15|500|aa…|ovh-node-2` avec **K1**, POST `/pbft/prepare` vers nœuds 2/3/4.

| Nœud | HTTP | reason | Couche identité |
|------|------|--------|-----------------|
| ovh-node-2 | 200 | `not_accepted` | **passée** (GAP) |
| aws-node-3 | 200 | `not_accepted` | **passée** (GAP) |
| ovh-node-4 | 200 | `not_accepted` | **passée** (GAP) |

`not_accepted` = digest pas dans `accepted[]`. Ce n’est **pas** un rejet d’identité.  
`verify_prepare` a traité K1 comme une voix `ovh-node-2`.

Verdict live : **GAP** (pas BOUND). Après merge + follow-main ×4, le même runner doit afficher **409 `invalid_replica_key_binding`**. Tant que ce n’est pas mesuré sur le nouveau SHA, A3 live n’est pas PASS.

Preuve primaire : `logs/273_identity_20260908T225711Z.json`  
Campagne : `logs/campaigns/273_20260908T225711Z/` SHA256 manifest `dc1cb5f870eba4007752b947ae2ec39108b649fd18156f9621a1aff4d62c9e5c`

## Ce qui n’est pas certifié

- CERTIFIED_100  
- N04 50 %  
- N06/N08/C03/A02/X03 isolés après 50 %  
- C04 thousands  
- TPM / certificat matériel / révocation live (A4–A8)  
- 43/43 sur un seul SHA  

Le 409 d’équivocation même-vue reste le résultat correct. R272 n’est pas remis en cause.
