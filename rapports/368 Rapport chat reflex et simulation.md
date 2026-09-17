# Audit croisé complet du dépôt ARTCB — état réel de `main`

J’ai repris **directement `origin/main`** avant l’analyse.

**Dépôt :** [vgactech/artcb — GitHub](https://github.com/vgactech/artcb/tree/main?utm_source=chatgpt.com)
**HEAD actuel vérifié :** `0483b309b645b9288f13552aae0eb282709a5edf`
**Dernier commit :** `V-08 DNS fix v2`, daté du **17 septembre 2026 à 07:36 UTC**.
Le dépôt est public, branche par défaut `main`. La connexion GitHub dont je dispose ici est en **lecture seule** (`pull: true`, `push: false`) : je peux donc auditer le code réel, mais je ne modifie pas le dépôt depuis cette session.

### Expertises mobilisées

* architecture logicielle Python/FastAPI
* architecture blockchain et registre distribué
* consensus PBFT
* autorisation / IAM / RBAC / ABAC
* identité utilisateur / agent / machine / wallet
* cryptographie et preuve matérielle
* observabilité et télémétrie
* gouvernance et gestion du corpus de règles
* CI/tests/validation
* Git/GitHub et traçabilité des versions
* analyse de divergence **décision → règle → code → test → live → certification**

Et surtout, j’ai croisé **les mécanismes actuels du code** avec les audits historiques déjà présents dans le dépôt, plutôt que de considérer les rapports comme étant eux-mêmes la vérité.

---

# 1. Première constatation importante : ARTCB possède déjà une grande partie de la mécanique que nous cherchions à construire

Ce n’est donc **pas** un cas où il faudrait inventer entièrement un système de règles pour l’agent.

Il existe déjà plusieurs couches :

```text
                    ARTCB ACTUEL
                         │
        ┌────────────────┼─────────────────┐
        │                │                 │
        ▼                ▼                 ▼
  Sources de règles   Registry          Runtime
        │                │                 │
        │                ▼                 ▼
        │        rule_registry.json   agent_runtime
        │                │                 │
        ▼                ▼                 ▼
 AUTO_PROMPT       rule telemetry    context contract
 PROTOCOLE         rule lineage      agent events
 Cursor rules      rule coverage
 DECISIONS
        │
        ▼
   R340 / R341
        │
        ▼
 divergence :
 DECIDED
 REGISTERED
 CODED
 TESTED
 LIVE
 CERTIFIED
```

Le problème principal que je constate maintenant est donc différent :

> **ARTCB sait déjà enregistrer, tracer et mesurer des règles, mais ne possède pas encore un véritable moteur de “rétro-apprentissage procédural” capable de transformer automatiquement une expérience terminée en amélioration structurée du processus d’exécution.**

C'est une différence fondamentale.

---

# 2. Le dépôt actuel est déjà structuré autour d'une hiérarchie de vérité

C'est probablement la base la plus importante à conserver.

`docs/PROTOCOL_SOURCE_OF_TRUTH.md` définit actuellement cette hiérarchie :

| Rang | Source                        | Signification                          |
| ---- | ----------------------------- | -------------------------------------- |
| 1    | `DECISIONS_UTILISATEUR_ARTCB` | ce que l'opérateur a réellement décidé |
| 2    | spécifications                | traduction de la décision              |
| 3    | code                          | ce qui est réellement exécuté          |
| 4    | tests / `RESULT.json`         | ce qui est prouvé localement           |
| 5    | live                          | ce qui tourne réellement               |
| 6    | rapports                      | ce qui a été observé à une date        |
| 7    | README                        | documentation de présentation          |

Le dépôt précise également qu'un commit n'est **pas** une preuve d'exécution et que le SHA du nœud live est nécessaire pour savoir ce qui tourne réellement.

### Pourquoi c'est excellent pour notre nouveau mécanisme

Cela fournit déjà une règle fondamentale :

```text
NE PAS APPRENDRE À PARTIR D'UNE SIMPLE AFFIRMATION.
APPRENDRE À PARTIR D'UN ÉVÉNEMENT TRAÇABLE ET QUALIFIÉ.
```

Autrement dit :

> l'agent ne doit pas apprendre « j'ai réussi ».

Il doit pouvoir apprendre :

```text
J'ai rencontré X
→ j'ai fait A
→ A a échoué
→ la cause était B
→ C aurait permis de détecter B plus tôt
→ C doit devenir un réflexe
→ C est testable
→ C est maintenant enregistré comme nouvelle règle
```

C'est exactement la structure qu'il faut exploiter.

---

# 3. La gestion des règles existe déjà : `rule_registry.json`

Le registre actuel est en **version 6** et contient **20 règles actives** au moment où j'ai vérifié `main`.

On y trouve notamment :

* `RT-002` — SHA live = `origin/main`
* `RT-003` — ne jamais inventer une mesure live
* `RT-004` — secrets jamais dans git/chat/rapport
* `RT-009` — traçage nanoseconde
* `RT-011` — ne jamais effacer une règle
* `RT-013` — reprendre les tâches ouvertes
* `RT-016` — ingérer la requête utilisateur au début
* `RT-039` — définition de completion
* `RT-SYBIL-076`
* `RT-TELEMETRY`
* `RT-CAPABILITY-FIRST`
* `RT-077-C04`
* `RT-ISSUE-87`
* `RT-HW-H1`
* `RT-HW-BINDING`
* `RT-CORPUS-MAP`
* `RT-MEASURE-VALID`
* `RT-DIVERGENCE-341`
* `RT-IDENTITY-LAYERS`

Le registre précise déjà que la règle doit avoir une provenance et qu'une révocation ne doit pas supprimer l'historique.

### Mais il manque une chose fondamentale

Le registre sait essentiellement dire :

```text
RuleID
version
severity
title
scope
status
source_incident
```

Il ne sait pas encore représenter suffisamment précisément :

```text
CONDITION
→ FIRST_REFLEX
→ ACTION
→ VALIDATION
→ CAUSE_ROOT
→ LESSON
→ COUNTEREXAMPLE
→ SUPERSEDES
→ DEPENDENCIES
→ APPLICABILITY
→ PROCESS_PHASE
```

C'est ici que notre nouvelle idée doit s'intégrer.

---

# 4. La télémétrie des règles est déjà très avancée

Le fichier :

`src/artcb/rules/telemetry.py`

est particulièrement intéressant.

Il possède déjà les états :

```text
seen
checked
applied
applied_confirmed
violated
corrected
not_proven
waived
```

et les événements supplémentaires :

```text
conflict
coverage_gap
new_rule
```

C'est très proche de ce qu'il nous faut.

## Surtout : l'honnêteté des preuves est déjà protégée

Le code interdit de considérer simplement la pensée de l'agent comme une preuve :

```text
thinking ≠ applied_confirmed
```

`applied_confirmed` exige notamment :

* un type de preuve autorisé ;
* une référence à cette preuve ;
* aucune simple affirmation de l'agent.

La liste de preuves reconnues comprend notamment :

```text
http_status
git_sha
pytest
file_sha256
measurement_json
live_bootstrap
commit
```

Le test associé vérifie explicitement qu'une affirmation de type « thinking only » ne peut pas produire `applied_confirmed`.

### C'est une fondation essentielle

Notre futur système de learning doit absolument conserver cette règle :

```text
OBSERVATION
≠
INTERPRÉTATION
≠
DÉCISION
≠
PREUVE
≠
RÈGLE VALIDÉE
```

---

# 5. Le dépôt possède également une cartographie du corpus

`artcb_r340_rule_corpus_audit.py` analyse déjà plusieurs sources :

```text
rules/rule_registry.json
PROTOCOLE_ARTCB
AUTO_PROMPT_ARTCB
.cursor/rules/artcb-live-node.mdc
.cursor/rules/artcb-read-all.mdc
.cursor/rules/mac-node-local.mdc
.cursor/rules/aws-node-3.mdc
.cursor/rules/ovh-node-4.mdc
DECISIONS_UTILISATEUR_ARTCB
CAHIER_DES_CHARGES_ARTCB
CHECKLIST_PRE_DEV_ARTCB
QUESTIONS_OUVERTES_ARTCB
LEÇONS_APPRISES_ARTCB
GOUVERNANCE_ARTCB
STANDARD_NAMES_ARTCB
```

Cela répond déjà à une partie de ton idée :

> « Étudie et identifie les moyens d'intégrer la nouvelle règle dans les règles existantes. »

Le système sait déjà **où chercher les règles**.

---

# 6. Mais il y a encore un gros problème : le corpus n'est pas encore sémantiquement unifié

C'est probablement le point le plus important de l'audit.

Le système actuel compte des **marqueurs**, mais un marqueur n'est pas nécessairement une règle.

Le dernier `rule_coverage.json` actuel indique :

```text
registered_rules = 20
numbered_entry_sum = 187
unmapped_estimate = 167
mapped_to_source = PARTIAL
```

et précise explicitement que les 187 marqueurs ne sont **pas** 187 règles sémantiques uniques.

Donc :

```text
20 règles enregistrées
          ≠
187 règles réelles
          ≠
187 règles uniques
```

Il faut plutôt considérer :

```text
187 = signaux textuels détectés
20  = règles officiellement enregistrées
X   = règles sémantiques réellement uniques
```

Le `X` n'est actuellement pas déterminé.

---

# 7. L'ancien audit R344 avait déjà identifié exactement ce problème

Le rapport R344 est extrêmement clair.

Il donnait :

```text
Découvert        PARTIAL
Extrait          PARTIAL
Normalisé        PARTIAL
Dédoublonné      NO
Classifié        PARTIAL
Enregistré       PARTIAL
Coverage         PARTIAL
Runtime          PARTIAL
```

et indiquait notamment :

> absence de `semantic_hash` unique

ainsi que :

> markers ≠ règles uniques.

### Donc notre nouvelle architecture doit corriger cela

Avant :

```text
texte
 ↓
regex
 ↓
marqueur
 ↓
registry
```

Après :

```text
texte
 ↓
extraction
 ↓
normalisation
 ↓
semantic canonicalization
 ↓
semantic_hash
 ↓
déduplication
 ↓
classification
 ↓
résolution des conflits
 ↓
RuleID
 ↓
registry
```

---

# 8. Autre découverte : `rule_lineage.json` existe déjà

C'est une très bonne base.

Le fichier actuel contient déjà :

```text
rule_id
status
priority
canonical_text
source_incident
authority
source
supersedes
superseded_by
enforcement
tests
evidence
mapped
```

Mais pratiquement toutes les règles actuelles restent au niveau :

```text
mapped = registry_only
```

avec peu de relations vers :

```text
décision
code
test
preuve
```

### C'est exactement l'endroit où intégrer notre futur système.

Je recommande de ne **pas créer un second système de règles parallèle**.

Il faut enrichir celui-ci.

---

# 9. Le système IR possède lui aussi déjà son propre moteur de règles

`src/artcb/ir/rules.py` contient :

```text
RuleCondition
RuleAction
IRRule
RuleEvaluationResult
RulesRegistry
```

Une règle peut déjà être exprimée comme :

```text
SI condition
ALORS action
```

avec des opérateurs :

```text
>
>=
<
<=
==
!=
in
contains
```

et des actions comme :

```text
set
call
transfer
mint_nft
log
```

### Mais attention

Ce moteur IR n'est pas actuellement le moteur de learning procédural.

La documentation du fichier dit elle-même que l'exécution automatique relève de l'agent ou d'un scheduler futur.

Donc :

```text
IR Rules
    =
règles déclaratives métier

Rule Telemetry
    =
suivi de conformité

Rule Corpus
    =
cartographie

Agent Learning
    =
❌ pas encore véritablement présent
```

C'est une distinction importante.

---

# 10. Le runtime agent possède déjà une autre fondation importante

`src/artcb/agent_runtime.py` existe.

Il définit notamment :

```text
memory:read
memory:write
context:read
memo:write
kcg:read
kcg:publish
agent:register
```

ainsi que les capacités privilégiées :

```text
wallet:export
wallet:seed
admin:*
```

Il possède également :

```text
register_agent()
commit_event()
get_event()
```

avec gestion d'idempotence.

### Cela signifie que le futur système peut être branché au runtime

Sans créer :

```text
un deuxième runtime
```

ou :

```text
un deuxième registre d'agents
```

---

# 11. Le `context_contract` montre cependant une limite importante

Le contexte agent actuel sait déjà exposer :

```text
chain_height
chain_tip
code_sha
code_branch
release_integrity
agent_id
provider
owner_address
task_id
node_id
role
PBFT
scope
active_decisions
open_bugs
validated_facts
not_proven
constraints
```

C'est très intéressant.

Mais le contrat indique explicitement comme **non prouvé** :

```text
decision_revoke_supersede
agent_used_received_context
```

et plusieurs autres éléments.

Donc l'agent connaît actuellement une partie de l'état du système, mais le système ne sait pas toujours démontrer :

> **« l'agent a effectivement utilisé telle information reçue pour prendre telle décision ».**

C'est une faiblesse directe pour le learning.

---

# 12. Il existe déjà une séparation correcte entre identité humaine et agent

C'est un point à préserver absolument.

`authz/identity.py` distingue :

```text
sess_
artcb_
X-ARTCB-Agent-Id
```

Un agent utilisant une session humaine devient :

```text
kind = agent
parent_address = humain
agent_id = ...
```

Et le moteur d'autorisation impose :

> un agent ne peut jamais dépasser les permissions de son parent humain.

Le code effectue d'abord l'autorisation de l'humain, puis limite l'agent à ce plafond.

C'est ce qu'il faut conserver.

### Donc notre futur mécanisme doit respecter :

```text
Agent Learning
       │
       ├── apprend une méthode
       ├── apprend un réflexe
       ├── apprend une cause
       └── améliore son parcours
       
       MAIS

Agent Learning
       ≠
Agent Authority Expansion
```

Autrement dit :

**apprendre mieux ≠ obtenir davantage de droits.**

---

# 13. L'autorisation elle-même est déjà beaucoup plus mature qu'auparavant

Le moteur `AuthorizationEngine` implémente notamment :

```text
DENY > ALLOW
```

et une logique par :

```text
organization
group
subgroup
resource
user
agent
```

avec plafond humain pour l'agent.

Le modèle `PolicyTx` est versionné, signé/auditable dans son architecture, révocable et expirant.

Le système fait également une distinction correcte entre :

```text
visibility
```

et :

```text
permission
```

Ce point est important pour notre système de règles : une règle ne doit jamais déduire une permission simplement parce qu'une ressource est `private`, `group` ou `public`.

---

# 14. Le système de Genesis / domaines est également déjà séparé du consensus

Le dépôt possède :

```text
authz/genesis.py
authz/domains.py
authz/registry.py
authz/body_replication.py
```

et la source de vérité rappelle explicitement :

```text
un nœud héberge un domaine
le fondateur possède le domaine
```

ainsi que :

```text
HOST_ONLY
REPLICA
CONSENSUS
```

comme rôles différents.

C'est une architecture saine pour notre futur système.

---

# 15. Côté blockchain/consensus : les garde-fous sont désormais beaucoup plus solides

Le code contient maintenant le chemin PBFT avec :

```text
PRE-PREPARE
PREPARE
COMMIT
certificate Q=3
```

et les blocs finalisés disposent d'un chemin spécifique `write_certified_block`.

La source de vérité rappelle également que les écritures publiques officielles doivent passer par PBFT à partir de la séquence concernée.

### Conséquence pour le learning

Une nouvelle règle issue d'une expérience blockchain doit pouvoir dire :

```text
j'ai observé un problème
↓
sur quel niveau ?
↓
agent
runtime
API
authz
P2P
consensus
blockchain
live
```

et **ne pas confondre** une erreur d'agent avec une erreur de consensus.

---

# 16. Le hook Cursor existe déjà, mais il ne fait pas encore le travail complet que nous voulons

`.cursor/hooks/after_agent_thought.py` capture déjà :

```text
afterAgentThought
↓
agent_thoughts.jsonl
↓
thinking/<timestamp>
↓
hash SHA-256
↓
optionnellement /ai/memo
↓
notifications
```

et génère aussi un bloc `RULE COMPLIANCE`.

Mais le code précise lui-même :

```text
ui_equals_hook = NOT_PROVEN_BY_ARCHITECTURE
```

et :

```text
Layer 1 private CoT is never here.
```

### Donc il ne faut surtout pas faire :

```text
Thought
 ↓
nouvelle règle
```

Il faut faire :

```text
Thought / Event
       ↓
Observation
       ↓
Evidence
       ↓
Task result
       ↓
Retrospective
       ↓
Candidate lesson
       ↓
Rule analysis
       ↓
Test
       ↓
Validation
       ↓
Rule registry
```

---

# 17. Le gros manque identifié : aucune vraie boucle de rétroaction procédurale

C'est ici que ton idée apporte quelque chose de réellement nouveau.

J'ai recherché explicitement dans le dépôt les mécanismes de :

```text
retrospective
root cause
process optimization
lesson extraction
```

Je ne trouve pas de moteur correspondant déjà implémenté.

Il existe :

* `LEÇONS_APPRISES_ARTCB`
* `rule_registry`
* `rule_lineage`
* `rule_telemetry`
* `rule_coverage`
* `rule_divergence_matrix`

mais pas encore un mécanisme complet :

```text
Tâche terminée
↓
reconstruction automatique du parcours
↓
analyse causale
↓
identification du premier point de détection possible
↓
comparaison parcours réel / parcours minimal
↓
extraction d'une règle candidate
↓
test de la règle
↓
intégration
↓
mesure future
```

C'est **le principal gap architectural que je recommande de traiter maintenant.**

---

# 18. Avant / après proposé

## AVANT

Actuellement, on a essentiellement :

```text
Utilisateur
    ↓
Agent
    ↓
Règles disponibles
    ↓
Travail
    ↓
Résultat
    ↓
Télémétrie
```

La télémétrie sait notamment :

```text
seen
checked
applied
applied_confirmed
violated
corrected
not_proven
```

mais elle ne reconstruit pas automatiquement :

```text
Pourquoi le chemin a été long ?
Pourquoi l'agent n'a pas appliqué une règle plus tôt ?
Quelle règle aurait évité 6 sous-tâches ?
Quelle nouvelle règle faut-il créer ?
```

---

# 19. APRÈS

Je recommande :

```text
                  ┌──────────────────┐
                  │    TASK START    │
                  └────────┬─────────┘
                           ↓
                  CONTEXT + RULES
                           ↓
                  FIRST REFLEX CHECK
                           ↓
                    EXECUTION
                           ↓
                 ┌─────────┴─────────┐
                 │                   │
              SUCCESS              ERROR
                 │                   │
                 └─────────┬─────────┘
                           ↓
                      VALIDATION
                           ↓
                    EVIDENCE PACK
                           ↓
                    TASK CLOSURE
                           ↓
                  RETROSPECTIVE GATE
                           ↓
            ┌──────────────┼──────────────┐
            ↓              ↓              ↓
       NO LESSON      EXISTING RULE    NEW RULE
            │              │              │
            │              ↓              ↓
            │        UPDATE USAGE    CANDIDATE
            │                             ↓
            │                         TEST
            │                             ↓
            │                         VALIDATE
            │                             ↓
            └──────────────────────→ REGISTER
                                      ↓
                                   FUTURE
                                      ↓
                              FIRST REFLEX
```

---

# 20. Le point clé : la nouvelle règle ne doit pas être appliquée immédiatement simplement parce qu'elle semble bonne

Il faut introduire des **états de cycle de vie**.

Je recommande :

```text
OBSERVED
   ↓
CANDIDATE
   ↓
ANALYZED
   ↓
TESTED
   ↓
VALIDATED
   ↓
ACTIVE
```

avec des sorties :

```text
REJECTED
SUPERSEDED
DEPRECATED
WAIVED
```

### Signification

**OBSERVED**

> Quelque chose s'est produit.

**CANDIDATE**

> Une amélioration potentielle est identifiée.

**ANALYZED**

> On a vérifié qu'elle ne duplique pas une règle existante.

**TESTED**

> Des cas positifs et négatifs ont été exécutés.

**VALIDATED**

> La règle est suffisamment démontrée.

**ACTIVE**

> Elle peut participer au comportement normal de l'agent.

---

# 21. Le premier réflexe doit devenir une propriété explicite de la règle

C'est une amélioration que je considère particulièrement importante.

Aujourd'hui :

```json
{
  "rule_id": "RT-002",
  "title": "SHA live == origin/main"
}
```

Demain :

```json
{
  "rule_id": "RT-002",
  "version": 2,

  "condition": {
    "phase": "LIVE",
    "requires": [
      "deployment_sha",
      "live_sha"
    ]
  },

  "first_reflex": {
    "action": "compare_live_sha_to_origin_main",
    "priority": "P0"
  },

  "prevents": [
    "claiming_live_proof_on_wrong_sha"
  ],

  "validation": {
    "required_evidence": [
      "live_bootstrap",
      "git_sha"
    ]
  }
}
```

### C'est-à-dire

La règle ne dit plus seulement :

> « SHA live = origin/main ».

Elle dit aussi :

> **« Lorsque tu commences une tâche live, ton premier réflexe est de comparer les deux SHA avant de lancer les autres opérations. »**

C'est précisément ton idée.

---

# 22. Pourquoi cette différence est très importante

Prenons un exemple directement issu de l'historique ARTCB.

### Mauvais chemin

```text
1. analyser le problème
2. chercher la configuration
3. modifier le script
4. relancer
5. regarder DNS
6. regarder TLS
7. regarder le backend
8. constater que le serveur exécutait un ancien SHA
9. recommencer
```

### Nouveau réflexe

```text
P0
↓
GET /health
↓
git_sha ?
↓
origin/main ?
```

Si :

```text
live_sha != origin/main
```

alors :

```text
STOP
↓
follow-main
↓
redeploy
↓
SHA verification
↓
seulement ensuite diagnostic applicatif
```

Le but n'est donc pas :

> faire moins de contrôles.

Le but est :

> **faire le bon contrôle suffisamment tôt pour éviter les contrôles devenus inutiles.**

---

# 23. Il faut donc introduire la notion de `FIRST_REFLEX`

Je recommande fortement :

```text
FIRST_REFLEX
```

comme concept natif du système.

Exemple :

```text
Règle :
RT-CAPABILITY-FIRST

Condition :
travail C04 / TPM / hardware

FIRST_REFLEX :
capability_discovery()

Avant :
chercher TPM
installer outils
tester
interpréter
...

Après :
capability_discovery()
→ UNSUPPORTED / AVAILABLE / ATTESTABLE
→ seulement ensuite poursuivre
```

Cette règle existe déjà conceptuellement et son code de découverte matériel est déjà présent. Le registre la décrit comme une règle critique empêchant les faux positifs hardware.

Notre amélioration consiste à **formaliser le réflexe lui-même**.

---

# 24. Deuxième notion indispensable : `APPLICABILITY_PHASE`

Une règle ne doit pas simplement être « active ».

Elle doit savoir **quand elle s'applique**.

Je recommande :

```text
GLOBAL
TASK_START
DISCOVERY
PLANNING
EXECUTION
VALIDATION
FAILURE
RECOVERY
TASK_CLOSURE
RETROSPECTIVE
DEPLOY
LIVE
CERTIFICATION
```

Exemple :

```text
RT-003
Never invent live measures

phase:
LIVE
VALIDATION
CERTIFICATION
REPORT
```

Alors que :

```text
RT-CAPABILITY-FIRST
```

serait :

```text
DISCOVERY
PLANNING
HARDWARE
```

---

# 25. Troisième notion : `PRIORITY`

Le système possède déjà un calcul de priorité dans `telemetry.py`.

Il empêche notamment qu'une règle critique rare soit noyée par une règle peu importante mais très fréquente.

Il faut conserver cela.

Mais je recommande une hiérarchie plus explicite :

```text
P0 = vérité / sécurité / précondition critique
P1 = contexte / historique / état réel
P2 = règle applicable
P3 = cause racine
P4 = action minimale
P5 = validation
P6 = régression
P7 = rétrospective
P8 = apprentissage
P9 = optimisation
```

### Attention

P9 ne doit jamais pouvoir passer devant P0.

Donc :

```text
performance
   ↓
ne peut jamais contourner
   ↓
security / evidence / validation
```

---

# 26. Quatrième notion : `CAUSE_ROOT`

Actuellement le système peut enregistrer `source_incident`.

Mais :

```text
source_incident
```

n'est pas encore la même chose que :

```text
root_cause
```

Exemple :

```text
Incident :
DNS inaccessible

Cause apparente :
OVH1 mort

Cause racine :
endpoint public dépendait d'un seul A record
```

Puis :

```text
Règle :
PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH
```

Et enfin :

```text
First reflex :
probe all endpoint candidates before diagnosing application failure
```

C'est beaucoup plus puissant.

---

# 27. Cinquième notion : `COUNTEREXAMPLES`

Une règle ne doit pas devenir active uniquement parce qu'un test montre qu'elle fonctionne.

Il faut aussi montrer où elle **ne doit pas s'appliquer**.

Exemple :

```text
Règle :
"Avant C04, faire capability discovery"
```

Cas positif :

```text
C04 demandé
→ capability discovery
→ UNSUPPORTED
→ ne pas poursuivre
```

Contre-exemple :

```text
Simple wallet Ed25519
→ C04 non concerné
→ capability discovery C04 inutile
```

Donc :

```text
condition
+
action
+
contre-exemple
```

---

# 28. Sixième notion : `RULE_CONFLICT`

C'est actuellement un point incomplet.

La télémétrie possède déjà :

```text
conflict
coverage_gap
```

mais R344 indiquait que le **full conflict engine** était encore ouvert.

Il faut donc construire :

```text
Rule A
    ↓
condition X
    ↓
action Y

Rule B
    ↓
condition X
    ↓
action Z
```

Le moteur doit produire :

```text
CONFLICT
```

plutôt que choisir arbitrairement.

---

# 29. Et il faut distinguer quatre types de conflits

## A. Contradiction

```text
A → ALLOW
B → DENY
```

## B. Spécialisation

```text
A = règle générale
B = règle plus spécifique
```

B peut être prioritaire sans être contradictoire.

## C. Remplacement

```text
R12 version 1
↓
R12 version 2
```

## D. Exception

```text
R10 :
toujours faire X

R11 :
sauf si condition Y
```

Le système doit comprendre cette différence.

---

# 30. Il faut également intégrer les règles aux phases du travail

Je recommande une architecture de ce type :

```text
RULE RESOLUTION ENGINE

          │
          ├── task classification
          │
          ├── applicable rules
          │
          ├── precedence
          │
          ├── conflicts
          │
          ├── dependencies
          │
          ├── first reflex
          │
          └── required evidence
```

Puis :

```text
TASK EXECUTOR
      ↓
RULE TELEMETRY
      ↓
EVIDENCE
      ↓
RETROSPECTIVE ENGINE
```

---

# 31. Le moteur de rétrospective devrait poser systématiquement ces questions

À la fin d'une tâche significative :

### Q1 — Qu'est-ce qui s'est réellement passé ?

Pas l'interprétation.

Les événements.

### Q2 — Quel était le résultat attendu ?

```text
expected
```

### Q3 — Quel a été le résultat réel ?

```text
actual
```

### Q4 — Quelle a été la première divergence ?

C'est très important.

### Q5 — Quelle information était déjà disponible à ce moment-là ?

### Q6 — Quelle règle existante aurait pu éviter le problème ?

### Q7 — Pourquoi cette règle n'a-t-elle pas été utilisée ?

### Q8 — Quelle sous-tâche est devenue nécessaire uniquement parce qu'un réflexe manquait ?

### Q9 — Quel aurait été le premier réflexe correct ?

### Q10 — Cette amélioration est-elle généralisable ?

### Q11 — Peut-elle devenir une règle ?

### Q12 — Peut-elle être testée automatiquement ?

---

# 32. Il faut distinguer « apprendre une solution » de « apprendre un réflexe »

C'est probablement **la distinction la plus importante de tout le système**.

### Mauvais apprentissage

```text
Problème X
→ Solution Y
```

Cela fonctionne seulement si X revient exactement.

### Bon apprentissage

```text
Classe de problème X
→ détecter caractéristique C
→ appliquer réflexe R
→ vérifier résultat V
```

Exemple :

```text
Erreur 502
```

Mauvais apprentissage :

```text
502 sur N2
→ redémarrer Python
```

Bon apprentissage :

```text
502
→ déterminer si nginx est vivant
→ déterminer si upstream est vivant
→ déterminer le SHA
→ déterminer si le problème est transport ou application
→ seulement ensuite choisir restart / deploy / DNS
```

C'est beaucoup plus général.

---

# 33. La boucle complète que je recommande pour ARTCB

## Phase A — début de tâche

```text
1. identifier tâche
2. charger contexte
3. charger règles
4. rechercher tâches ouvertes
5. classifier la tâche
6. déterminer les règles applicables
7. déterminer FIRST_REFLEX
```

---

## Phase B — préparation

```text
8. vérifier préconditions
9. vérifier dépendances
10. identifier preuves nécessaires
11. identifier contre-exemples
```

---

## Phase C — exécution

```text
12. exécuter
13. journaliser événements
14. journaliser règles vues
15. journaliser règles utilisées
16. journaliser preuves
```

---

## Phase D — validation

```text
17. résultat attendu ?
18. résultat réel ?
19. test ?
20. preuve indépendante ?
21. live ?
22. SHA ?
```

---

## Phase E — clôture

```text
23. tâche réellement terminée ?
24. tâches secondaires encore ouvertes ?
25. rapport créé ?
26. preuve conservée ?
```

---

## Phase F — rétrospective

```text
27. reconstruire parcours
28. détecter erreurs
29. identifier cause racine
30. identifier premier point détectable
31. identifier sous-tâches évitables
32. trouver règle existante
33. déterminer pourquoi elle n'a pas été appliquée
34. chercher amélioration
```

---

## Phase G — apprentissage

```text
35. créer candidate lesson
36. normaliser
37. semantic_hash
38. dédupliquer
39. chercher conflits
40. définir FIRST_REFLEX
41. définir phase
42. définir priorité
43. créer tests
```

---

## Phase H — activation

```text
44. TESTED
45. VALIDATED
46. REGISTERED
47. ACTIVE
```

---

# 34. Ce qu'il ne faut surtout pas faire

Je déconseille fortement :

```text
agent termine tâche
↓
agent écrit une nouvelle règle
↓
règle immédiatement active
```

Cela créerait une forme d'auto-modification incontrôlée.

Le bon modèle est :

```text
agent
 ↓
proposition
 ↓
analyse
 ↓
test
 ↓
preuve
 ↓
validation
 ↓
activation
```

---

# 35. Cela s'intègre parfaitement avec la hiérarchie de vérité actuelle

On obtient alors :

```text
DÉCISION
   ↓
SPEC
   ↓
RULE CANDIDATE
   ↓
RULE TEST
   ↓
RULE REGISTERED
   ↓
CODE
   ↓
TEST
   ↓
LIVE
   ↓
CERTIFIED
```

Et surtout :

```text
LESSON
```

ne doit **pas** être automatiquement :

```text
DECISION
```

ni :

```text
ACTIVE RULE
```

C'est fondamental.

---

# 36. Je propose donc de fusionner R340/R341 avec le futur système au lieu de créer R350-like parallèle

Le dépôt a déjà :

```text
R337 = telemetry
R338 = capability
R339 = hardware identity
R340 = corpus mapping
R341 = divergence
R344 = corpus compliance
R347 = identity layers
```

La bonne évolution est :

```text
R337
  ↓
Rule telemetry

R340
  ↓
Rule corpus

R341
  ↓
Rule state/divergence

NOUVELLE COUCHE
  ↓
Rule lifecycle + procedural learning
```

Pas :

```text
nouveau système complètement séparé
```

---

# 37. Architecture de données recommandée

Je recommande un objet conceptuel :

```json
{
  "rule_id": "RT-AUTO-001",
  "version": 1,

  "canonical_text": "...",

  "semantic_hash": "...",

  "status": "candidate",

  "authority": "agent_proposal",

  "source_incident": "TASK-123",

  "root_cause": "...",

  "condition": {
    "task_phase": "LIVE",
    "signals": [
      "public_endpoint",
      "deployment"
    ]
  },

  "first_reflex": {
    "priority": "P0",
    "action": "verify_live_sha"
  },

  "action": "...",

  "expected_outcome": "...",

  "counterexamples": [],

  "dependencies": [],

  "supersedes": null,

  "superseded_by": null,

  "tests": [],

  "evidence": [],

  "source": {
    "task_id": "...",
    "agent_id": "...",
    "timestamp": "..."
  }
}
```

---

# 38. Et il faut séparer `LESSON` et `RULE`

Je recommande fortement cette distinction.

```text
LESSON
```

signifie :

> Nous avons appris quelque chose.

Alors que :

```text
RULE
```

signifie :

> Cette connaissance est suffisamment formalisée pour guider systématiquement le comportement.

Donc :

```text
LESSON
 ↓
candidate rule
 ↓
validation
 ↓
RULE
```

---

# 39. Exemple concret sur l'histoire récente du dépôt

Dernière séquence V-08 :

```text
OVH1 mort
↓
DNS apex multi-A
↓
TLS
↓
N4/N2
↓
failover
```

Le dépôt a maintenant plusieurs garde-fous :

```text
failover.py
v08_e2e_probe.py
DNS verification
TLS validation
multi-A
```

et le dernier commit a supprimé l'adresse OVH1 du DNS apex après constat de son indisponibilité. Le commit précise également :

```text
41/41 tests PASS
CERTIFIED_100=false
OVH1 BLOQUÉ
R299 respecté
```

Mais la vraie leçon procédurale généralisable est plutôt :

```text
FIRST_REFLEX :

Avant de diagnostiquer l'application derrière un endpoint public,
vérifier indépendamment :

1. DNS
2. TCP
3. TLS
4. hostname
5. backend
6. blockchain
7. SHA
```

Cela devient une règle réutilisable pour toutes les futures pannes.

---

# 40. Autre exemple : le problème du corpus

Avant :

```text
registered_rules = 20
```

Un agent pourrait facilement penser :

> « Il y a 20 règles. »

Mais le système indique lui-même :

```text
registered_rules ≠ corpus total
```

### Le nouveau réflexe devrait devenir :

```text
Quand on me demande "toutes les règles",
FIRST_REFLEX =
ne jamais lire seulement rule_registry.json.
```

Puis :

```text
1. rule sources
2. corpus scan
3. normalization
4. dedupe
5. authority classification
6. registry
7. divergence
```

C'est exactement le type de gain procédural recherché.

---

# 41. Autre exemple : identité

R347 constate actuellement :

```text
Cartographie code = DONE
I1-I8 = CODED + tested
User↔Node signature association = NOT_IMPLEMENTED
HumanRegistry ↔ /wallet/create = NOT_WIRED
UNIQUE_HUMAN = false
CERTIFIED_100 = false
```

La bonne règle procédurale n'est donc pas :

> « L'identité ARTCB est terminée. »

mais :

```text
FIRST_REFLEX :

Pour toute affirmation d'identité,
séparer :

Node
User
Device
Wallet
Human
Agent

puis vérifier quelle liaison est réellement prouvée.
```

Cette règle est déjà partiellement représentée par `RT-IDENTITY-LAYERS`, mais elle devrait être transformée en **réflexe procédural testable**.

---

# 42. Le système doit également apprendre des tâches qui ont réussi

C'est très important.

Le learning ne doit pas être :

```text
ERROR → LESSON
```

uniquement.

Il faut :

```text
SUCCESS → optimisation possible
ERROR → correction nécessaire
SURPRISE → investigation
CONFLICT → résolution
NEW RULE → intégration
REPEATED TASK → compression du processus
```

Une tâche réussie peut avoir pris :

```text
20 étapes
```

alors que :

```text
6 étapes
```

auraient suffi.

C'est précisément là que ton idée de :

> « quelle première réaction aurait permis d'éviter toutes les sous-tâches ? »

devient extrêmement intéressante.

---

# 43. Nouvelle métrique à ajouter

Je recommande :

```text
actual_steps
optimal_steps
avoidable_steps
```

puis :

```text
Process Compression Ratio
=
avoidable_steps / actual_steps
```

Exemple :

```text
actual = 12
optimal = 5
avoidable = 7

compression =
7 / 12
=
58,3 %
```

Mais attention :

**cette métrique ne doit jamais récompenser la suppression d'une vérification de sécurité.**

Donc :

```text
sécurité obligatoire
preuve obligatoire
validation obligatoire
```

restent incompressibles.

---

# 44. Une meilleure métrique serait donc pondérée

Par exemple :

```text
Étape sécurité       = incompressible
Étape preuve         = incompressible
Étape validation     = incompressible
Étape découverte     = compressible
Étape répétitive     = compressible
Étape diagnostic     = potentiellement compressible
Étape administrative = compressible
```

Ainsi :

```text
OPTIMISATION
≠
SUPPRESSION DES CONTRÔLES
```

mais :

```text
OPTIMISATION
=
SUPPRESSION DES DÉTOURS INUTILES
```

---

# 45. Intégration avec `rule_usage.jsonl`

La télémétrie actuelle est déjà append-only.

Je recommande d'y ajouter des événements procéduraux :

```text
task_started
rule_resolution
first_reflex_selected
rule_applied
rule_blocked
rule_conflict
step_started
step_completed
step_avoided
root_cause_identified
retrospective_started
lesson_candidate
rule_candidate
rule_tested
rule_validated
rule_activated
```

Cela donnerait enfin une vraie chronologie.

---

# 46. Exemple d'une trace future

```text
09:00 task_started
09:00 context_loaded
09:00 rules_resolved
09:00 RT-002 selected
09:00 first_reflex=verify_live_sha
09:00 live_sha checked
09:00 SHA mismatch
09:00 task_execution_blocked
09:01 follow-main
09:02 redeploy
09:03 SHA verified
09:03 task resumed
09:10 success
09:10 validation
09:11 retrospective
09:12 lesson_candidate
09:13 existing_rule_match=RT-002
09:14 no_new_rule
09:14 process_optimization_recorded
```

Cela permettrait à l'agent de comprendre :

> **« La règle existait déjà ; mon problème n'était pas l'absence de connaissance mais l'absence de sélection précoce de cette règle. »**

C'est une distinction très puissante.

---

# 47. C'est également compatible avec la conservation historique exigée par ARTCB

La règle `RT-011` impose déjà de ne jamais effacer les règles et de conserver l'historique.

Donc :

```text
R1 v1
   ↓
R1 v2
   ↓
R1 v3
```

et non :

```text
R1
↓
écrasée
```

Le système doit garder :

```text
qui
quand
pourquoi
à partir de quel incident
quelle ancienne règle
quelle nouvelle règle
quelle preuve
quels tests
```

---

# 48. Ce que je considère déjà réellement en place

| Domaine                                 | État constaté                       |
| --------------------------------------- | ----------------------------------- |
| Rule registry                           | **EN PLACE**                        |
| Rule telemetry                          | **EN PLACE**                        |
| Rule lineage                            | **EN PLACE mais partiel**           |
| Corpus discovery                        | **EN PLACE mais partiel**           |
| Rule divergence                         | **EN PLACE**                        |
| Evidence gating                         | **EN PLACE**                        |
| Thinking ≠ proof                        | **EN PLACE**                        |
| Agent runtime                           | **EN PLACE**                        |
| Agent identity                          | **EN PLACE**                        |
| Human ceiling                           | **EN PLACE**                        |
| Authorization engine                    | **EN PLACE**                        |
| Domain/Genesis model                    | **EN PLACE**                        |
| PBFT finality                           | **EN PLACE**                        |
| Live SHA verification                   | **EN PLACE**                        |
| Hardware capability preflight           | **EN PLACE**                        |
| Identity layer model                    | **EN PLACE**                        |
| Semantic rule deduplication             | **MANQUANT**                        |
| Full corpus semantic mapping            | **PARTIAL**                         |
| Rule conflict engine                    | **PARTIAL / OUVERT**                |
| Rule applicability phase                | **PAS FORMALISÉE SUFFISAMMENT**     |
| First-reflex engine                     | **MANQUANT**                        |
| Root-cause engine                       | **MANQUANT**                        |
| Actual-vs-optimal process analysis      | **MANQUANT**                        |
| Automatic retrospective                 | **MANQUANT**                        |
| Lesson → candidate rule                 | **MANQUANT**                        |
| Candidate → tested → validated → active | **MANQUANT comme workflow complet** |
| Counterexample validation               | **MANQUANT**                        |
| Process compression metric              | **MANQUANT**                        |

---

# 49. Priorités que je recommande

## P0 — Ne pas créer un second moteur de règles

Réutiliser :

```text
rule_registry
rule_lineage
rule_coverage
rule_divergence_matrix
rule telemetry
agent_runtime
context_contract
```

---

## P1 — Créer le `Rule Lifecycle Engine`

Concept :

```text
OBSERVED
→ CANDIDATE
→ ANALYZED
→ TESTED
→ VALIDATED
→ ACTIVE
```

---

## P1 — Ajouter `semantic_hash`

Objectif :

```text
même règle formulée différemment
=
même concept
```

sans prétendre que de simples mots identiques constituent une règle identique.

---

## P1 — Ajouter `FIRST_REFLEX`

Chaque règle importante doit avoir :

```text
condition
phase
first_reflex
required_evidence
```

---

## P1 — Ajouter `root_cause`

Séparer :

```text
incident
symptom
cause
root cause
lesson
rule
```

---

## P2 — Construire le `Retrospective Engine`

Déclenché notamment après :

```text
ERROR
CORRECTED
SURPRISE
NEW_RULE
TASK_COMPLETE
```

---

## P2 — Construire le `Rule Conflict Resolver`

Avec :

```text
general
specific
override
exception
supersedes
contradiction
```

---

## P2 — Ajouter les contre-exemples

Une règle candidate ne devient pas active sans cas où elle doit :

```text
s'appliquer
```

et :

```text
ne pas s'appliquer
```

---

# 50. Ce que je ne recommande PAS de modifier

Je conserverais tels quels les principes suivants :

### `registered_rules ≠ corpus`

Indispensable.

### `thinking ≠ proof`

Indispensable.

### `CERTIFIED_100=false` tant que la preuve manque

Indispensable.

### SHA live ≠ commit Git

Indispensable.

### ne jamais supprimer l'historique des règles

Indispensable.

### agent ≤ human authority

Indispensable.

### Node ≠ User ≠ Device ≠ Wallet

Indispensable.

---

# 51. Une incohérence documentaire subsiste également dans `main`

Le README actuel affiche :

```text
Tests : 519/519 passent
```

mais la section de commande indique encore :

```text
python3 -m pytest tests/ -q
# 303/303 PASS
```

Le README est explicitement classé comme **rang 7**, donc il n'est pas une source de vérité sur l'état réel du code.

Mais cette divergence reste à corriger dans la documentation, car elle peut produire exactement le type de confusion que R340/R341 cherchent à éliminer.

Je ne considérerais donc pas `519/519` comme un résultat actuellement vérifié simplement parce qu'il apparaît dans README.

---

# 52. Autre divergence actuelle : les artefacts R340/R341 ne sont pas tous au même niveau de fraîcheur

Le `rule_registry.json` actuel est :

```text
version 6
20 règles
```

alors que `rule_divergence_matrix.json` reste explicitement construit autour de :

```text
registry_version = 5
registered_rules = 18
```

C'est un point important.

Cela ne signifie pas que le code est faux.

Cela signifie :

```text
registry actuel
       ≠
matrix de divergence actuelle
```

et donc que la matrice doit être régénérée avant de pouvoir être utilisée comme état courant.

C'est précisément le genre de problème que notre futur système devrait détecter automatiquement.

---

# 53. C'est même un excellent premier cas d'utilisation du futur système

Le nouveau moteur pourrait détecter :

```text
registry.version = 6
matrix.registry_version = 5
```

et produire automatiquement :

```text
RULE_DIVERGENCE_DETECTED
```

puis :

```text
severity = HIGH
```

et :

```text
first_reflex =
regenerate_or_reconcile_divergence_matrix
```

L'agent n'aurait alors plus besoin d'attendre que quelqu'un remarque manuellement la divergence.

---

# 54. La règle méta que je recommande d'ajouter conceptuellement

Je la formulerais ainsi :

> **Après toute tâche produisant une erreur, une correction, une divergence, une nouvelle information importante, une nouvelle règle ou un résultat inattendu, l'agent doit effectuer une rétrospective causale et procédurale. Il doit reconstruire le parcours réel, identifier la première divergence détectable, rechercher les règles déjà applicables, déterminer le premier réflexe qui aurait pu éviter les étapes inutiles, comparer le parcours réel au parcours minimal sûr, puis déterminer si une règle existante doit être renforcée ou si une nouvelle règle candidate doit être créée. Une nouvelle règle ne devient active qu'après normalisation, déduplication, analyse des conflits, tests et validation indépendante.**

C'est, selon moi, **la bonne traduction architecturale de ton idée** dans ARTCB.

---

# 55. Et la conséquence la plus importante

Le système ne doit plus seulement apprendre :

```text
"QUOI FAIRE"
```

Il doit apprendre :

```text
"QUAND LE FAIRE"
```

et encore mieux :

```text
"QUEL EST MON PREMIER RÉFLEXE
QUAND JE RECONNAIS CE TYPE DE SITUATION ?"
```

On passe ainsi de :

```text
Knowledge
```

à :

```text
Procedural Knowledge
```

puis à :

```text
Operational Reflex
```

C'est une évolution beaucoup plus profonde qu'une simple liste de règles.

---

# 56. État global de l'audit

### Architecture actuelle

```text
                    ARTCB
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
     RULES          AGENTS        PROOF
        │             │             │
   registry       runtime       telemetry
   lineage        context       evidence
   coverage       identity      divergence
        │             │             │
        └─────────────┼─────────────┘
                      │
                      ▼
                 MANQUE ACTUEL
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
    RETROSPECTIVE            PROCEDURAL
       ENGINE                 LEARNING
          │                       │
          └───────────┬───────────┘
                      ▼
                FIRST REFLEX
                      │
                      ▼
             RULE LIFECYCLE
```

### Conclusion technique

**Le socle nécessaire est déjà largement présent dans le code.**

Le principal travail restant n'est donc pas de « créer un système de règles », mais de **relier les systèmes déjà existants** :

```text
Corpus
   ↓
Registry
   ↓
Applicability
   ↓
First Reflex
   ↓
Execution
   ↓
Telemetry
   ↓
Evidence
   ↓
Retrospective
   ↓
Root Cause
   ↓
Lesson
   ↓
Semantic Dedup
   ↓
Conflict Resolution
   ↓
Rule Candidate
   ↓
Test
   ↓
Validation
   ↓
Active Rule
```

Et surtout, il faut que **la nouvelle règle soit une conséquence vérifiable de l'expérience**, pas simplement une phrase ajoutée au prompt.

### Priorité que je retiens pour la suite

**1. Semantic rule model + lineage enrichi**
**2. `FIRST_REFLEX` + `APPLICABILITY_PHASE`**
**3. Retrospective Engine**
**4. Root-cause / actual-vs-optimal path**
**5. Candidate Rule Engine**
**6. Semantic deduplication**
**7. Conflict / supersession engine**
**8. Tests de non-régression et contre-exemples**
**9. Intégration runtime / telemetry**
**10. Seulement ensuite activation automatique des nouvelles règles**

Cela permet de faire évoluer l'agent **sans créer une seconde hiérarchie de vérité et sans transformer son apprentissage en modification incontrôlée de ses propres règles ou de ses droits**.

Le point le plus urgent que l'audit croisé révèle par ailleurs est que **R341 et les artefacts de couverture doivent être resynchronisés avec le registre actuel v6/20 règles avant de servir de représentation canonique de l'état des règles**. C'est une tâche distincte du futur moteur de learning, mais elle entre directement dans son premier réflexe : **toujours vérifier que les artefacts de connaissance qu'il utilise décrivent bien le même état du dépôt.**
