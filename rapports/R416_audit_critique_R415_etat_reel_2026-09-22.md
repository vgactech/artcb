# R416 — Audit critique R415 / état réellement vérifié

**Date :** 2026-09-22  
**Référentiel audité :** `main`  
**HEAD audité :** `d05a615916be9af724cc41339632f99927707659`  
**Commit R415 :** `d05a615916be9af724cc41339632f99927707659`  
**Certification globale :** non déduite / `certified_distributed_mainnet` doit rester gouvernée par son gate et les preuves exigées.  
**Modification du code produit :** AUCUNE dans ce rapport. Seul ce rapport est ajouté dans `rapports/`.

---

## 1. Expertises mobilisées

- audit Git/GitHub et vérification de SHA ;
- audit logiciel Python/TypeScript ;
- forensic logging et traçabilité ;
- DevOps / Git hooks / CI-CD ;
- architecture blockchain, consensus et validation distribuée ;
- analyse de spécification versus implémentation versus preuve live ;
- cryptographie appliquée et biométrie ;
- tokenomics / PoL ;
- gouvernance du rule corpus ;
- méthodologie de certification et gestion des preuves.

---

# 2. Processus d'audit

Le dépôt a été vérifié avant conclusion sur le commit réellement présent en tête de `main`.

Le dernier commit retourné par GitHub est bien R415 : `d05a615916be9af724cc41339632f99927707659`.

Le commit R415 modifie principalement `frontend/src/i18n/translations.ts` pour retirer des clés de navigation et d'AgentMemory devenues orphelines. Le diff GitHub confirme ces suppressions/commentaires dans plusieurs langues.

**Point méthodologique :** un rapport déclarant `DONE`, `PASS`, `ACTIF` ou `100 %` n'est jamais pris comme preuve suffisante lorsqu'une preuve versionnée indépendante est disponible.

---

# 3. Résultat immédiat

## 3.1 R415 existe réellement

Le commit existe sur GitHub avec le message :

`R415 — Nettoyage traductions orphelines P2P/AgentMemory (7 langues) + audit cartographie DO-178C/log forensic/versioning`

Le SHA est exactement :

`d05a615916be9af724cc41339632f99927707659`.

## 3.2 Le nettoyage frontend est réel

Le diff R415 retire/commentent notamment :

- `nav_network` ;
- `nav_agent_memory` ;
- `agent_memory_title` et plusieurs clés `agent_memory_*` ;
- dans les langues présentes dans `translations.ts`.

Cela confirme que la partie « nettoyage des clés orphelines » n'est pas seulement documentaire.

## 3.3 Mais « zéro régression TypeScript » n'est pas prouvé par le commit seul

Le commit est réel, mais l'état GitHub interrogé ne retourne aucun status CI associé à ce commit dans `get_commit_combined_status`.

Donc :

- **fait démontré :** le diff frontend existe ;
- **non démontré par cette vérification :** une exécution CI complète prouvant zéro régression TypeScript sur ce SHA précis.

Il faut donc remplacer, dans les futurs rapports, une formulation comme « zéro régression » par « diff appliqué ; CI TypeScript non indépendamment attestée sur ce SHA » tant qu'un artefact CI correspondant n'est pas disponible.

---

# 4. Correction importante : le versioning automatique existe comme mécanisme, mais le hook n'est pas versionné

R415 affirme que `.git/hooks/pre-commit` est actif automatiquement.

Le dépôt contient bien les composants R405 :

- `scripts/artcb_r405_precommit_hook.sh` ;
- `scripts/artcb_r405_install_precommit_hook.py` ;
- `tests/test_r405_precommit_hook.py`.

Le rapport R405 indique également **15/15 tests PASS** et décrit un test E2E dans lequel `MODULE_VERSION` passe de `2.0.0` à `2.0.1` après commit.

Cependant, le rapport R405 précise explicitement que `.git/hooks/` est **non tracké par Git** et qu'un nouveau clone doit exécuter le script d'installation.

### Conclusion

La formulation correcte est :

> **Le mécanisme de pre-commit auto-bump est implémenté et testé, mais son activation n'est pas une propriété intrinsèque d'un clone Git. Elle dépend de l'installation locale du hook.**

C'est important pour la reproductibilité : deux clones du même SHA peuvent avoir des états différents du répertoire `.git/hooks/`.

---

# 5. Correction importante : fingerprint SHA-256 R394 est actuellement antérieur au HEAD R415

Le fichier :

`logs/R394_module_fingerprints.json`

contient comme SHA de référence :

`9954a60`

alors que le HEAD actuel audité est :

`d05a615916be9af724cc41339632f99927707659`.

Le fichier indique donc une photographie de l'état des modules réalisée sur un ancien SHA.

Le dépôt contient par ailleurs la règle L-053 disant que le fingerprint doit être régénéré sur le SHA final avant push.

### Processus

Un fingerprint SHA-256 sert à produire une empreinte déterministe du contenu d'un module.

### Problème

Si le fichier de fingerprint est conservé avec une référence `git_sha` ancienne, il ne constitue plus une attestation cryptographique de l'état actuel du dépôt.

Même si R415 ne modifie que du frontend TypeScript et que certains fingerprints concernent uniquement les modules Python, le champ `git_sha` du manifeste n'est plus celui du HEAD final. Il faut donc distinguer :

- « fingerprint des modules à l'époque du SHA 9954a60 » ;
- « fingerprint attestant l'état du HEAD d05a615 ».

### Solution

Régénérer le fingerprint après le dernier commit destiné à être attesté, puis vérifier que le fichier enregistré contient le SHA final.

**Important :** ce rapport ne réalise pas cette modification, conformément à la règle de non-modification du code hors `rapports/`.

---

# 6. Auto-feedback rétro : la mécanique est bien présente

La recherche GitHub confirme :

- `scripts/artcb_r392_auto_feedback.py` existe ;
- `.bob/hooks/stop.py` appelle le script via `subprocess` ;
- les rapports RETRO générés existent dans `rapports/` ;
- R401 documente l'intégration `stop.py`.

### Conclusion

La déclaration « mécanisme présent et branché » est cohérente avec le dépôt.

La nuance à conserver est :

> le dépôt contient le hook et le script ; l'exécution automatique dépend de l'environnement Bob/IDE qui exécute effectivement `.bob/hooks/stop.py`.

Un fichier versionné ne prouve pas à lui seul qu'un runtime externe l'a exécuté lors de chaque tour.

---

# 7. Blocage des opérations destructrices : présent dans le dépôt

`.bob/hooks/pre_tool_use.py` existe et bloque notamment :

- écritures vers `blocks.jsonl` ;
- écritures vers `chain.key` ;
- écritures vers `genesis.json` ;
- `git reset --hard` ;
- `rm -rf data/` ;
- commandes de wipe de `blocks.jsonl`.

Le hook journalise également l'événement dans `data/trace/bob_pretooluse.jsonl`.

### Limite

C'est une protection au niveau du workflow/outillage Bob. Ce n'est pas une garantie de sécurité OS absolue contre un administrateur ou un processus disposant de privilèges système.

Il ne faut donc pas présenter ce mécanisme comme une barrière cryptographique ou comme une protection root-level.

---

# 8. Correction majeure sur DO-178C

R415 indique en substance que les principes DO-178C sont respectés, tout en reconnaissant que le formalisme complet DAL/MCDC/revue indépendante est hors scope MVP.

Cette formulation doit être durcie.

## Ce qui est réellement démontré

Le dépôt contient des mécanismes de :

- traçabilité ;
- versioning ;
- tests ;
- logs forensic ;
- séparation faits / preuves dans plusieurs rapports ;
- contrôles automatisés.

## Ce qui n'est pas démontré

Cela ne permet pas de conclure à une conformité DO-178C.

DO-178C est un cadre de développement et de certification logicielle aéronautique avec des objectifs et des activités structurés. L'existence de tests, de versioning et de logs ne suffit pas à déclarer une conformité.

### Formulation recommandée

> **« Des mécanismes d'assurance qualité inspirés de principes de traçabilité, vérification et contrôle de configuration sont présents. La conformité/certification DO-178C n'est pas revendiquée et reste hors scope. »**

Cette formulation est beaucoup plus rigoureuse.

---

# 9. Rule corpus : correction du nombre de types normatifs

R415 parle de « 7 types normatifs » puis énumère :

1. RULE
2. DECISION
3. SPEC
4. LESSON
5. CHECK
6. CONVENTION
7. QUESTION
8. EVIDENCE

Il y a donc **8 types**, pas 7.

Le dépôt confirme d'ailleurs cette structure dans `rules/rule_corpus_index.json` et le ledger :

`RULE=133, DECISION=47, LESSON=44, SPEC=2, CHECK=1, CONVENTION=1, QUESTION=1, EVIDENCE=1`.

Total :

`133 + 47 + 44 + 2 + 1 + 1 + 1 + 1 = 230`.

### Conclusion

Le corpus de 230 entrées est cohérent sur ce point, mais le texte de R415 doit dire **8 types normatifs**.

---

# 10. Cartographie des 230 règles : l'ancienne formulation « RESTE À FAIRE » est devenue incorrecte

Les documents R398/R401 et le ledger indiquent que les 230 CR-* ont déjà un `domain` / `primary_domain` et une classification par `artcb_r393_v2`.

La répartition documentée est notamment :

- PROTOCOL : 96
- GOVERNANCE : 48
- LESSONS : 44
- NETWORK : 39
- TESTING : 1
- ROADMAP : 1
- IDENTITY : 1

Total : 230.

Le point qui reste n'est donc pas « classifier les 230 par domaine » : cette partie est déjà réalisée.

Le chantier résiduel est plutôt la qualité et l'utilisation opérationnelle de cette classification, notamment le routage automatique et les états normatifs associés.

---

# 11. DV-01 / DV-02 / DV-06 / DV-07 : la liste « prochaines priorités » de R415 est obsolète

C'est l'une des corrections les plus importantes.

Le HEAD actuel contient déjà :

- DV-01 = PASS ;
- DV-02 = PASS ;
- DV-03 = PASS ;
- DV-04 = PASS ;
- DV-05 = PASS ;
- DV-06 = PASS ;
- DV-07 = PASS.

Les artefacts versionnés montrent notamment :

- DV-01 : `e2e189_mainnet_genesis`, PASS ;
- DV-02 : `e2e208_dv02_dv06_live`, PASS ;
- DV-03 : `e2e189_mainnet_genesis`, PASS ;
- DV-04 : `e2e189_mainnet_genesis`, PASS ;
- DV-05 : `e2e188_dv05_live_bft`, PASS ;
- DV-06 : `e2e208_dv02_dv06_live`, PASS ;
- DV-07 : `e2e189_mainnet_genesis`, PASS.

### Nuance critique

DV-05 indique explicitement que son PASS est hérité de l'exécution 188 et que la simulation 189 n'a pas relancé les scénarios BFT.

De même, `certified_distributed_mainnet` est une décision de gate distincte des simples fichiers `RESULT.json`.

Donc :

> **Les artefacts DV-01…DV-07 sont actuellement tous marqués PASS dans le dépôt, mais cela ne suffit pas à conclure à lui seul à une certification distribuée mainnet.**

Il faut conserver la distinction entre :

`RESULT.json = résultat d'une validation donnée`

et

`certified_distributed_mainnet = état de certification global gouverné par le gate.`

---

# 12. TASK-001 / FHE : le chantier reste ouvert

Le ledger conserve comme limites de TASK-001 :

- ECC externe pour une vraie tolérance à la distance biométrique ;
- FHE véritable pour `check_uniqueness` ;
- mesures FAR/FRR/PAD sur vrais capteurs ;
- tests SDK iOS/Android.

Donc R415 a raison de maintenir FHE parmi les travaux restants, mais il faut éviter de présenter le Secure Sketch actuel comme une solution FHE.

### C'est-à-dire

Le Secure Sketch protège/reconstruit un secret dérivé d'un gabarit biométrique sous certaines hypothèses.

Le FHE est différent : il permettrait de calculer une fonction sur des données chiffrées sans exposer les données en clair au calculateur.

Ce sont deux problèmes différents.

---

# 13. État consolidé corrigé

| Élément | État réellement établi | Correction à apporter |
|---|---|---|
| HEAD | `d05a615…` | confirmé |
| R415 frontend cleanup | réel | confirmé |
| CI zéro régression TS sur R415 | non attesté par status actuel | ne pas écrire « prouvé » |
| Auto-feedback | code + intégration présentes | runtime externe à distinguer |
| PreToolUse wipe block | présent | protection workflow, pas OS absolue |
| Pre-commit auto-bump | mécanisme + tests présents | installation locale requise |
| Fingerprint R394 | présent | **stale : SHA `9954a60` ≠ HEAD R415** |
| Rule corpus | 230 entrées | déjà classifiées par domaine |
| Types normatifs | 8 | corriger « 7 » → « 8 » |
| DV-01…DV-07 | tous `PASS` dans les RESULT versionnés | ne pas confondre avec certification globale |
| FHE `check_uniqueness` | non livré comme FHE réel | reste ouvert |
| FAR/FRR/PAD | non mesurés sur vrais capteurs | reste ouvert |
| DO-178C | pratiques inspirées présentes | ne pas déclarer conformité DO-178C |

---

# 14. Processus / Problème / Solution pour la prochaine itération

## A. Processus

À chaque nouvelle génération de rapport :

`HEAD GitHub actuel`
→ `diff depuis dernier rapport`
→ `preuves versionnées`
→ `tests/CI`
→ `preuves live datées`
→ `écarts entre documentation et code`
→ `rapport suivant`.

## B. Problème

Le principal risque observé dans R415 n'est pas un défaut de code critique ; c'est une **dérive documentaire** : des états anciens restent formulés comme s'ils étaient encore actuels.

Exemples :

- DV-01/02/06/07 présentés comme prochaines priorités alors qu'ils ont déjà des `RESULT.json` PASS ;
- « 7 types » alors que la liste contient 8 ;
- fingerprint décrit comme référence actuelle alors que son SHA interne est ancien ;
- hook pre-commit décrit comme « actif automatiquement » alors que son installation est locale et non versionnée.

## C. Solution

Le prochain audit doit donc introduire systématiquement trois états distincts :

1. **IMPLEMENTED** — le mécanisme existe dans le code ;
2. **VERIFIED** — un test/artefact vérifiable démontre son comportement ;
3. **LIVE_CURRENT** — une preuve datée démontre l'état actuel du réseau ou runtime.

Un élément ne doit être marqué `LIVE_CURRENT` que si la preuve correspond au SHA/état demandé.

---

# 15. Priorités corrigées après R415

### P0 — cohérence des preuves

1. Régénérer le fingerprint sur le SHA final à attester.
2. Refaire une vérification CI/TypeScript sur `d05a615` si elle n'est pas déjà archivée.
3. Actualiser le ledger `.artcb/task_ledger.yaml`, qui référence encore `b9036a3` comme `git_head` dans la version observée.

### P1 — certification / réseau

4. Vérifier le gate `certified_distributed_mainnet` sur l'état actuel plutôt que de déduire la certification des seuls `RESULT.json`.
5. Conserver la provenance exacte de chaque validation DV et signaler les validations héritées.

### P2 — biométrie

6. ECC réel pour tolérance aux variations de capture.
7. FHE réel pour `check_uniqueness`.
8. FAR / FRR / PAD sur données de capteurs réels.
9. Tests natifs iOS / Android.

### P3 — PoL / IA

10. Poursuivre les validations T4/T6/T7–T11 indiquées comme non prouvées dans R415.
11. Distinguer systématiquement preuve locale, preuve inter-agent et preuve réseau.

---

# 16. Verdict R416

**R415 est réel et le nettoyage frontend est bien présent dans `main`.**

Mais son « Avancement : 100 % » doit être compris comme **100 % du périmètre R415**, et non comme 100 % de la certification ou de tous les chantiers ARTCB.

Les corrections critiques du rapport R415 sont :

1. **8 types normatifs, pas 7.**
2. **DV-01…DV-07 sont déjà marqués PASS dans les artefacts actuels ; ils ne doivent plus être présentés comme simples prochaines priorités.**
3. **Le fingerprint R394 est basé sur `9954a60`, pas sur le HEAD R415 `d05a615…` : il est donc à régénérer pour constituer une attestation du HEAD final.**
4. **Le hook pre-commit est implémenté et testé mais doit être installé dans chaque clone ; `.git/hooks` n'est pas versionné.**
5. **La présence de mécanismes inspirés de DO-178C ne constitue pas une conformité DO-178C.**
6. **Les validations DV PASS ne doivent pas être assimilées automatiquement à `certified_distributed_mainnet`.**
7. **FHE, FAR/FRR/PAD et certains tests biométriques restent explicitement ouverts.**

**Aucune modification de code, configuration ou données de production n'a été effectuée pendant cet audit.**
