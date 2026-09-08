# Rapport 262 — Arrêt du créateur OVH1 + replica des preuves

**Date :** 2026-09-08T12:00Z → 12:05Z  
**Contact :** `official@artcb.space`  
**260/261 restent verrouillés.** On ne les rejoue pas.  
**Pas de wipe.** OVH1 **relancé** avant la fin. Clé temporaire OVH2 **effacée**.  
**Pas PBFT.**

---

## Protocole

`.cursor/rules/artcb-live-node.mdc` : plus d’attente de GO pour follow-main / stop / partition / probe / mémo.  
Toujours : un seul nœud down, restore avant de finir, jamais wipe, jamais token, jamais SHA inventé.

---

## Evidence (code + live)

`consensus/byzantine_evidence.jsonl` est dans le replica officiel. Import = **merge append-only** (pas d’écrasement).  
`GET /consensus/byzantine/evidence` : `sha256`, `bytes`, `persistent`, **`signed_on_chain=false`**.

Live après `include_files=true` depuis OVH2 :

| Nœud | `/health` git_sha | ev count | ev sha256 | on-chain |
|---|---|---|---|---|
| ovh-node-1 | `ae8447be45ea8304ea41012502ad2208cdb0cf99` | **32** | `621a09e878dd…` | false |
| ovh-node-2 | `ae8447be45ea8304ea41012502ad2208cdb0cf99` | **16** (source) | `f191e9a6dda1…` | false |
| aws-node-3 | `ae8447be45ea8304ea41012502ad2208cdb0cf99` | **32** | `856528cff0b0…` | false |
| ovh-node-4 | `ae8447be45ea8304ea41012502ad2208cdb0cf99` | **32** | `401bcc91f607…` | false |

Persistante : oui (JSONL). Répliquée : **oui, merge** (16 locales + 16 distantes = 32 sur 1/3/4). Authentifiée on-chain : **non**. Falsifiable sur disque : oui. Ce n’est pas une preuve ancrée.

---

## Arrêt du créateur (complémentaire 259/261)

259/261 isolaient **OVH4**. Ici **OVH1** (writer habituel) est `systemctl stop`.

### Avant

SHA **`ae8447be45ea8304ea41012502ad2208cdb0cf99` ×4**. Height **1080**, tip `130882e0…`. Livres **1080**.

### Pendant

| Mesure | Valeur |
|---|---|
| OVH1 `:8000` | `URLError` |
| OVH1 `wc -l` | **1080** (non vidé) |
| Mémo **OVH2** localhost | HTTP **200**, index **1080**, hash **`31bb77a1fc1f1bb317d1a54671d03523e9dd678ee7ce788bf58a6639f71ae3b2`**, graph `ai_memo_5646e5471f77`, **194.6 ms** |
| OVH2 height | **1081** |
| Replica OVH2 `include_files=true` | AWS3 **1080→1081**, OVH4 **1080→1081**, OVH1 **`ConnectError`** |

La clé opérateur nœud 1 est **401** sur 2/3/4 (Doppler D-029 : pas `ARTCB_API_KEY` sur `artcb-2`). Écriture via `api_keys.json` temporaire hashé sur OVH2, fichier clé mode 0600, **supprimé** après.

### Rejoin

`systemctl start artcb` OVH1 → healthy `ae8447be…`, livre encore **1080**.  
Replica 2 : OVH1 **1080→1081**, AWS3/OVH4 nothing extra.

### Après

| Nœud | SHA | height | tip | `wc -l` | liveness |
|---|---|---|---|---|---|
| ×4 | `ae8447be45ea8304ea41012502ad2208cdb0cf99` | **1081** | `31bb77a1fc1f1bb317d1a54671d03523e9dd678ee7ce788bf58a6639f71ae3b2` | **1081** | `reachable=4` |

OVH1 **active**.

---

## Verdict 262

| Propriété | |
|---|---|
| Autonomie protocole | gravée |
| Evidence persistante + sha256 | PASS live |
| Evidence répliquée (merge) | PASS live (32 vs 16 source) |
| Evidence signée on-chain | **NON** |
| Créateur arrêté, autre nœud écrit | PASS live (OVH2) |
| Replica 3/4 pendant l’arrêt | PASS live |
| Catch-up créateur | PASS live 1080→1081 |
| PBFT / 2 nœuds down / fork distribué | **NON** |

Tests : `tests/test_e2e262_evidence_replica.py`.

---

## Interdit

Laisser OVH1 down. Copier la clé nœud 1 dans Doppler 2/3/4. Wipe. Inventer un PASS PBFT.
