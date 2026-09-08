# 277 — Issue #77 live after R273 is actually deployed

Horodatage : 2026-09-08T23:30:12Z (campagne) / 2026-09-08T23:35:42Z (partition + crash)  
CERTIFIED_100 : **false**  
PRODUCTION_READY : **false**  
N04 50 % : **FAIL** (non recasté)

Le rapport Cursor n’est pas la preuve. Les preuves sont les JSON bruts.

## Ce que cette campagne prouve — et ce qu’elle ne prouve pas

| Affirmation | Verdict |
|---|---|
| A. Le code contient la correction R273 | Oui (PR #76 mergée, plus `41c9e1dd`) |
| B. Les tests logiciels reproduisent la correction | Oui (15 pytest) |
| C. Les quatre machines réelles exécutent cette correction | **Oui** — SHA `41c9e1dd` ×4 = `origin/main`, `binding_enforced=true` ×4 |
| D. Le réseau réel est certifié / production ready | **Non** |

`payload.ok=true` dans le JSON 277 signifie seulement : SHA×4 + binding + A3 + A7. Ce n’est **pas** `CERTIFIED_100`.

## Phase 1 — déploiement

SHA déployé et mesuré :

`41c9e1dd4e142b884ab5f99f37430f63b4ad070a` ×4 = `origin/main`

Livre non vidé : `blocks.jsonl` = **1133** lignes sur les 4 nœuds.  
Tip live : `cc0bf8a1053c7ae75c3c00b0a4ebf72da311efbf1f13e3164a95f159fc7d71b3`  
Hauteur **1133** · view **15** · primary `ovh-node-4` · `chain_valid` ×4

Ingest du prompt de ce tour : **sauté** (`ingest_http=409` `equivocation`). Le prompt n’est pas on-chain.

## Phase 2 — identité live (après déploiement, pas le GAP pré-R273)

Pré-déploiement (SHA `d9eba2ac`, campagne `273_20260908T225711Z`) : K1 déclaré `ovh-node-2` → HTTP **200** `not_accepted`, `verify_prepare` passé = **GAP**. Ce résultat reste un GAP. Il n’est pas recasté.

Sur SHA `41c9e1dd` :

| Test | Attendu | Mesure | Statut |
|---|---|---|---|
| A1 K1 + Node1 | identité acceptée | HTTP 200 `not_accepted` ×3 (digest hors accepted) | **PASS** identité |
| A3 K1 + Node2 | 409 binding | 409 `invalid_replica_key_binding` ×3 | **PASS / BOUND** |
| A7 K2 + Node1 | 409 binding | 409 `invalid_replica_key_binding` ×3 | **PASS / BOUND** |
| clé inconnue | reject | 409 binding ×3 | **PASS** |
| signature invalide (bon NodeID+clé) | reject crypto | 200 `invalid_prepare` ×3 | **PASS** |
| `producer_*` = clé de Node2 sur message Node1 | reject | 409 binding ×3 | **PASS** |
| replay ancienne sig + nouveau NodeID | reject | 409 binding ×3 | **PASS** |

HTTP 200 `not_accepted` n’est un PASS **que** pour A1 (identité correcte, message hors log). Pour A3 ce serait encore un GAP.

## Phase 3 — NEW-VIEW live (sans ChainManager / liboqs, sans bind)

Endpoint lu : `POST /api/v1/consensus/pbft/analyze-new-view` (analyse seule, `bound=false`).

| Entrée | quorum_ok | selected | reason | Statut |
|---|---|---|---|---|
| 1 VC honnête | false | null | ok | **PASS** |
| 2 VC honnêtes | false | null | ok | **PASS** |
| 3 VC honnêtes, prepared vide | true (ids ovh-1, ovh-2, aws-3) | null | `no_prepared` | **PASS** |
| 1 VC + prepared non reconstructible | false | null | `state_incomplete` | **PASS** |
| 3 VC + prepared non reconstructible | true | null | `state_incomplete` | **PASS** |
| 3 VC signés par K1 sous 3 NodeID | false | null | `state_incomplete` | **PASS** |

`select-prepared` avec 3 VC honnêtes vides : `chosen=null`, `bound.reason=no_prepared`. Aucun prepared n’a été installé.

## Phase 4 — combinés

| Scénario | Mesure | Statut |
|---|---|---|
| identité forgée + VIEW-CHANGE 265 | `invalid_view_change_265` ×4 | **PASS** (rejet message ; le binding est prouvé par l’analyse NEW-VIEW) |
| identité forgée + NEW-VIEW | quorum_ok=false, `state_incomplete` | **PASS** |
| partition 2–2 (8 s) | un seul tip `cc0bf8a1…`, pas de double finalité | **PASS** safety |
| crash ovh-2 + A3 | 409 binding sur aws-3 et ovh-4 pendant l’arrêt | identité **mesurée** ; statut script **FAIL** car health ovh-2 encore HTTP 0 au snap immédiat ; ovh-2 **active** ensuite |
| latence / reorder / asymétrie isolées | non rejouées ici | **NOT_PROVEN** |

## N04 50 %

Isolé : netem `loss 50%` sur ovh-2 / aws-3 / ovh-4 (ovh-1 restait joignable).  
Propose via ovh-1 (primary réel = ovh-4) → HTTP **409** `not_primary`.  
**FAIL.** La ligne N04 n’est pas PASS. Les PASS 1–30 % de R272 (`3286996`) ne s’appliquent pas à ce SHA.

## A4–A8 / TPM / C04

| Ligne | Statut | Pourquoi |
|---|---|---|
| A4–A8 live (révocation / expiration / downgrade du service) | **NOT_PROVEN** | registre live `revoked=false` ×4 ; overlay process-local OVH1 refuse bien `replica_key_revoked` mais **ne mute pas** l’API |
| TPM quote | **NOT_PROVEN** | `/dev/tpm0` **absent** ×4 ; pas d’outils tpm2 ; le registre public ≠ quote |
| C04 milliers | **NOT_PROVEN** | non exécuté ; un substitut court est interdit |

## Artefacts

- `logs/277_issue77_20260908T233012Z.json`
- `logs/277_issue77_latest.json`
- `logs/277_issue77_combo_extra.json`
- `logs/campaigns/277_20260908T233012Z/manifest.json`
- `MANIFEST.sha256` = `951e16fdcad86c557f5921b93fdd549cc117b423d930ebc43a072ef1ad73acc2`
- GAP pré-déploiement : `logs/campaigns/273_20260908T225711Z/`

## Après campagne

artcb **active** ×4 · iptables artcb261–266/271 **0** · netem **0** · height **1133** · SHA `41c9e1dd` ×4  
Pas de wipe. AWS reste t3.small. HPC interdit.

**PBFT 100 % = NON CERTIFIÉ.**
