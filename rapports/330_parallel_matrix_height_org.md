# Rapport 330 — Pilotage parallèle + height() audit + ORG commitment probe

**Date:** 2026-09-12T20:15:00Z  
**SHA code:** *(après push)*  
**CERTIFIED_100:** `false`  
**Issues:** #77 OPEN · #86 OPEN (ne pas clôturer)

## Méthode

Nouveau chantier **ajoute** une ligne au registre `CERTIFICATION_MATRIX_ARTCB.md`.  
R273/#77 et R328/#86 restent ouverts. PASS = tied to SHA.

## R330-E — `height()`

Script : `scripts/artcb_r330_height_audit.py` → `logs/R330/height_audit.json`.

Correctifs ce tour :
- `pbft/client-request` : fallback n’utilise plus `height()` quand split actif.
- `tip_attest.attest_tip` : signe le **tip public**, expose `height_total_legacy` séparément.

Sites encore `RISK_CONSENSUS` : P2P `local_height` / official_replica — à traiter avant de les utiliser comme tip PBFT.

## R330-A — ORG live (déclaratif ≠ exécuté)

Probe : `scripts/artcb_r330_org_commitment_probe.py`  
Mesure projections `/authz/orgs` ×4 + tip public.  
**Ne prouve pas** la copie du body ORG entre nœuds (`authorized_nodes ≠ copied`).

## Suite parallèle (backlog inchangé)

1. #77 rejouer binding NodeID↔clé sur SHA courant  
2. #86 auto VC + restart live  
3. R330-A body export/import hash multi-node  
4. R330-B/C/D isolation distribuée + pollution  
5. Nettoyer RISK_CONSENSUS P2P

## Certification

`four_layer_certified=false` · `CERTIFIED_100=false`
