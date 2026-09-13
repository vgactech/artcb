# R335 — Où sont les clés, pourquoi SSH≠HTTPS, % avancement (2026-09-13T17:41:26Z)

## Verdict

`CERTIFIED_100=false` · avancement estimé **~58 %** des lignes P0 déclarées (pas 100 %).

Après sleep Mac + recharge : SHA live **`25faa42102a4` ×4 seeds** (+ Mac `127.0.0.1:8001` même SHA). Tip ingest prompt bloc **1166** ; ReasoningID ancre **1167**.

## Le 401 n’est pas « il manque trois clés dans le shell »

| Couche | Rôle | État mesuré ce tour |
|--------|------|---------------------|
| `artcb-blockchain` / `dev` | secrets **partagés** (Stripe, Bob, GitHub, clé opérateur ovh1) | OK pour artcb.me writes |
| `artcb-2` / `artcb3` / `artcb-4` | Doppler **par nœud** | étaient **vides** (meta Doppler only) — **cause racine** du 401 write |
| Cursor `KEY_API_ARTCB_DOPPLER_2/3/4` | tokens service Cursor → projets nœud | absents de ce shell agent |
| `DOPPLER_TOKEN` injecté Cursor | souvent `dp.st…` **Invalid Auth** | **empoisonne** le CLI tant qu’il n’est pas `unset` |
| Doppler CLI `~/.doppler` (personal) | gère tous les projets | OK **après** `unset DOPPLER_TOKEN` |
| `~/.artcb/nodes/{ovh-node-2,aws-node-3,ovh-node-4}.env` | cache opérateur local 0600 | **recréé** ce tour (clés provisionnées) |
| VM `/etc/artcb/doppler.env` | token service sur la machine | inaccessible sans SSH :22 |
| Processus artcb VM | `doppler run` au start | **n’a pas encore** les nouvelles clés tant que pas de restart |

Action faite : `ARTCB_API_KEY` + `ARTCB_NODE_ID` **posés** dans Doppler `artcb-2`/`artcb3`/`artcb-4` (prd **et** dev).  
Contournement protocole (meilleur que « 3 clés magiques ») : **`POST /api/v1/concepts/fanout`** → peer-ingest signé replica → n2/n3/n4 **HTTP 200** (`peers_ok=3`, `c2d_five_store_fanout_pass=true`).

Direct `POST /concepts/publish` avec Bearer ovh1 ou clé locale **reste 401** sur n2–n4 jusqu’au reload VM — **attendu** (`require_write_actor` = clé locale **du** nœud).

## Pourquoi GitHub / Doppler / Cursor / Chrome « marchent » et pas SSH ARTCB

Mesure LAN ce tour :

| Cible | :22 | :443 |
|-------|-----|------|
| github.com | CLOSED | OPEN |
| 152.228.144.34 (ovh1) | CLOSED | OPEN |
| 151.80.107.29 (ovh2) | CLOSED | — |
| 13.38.209.25 (aws3) | CLOSED | — |
| 91.134.45.8 (ovh4) | CLOSED | — |

Leur solution : **HTTPS (et API cloud)**, pas SSH vers les VMs. `git` vers GitHub = HTTPS ; Doppler = HTTPS API ; Cursor = HTTPS ; Chrome = HTTPS.  
ARTCB health/API = HTTPS `*.artcb.me:443` → **ça marche**.  
Netem N04 / `systemctl` / lecture `/etc/artcb/doppler.env` = **SSH :22** → **fermé depuis ce LAN**. Clés SSH `~/.ssh/artcb_*` présentes ≠ port ouvert.

## Machine éteinte / sleep

Session brew **restaurée** 12 sept 23:09 — install swtpm **coupée** (`[y/n]` puis typo `swtpmy`).  
Après rallumage : Mac artcb UP (`launchd me.artcb.node`, SHA aligné). IP LAN **changée** `10.234.49.2` → `10.5.21.208` (timeout sur ancienne IP). Utiliser `127.0.0.1:8001` en local.

## swtpm

`brew install swtpm` **FAIL** sur macOS 12 (dépendance `gobject-introspection` / pip). Guest swtpm ≠ NitroTPM AWS. Reste **NOT_PROVEN** pour L3 Mac.

## % avancement (honnête)

| Panier | ~% du panier | Commentaire |
|--------|-------------|-------------|
| Tip public / split ledger | ~80 % | PASS_LIVE historique |
| #77 identité / NV | ~65 % | A3/A7 PASS ; N04 FAIL (SSH) |
| #86 VC/restart/pollution | ~70 % | auto VC + Mac restart mesurés ; ORG multi-controller suite |
| Langage / C2-D | ~75 % | resolve + **fanout replica PASS** ce tour |
| ReasoningID R334 | ~70 % | T1–T12 + ancre live ; pas CoT privé |
| TPM / C04 / hole 716 | ~15 % | profil / SSH / trou seed |
| **CERTIFIED_100** | **0 %** | false tant que critiques ouvertes |
| **Global P0 déclaré** | **~58 %** | pondération matrice |

## Artefacts

- `logs/R334/measurement.json` (`fanout_writes_x4=true`)
- `logs/322_c2d_multihote_latest.json`
- Doppler projects provisionnés (valeurs hors git)
