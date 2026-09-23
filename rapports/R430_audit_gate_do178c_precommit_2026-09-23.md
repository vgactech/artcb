# R430 — Audit et spécification du gate DO-178C-inspired / pre-commit

**Date :** 2026-09-23 UTC  
**SHA HEAD audité :** `c624f12273cdd58a1e1f63fb311ed62bfb43a2e7`  
**CERTIFIED_100 :** false  
**Type :** audit + spécification — aucun code hors `rapports/` modifié par R430  
**Avancement R430 :** audit terminé, implémentation NON effectuée

## 0. Expertises mobilisées

- audit Git/GitHub et intégrité des références SHA ;
- ingénierie logicielle / Git hooks ;
- CI/CD et gates de qualité ;
- traçabilité et configuration management ;
- assurance qualité logicielle inspirée de DO-178C ;
- sécurité de chaîne de développement ;
- audit forensic et versioning ;
- analyse de cohérence SPEC → CODE → TESTS → EVIDENCE ;
- architecture ARTCB / ARTCD.

## 1. Synchronisation GitHub

Le dépôt public `vgactech/artcb` a été relu sur `main`. Le HEAD courant est `c624f12273cdd58a1e1f63fb311ed62bfb43a2e7`, avec les commits R428 puis R429 et enfin R429-fp.

Le commit immédiatement précédent R429 est `e2e5cfb` et `c624f12` est le fingerprint régénéré sur ce HEAD. Le dépôt est donc plus récent que les rapports R415/R416/R417/R423 qui utilisaient des SHA antérieurs.

## 2. Question R430

Objectif demandé :

> Transformer la traçabilité/versioning existants en un gate automatique capable de bloquer une modification non conforme avant qu'elle puisse être considérée comme valide.

Important : « inspiré de DO-178C » ne signifie pas « conforme DO-178C ». R417 a correctement durci cette formulation. R430 ne revendique aucune certification DO-178C.

## 3. Processus actuel

### 3.1 Versioning

ARTCB possède déjà :

- `scripts/artcb_r405_precommit_hook.sh`
- `scripts/artcb_r405_install_precommit_hook.py`
- `scripts/artcb_bump_module_version.py`
- `Makefile: install-hooks`
- `Makefile: check-hooks`

Le hook détecte les fichiers Python stagés contenant `MODULE_VERSION`, incrémente PATCH et re-stage le fichier.

### 3.2 Limite critique

Le hook R405 est explicitement **FAIL-OPEN** :

- si le script de bump manque, le commit continue ;
- si le bump échoue, le commit continue ;
- `exit 0` est utilisé dans tous les cas ;
- `.git/hooks/` n'est pas versionné ;
- un nouveau clone n'a pas automatiquement le hook ;
- `git commit --no-verify` peut contourner un hook local.

Donc :

**R405 = automatisation de versioning, pas gate de sécurité bloquant.**

## 4. Problème R430

Le système actuel peut produire la situation suivante :

```
modification de code
      ↓
hook absent OU erreur du hook
      ↓
commit quand même accepté
      ↓
MODULE_VERSION / preuve / tests potentiellement non conformes
```

C'est incompatible avec l'objectif « sécuriser tous les chantiers suivants » si la conformité doit être obligatoire.

Autre problème : le ledger `.artcb/task_ledger.yaml` actuellement visible sur `main` porte encore des métadonnées historiques (`git_head: 7a6c04f`) alors que le HEAD réel est `c624f12...`. Cette divergence ne doit pas être silencieusement considérée comme une preuve à jour.

## 5. Solution R430 proposée

### Niveau A — Gate local versionné

Créer un mécanisme versionné dans le dépôt, par exemple :

```
.githooks/pre-commit
scripts/artcb_r430_gate.py
tests/test_r430_gate.py
```

et configurer le clone avec :

```
git config core.hooksPath .githooks
```

Le hook ne doit plus dépendre d'un fichier invisible dans `.git/hooks/`.

### Niveau B — Séparation « auto-correction » / « gate »

Le bump automatique et le gate ne doivent pas être la même fonction.

```
R405
  → corrige automatiquement MODULE_VERSION

R430
  → vérifie que l'état final est conforme
  → FAIL-CLOSED si la preuve obligatoire manque
```

C'est-à-dire : R430 ne doit pas simplement dire « j'ai essayé de corriger ». Il doit vérifier le résultat après correction.

### Niveau C — Contrôles minimaux

Pour une modification de code/configuration :

1. dépôt Git dans un état attendu ;
2. référence HEAD identifiable ;
3. `MODULE_VERSION` présent lorsque requis ;
4. version modifiée cohérente avec la modification ;
5. fingerprint/artefact L-053 cohérent lorsqu'il est exigé ;
6. tests ciblés associés au chantier ;
7. aucun secret détecté dans le diff ;
8. rapport correspondant présent pour un chantier Rxxx ;
9. aucune déclaration `PASS` sans artefact vérifiable ;
10. distinction `DONE_REPORTED` / `DONE_VERIFIED` conservée ;
11. aucune revendication `CERTIFIED_100=true` sans gate dédié ;
12. journal forensic disponible pour l'opération de développement.

## 6. Ce que R430 ne doit PAS faire

R430 ne doit pas :

- prétendre fournir une certification DO-178C ;
- considérer un simple log comme une preuve suffisante ;
- bloquer arbitrairement les modifications de rapports ;
- supprimer l'historique du ledger ;
- réécrire les anciens rapports ;
- modifier automatiquement le code métier ;
- transformer un test local en preuve live ;
- considérer `PASS` comme équivalent à certification globale.

## 7. CI : gap important

La recherche du dépôt montre que le workflow `tests.yml` a historiquement été utilisé en mode manuel (`workflow_dispatch`) plutôt qu'en CI automatique sur chaque push.

Donc un pre-commit seul ne peut pas constituer la dernière ligne de défense.

Architecture recommandée :

```
                 modification
                      │
             ┌────────▼────────┐
             │ R430 local gate │
             └────────┬────────┘
                      │
                 git commit
                      │
             ┌────────▼────────┐
             │ GitHub CI gate  │
             └────────┬────────┘
                      │
                required check
                      │
             ┌────────▼────────┐
             │ merge autorisé  │
             └─────────────────┘
```

Le CI doit être l'autorité finale, car un hook local peut être absent ou contourné.

## 8. Politique fail-closed proposée

### Bloquant

- gate absent ;
- contrôle critique en échec ;
- test obligatoire en échec ;
- preuve attendue absente ;
- divergence de SHA critique ;
- fingerprint explicitement requis mais incohérent ;
- secret détecté ;
- artefact déclaré PASS mais invalide ;
- tentative de déclarer une certification non démontrée.

### Non bloquant / warning

- simple modification documentaire ;
- artefact historique explicitement marqué historique ;
- benchmark informatif non requis par le chantier ;
- amélioration non critique.

## 9. Preuves nécessaires pour R430

Le futur gate doit produire un artefact versionné du type :

```
reports/r430_gate_result.json
```

avec au minimum :

```json
{
  "gate": "R430",
  "git_sha": "<HEAD>",
  "status": "PASS|FAIL",
  "checks": [],
  "tests": [],
  "fingerprint_status": "...",
  "secret_scan": "...",
  "module_version_status": "...",
  "report_status": "...",
  "timestamp_ns": 0
}
```

Le principe important est que le résultat soit **auditable après coup**, et pas uniquement affiché dans le terminal.

## 10. Tests R430 à prévoir

Minimum :

- absence du hook ;
- hook installé ;
- hook versionné ;
- fichier Python avec MODULE_VERSION ;
- fichier Python sans MODULE_VERSION ;
- bump réussi ;
- bump échoué ;
- tentative `--no-verify` ;
- modification de code sans rapport ;
- rapport sans code ;
- fingerprint périmé ;
- fingerprint à jour ;
- secret détecté ;
- test obligatoire échoué ;
- test obligatoire réussi ;
- résultat PASS falsifié ;
- HEAD divergent du ledger ;
- distinction historique/current SHA ;
- réexécution idempotente du gate.

## 11. Tâches précédentes à maintenir en parallèle

R430 ne ferme pas les chantiers déjà ouverts.

### P0 / sécurité-identité

- FHE réel pour `check_uniqueness()` ;
- FAR/FRR/PAD sur vrais capteurs ;
- tests SDK iOS/Android ;
- distinction biométrie/PIN/WebAuthn ;
- anti-Sybil multi-appareil.

### ARTCD

- G4 : `src/artcb/ir/reasoning.py` — moteur de déduction natif ;
- G5 : vocabulaire canonique complet ;
- G1 : test texte → ConceptID → KCG → PoL → bloc ;
- G3/L10 : test réel A sur nœud 1 ↔ B sur nœud 2.

R429 confirme que G16 cross-language a maintenant 17/17 tests PASS sur son périmètre, mais cela ne ferme pas G4/G10-G20.

### Consensus / exploitation

- validation live de la politique creator-node ;
- scénario panne réelle du nœud créateur ;
- validation view-change live ;
- retrait réel d'un nœud après panne permanente.

## 12. Conclusion R430

### État actuel

**R430 n'est PAS encore implémenté.**

Ce qui existe :

- versioning automatique R405 ;
- installation reproductible R406 ;
- forensic nanoseconde ;
- auto-feedback ;
- preflight logiciel ;
- ledger persistant.

Ce qui manque pour appeler cela un **gate R430** :

1. contrôle bloquant explicite ;
2. hook versionné utilisé par défaut ;
3. séparation correction/versioning ↔ validation ;
4. artefact de résultat du gate ;
5. tests adversariaux du gate ;
6. gate CI automatique ;
7. protection contre l'absence du hook local ;
8. cohérence systématique SHA/artefacts/rapports.

### Décision

**R430 = AUDIT COMPLET / SPÉCIFICATION VALIDÉE, CODE NON MODIFIÉ.**

La prochaine implémentation autorisée doit être limitée au chantier R430 et documentée dans un rapport suivant ; aucun autre code ARTCB ne doit être modifié dans le cadre de cet audit.

**CERTIFIED_100 = false.**
