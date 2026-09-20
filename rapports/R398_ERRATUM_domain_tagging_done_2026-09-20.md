# ERRATUM R398 — Section "TASK-RULES-DOMAINS RESTE À FAIRE" obsolète
**Date :** 2026-09-20T22:45:00Z  
**SHA HEAD :** 4df65a4 (main)  
**Rapport corrigé :** `rapports/R398_audit_6_domaines_cartographie_2026-09-20.md`  
**Détecté par :** audit expert GitHub (synchronisation post-R398)

---

## Anomalie documentaire constatée

Le rapport R398 (Domaine 6) affirmait :

> *"Les CR-* sont dans `rule_corpus_index.json` mais sans `domain` tag. Les domaines prévus : CRYPTO_PQC, BIOMETRIE, CONSENSUS_BFT…"*
> *"TASK-RULES-DOMAINS : RESTE À FAIRE"*

**C'est incorrect.** La vérification directe sur HEAD `4df65a4` démontre que la classification est **déjà présente et complète**.

---

## Vérification réelle (HEAD 4df65a4)

```python
total = 230
with_domain = 230   # 100% des entrées ont un domain
domain_classified_by = "artcb_r393_v2"
domain_classification_version = "R393-v2-R394E"
```

### Distribution des domaines (230 CR-*)

| Domaine | Count |
|---------|-------|
| PROTOCOL | 96 |
| GOVERNANCE | 48 |
| LESSONS | 44 |
| NETWORK | 39 |
| TESTING | 1 |
| ROADMAP | 1 |
| IDENTITY | 1 |

### Champs présents par entrée

Chaque entrée CR-* contient déjà :
- `domain` — domaine principal (ex: `"PROTOCOL"`)
- `primary_domain` — alias
- `domains` — liste (potentiellement multi-domaine)
- `confidence` — score de classification
- `classification_basis` — liste des critères utilisés
- `domain_classified_by` — `"artcb_r393_v2"`
- `domain_classified_ts` — timestamp nanoseconde

---

## Cause de l'erreur

Le rapport R398 a été rédigé en s'appuyant sur le rapport R375/R381 (qui documentait une limite réelle à l'époque), **sans vérifier l'état actuel du fichier** `rule_corpus_index.json`.

Entre R381 et R398, R393 a exécuté la classification de domaine (`artcb_r393_v2`) et mis à jour les 230 entrées. R398 n'a pas lu le fichier avant de déclarer ce chantier "ouvert".

---

## AVANT / APRÈS

**AVANT (R398 section Domaine 6, ligne ~165 du rapport) :**
```
TASK-RULES-DOMAINS : RESTE À FAIRE
  script à créer : scripts/artcb_r399_domain_tagging.py
  ajouter champ "domain" dans chaque entrée CR-*
  45% — domaines non encore organisés ❌
```

**APRÈS (état réel HEAD 4df65a4) :**
```
TASK-RULES-DOMAINS : DONE_VERIFIED
  230/230 CR-* avec domain + classification_basis
  domain_classification_version = R393-v2-R394E
  classifier = artcb_r393_v2
  ~60% pour ce sous-domaine (9 catégories vs 7 actuelles)
```

---

## Note honnête sur les limites restantes

La classification R393v2 utilise **7 domaines** (PROTOCOL, GOVERNANCE, LESSONS, NETWORK, TESTING, ROADMAP, IDENTITY). Les 9 domaines décrits dans R398 (CRYPTO_PQC, BIOMETRIE, CONSENSUS_BFT, TOKENOMICS, IDENTITE_HUMAINE, RESEAU_P2P, FORENSIC_TRACE, FRONTEND_UX, PROTOCOLE_AGENT) sont plus granulaires et ne correspondent pas exactement.

Ce qui **reste réellement ouvert** dans ce domaine :
1. Mapping R393v2 domains → granularité 9 catégories (non critique — refactoring sémantique)
2. `agent_id=Bob/Cursor` absent des compteurs (limites documentées R375)

Ces points sont **OPEN mais non critiques** — ne pas les recréer en tant que TASK principale.

---

## Règle L-055 dérivée

**Ne jamais déclarer une tâche "RESTE À FAIRE" sans avoir vérifié le fichier concerné sur le HEAD actuel.**  
Un rapport décrivant un état antérieur ≠ état actuel du dépôt.  
Toujours lire `git log --oneline -10` + le fichier cible avant de rédiger la section "RESTE".

**Action :** Erratum R398 enregistré. `TASK-RULES-DOMAINS` retirée de la file OPEN. `CERTIFIED_100=false`.
