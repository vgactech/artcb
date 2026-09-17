# Audit — cartographie d’intégration `REASONING_RECORD + ReferenceID + FIRST_REFLEX + EARLIEST_DETECTABLE_POINT`

J’ai repris l’audit directement sur le dépôt distant `vgactech/artcb`, branche `main`.

[Dépôt GitHub ARTCB — main](https://github.com/vgactech/artcb/tree/main?utm_source=chatgpt.com)

## 0. État exact au moment de l’audit

Le `main` distant est maintenant sur :

```text
6f86fb3f8f6c0084dc244e68934031f4470a3bd4
```

Dernier commit :

```text
fix(vpqc2): certif_vpqc2_x4 v2 — wallet_name + passphrase par nœud
```

Horodatage :

```text
2026-09-17T09:06:46Z
```

Il est important de signaler ce changement : le HEAD n’est plus le `0483b309...` utilisé dans l’audit précédent. Le nouveau commit ajoute notamment `scripts/certif_vpqc2_x4.py` et le rapport de certification VPQC2. Le dépôt indique explicitement `CERTIFIED_100=false` pour cette certification.

**Donc la cartographie ci-dessous est faite contre le code actuel `6f86fb3...`, et non contre un ancien snapshot.**

---

# 1. Résultat principal

La bonne nouvelle est que nous n’avons **pas besoin de construire un nouveau système depuis zéro**.

Le dépôt possède déjà presque toutes les briques :

```text
                    EXISTANT
                       │
                       ├── Context Contract
                       │
                       ├── ReasoningID canonique
                       │
                       ├── journal de raisonnement
                       │
                       ├── journal afterAgentThought
                       │
                       ├── mémoire agent
                       │
                       ├── événements idempotents
                       │
                       ├── Rule Telemetry
                       │
                       └── blockchain / PoL
                                │
                                ▼
                    CE QUI MANQUE
                                │
              ┌─────────────────┴─────────────────┐
              │                                   │
       REASONING_RECORD                    RETROSPECTIVE
              │                                   │
       ReferenceID                         EARLIEST_DETECTABLE_POINT
              │                                   │
       FIRST_REFLEX                              │
              └─────────────────┬─────────────────┘
                                ▼
                     LEARNING / NEW RULE
```

Le problème actuel est donc principalement **un problème de liaison entre les briques**, pas d'absence totale de technologie.

---

# 2. Cartographie globale des points d'insertion

| Élément                     | Fichier actuel                        | Fonction / zone             | État                 | Intégration proposée           |
| --------------------------- | ------------------------------------- | --------------------------- | -------------------- | ------------------------------ |
| `REASONING_RECORD`          | `scripts/artcb_reason_log.py`         | `append_reason()`           | EXISTE partiellement | Étendre                        |
| contexte d'exécution        | `src/artcb/agent_context_contract.py` | `build_context_contract()`  | EXISTE               | Réutiliser                     |
| identité raisonnement       | `src/artcb/reasoning/canonical.py`    | `canonicalize_text()`       | EXISTE               | Réutiliser                     |
| `ReasoningID`               | même fichier                          | `reasoning_id()`            | EXISTE               | Réutiliser                     |
| `ReferenceID`               | aucun moteur central identifié        | —                           | ABSENT               | Créer                          |
| `FIRST_REFLEX`              | aucun champ/moteur trouvé             | —                           | ABSENT               | Créer                          |
| `EARLIEST_DETECTABLE_POINT` | aucun champ/moteur trouvé             | —                           | ABSENT               | Créer                          |
| observation                 | `ai_routes.py` / runtime              | `/ai/memo`, `/agent/events` | EXISTE               | enrichir                       |
| résultat                    | `AgentRuntime.commit_event()`         | `commit_event()`            | EXISTE               | rattacher au record            |
| preuves                     | Rule Telemetry                        | `applied_confirmed`         | EXISTE               | réutiliser                     |
| validation                  | `rules/telemetry.py`                  | états de règle              | EXISTE               | brancher                       |
| apprentissage               | mémoire / PoL                         | `ai_memo`, `ai_think`       | PARTIEL              | ajouter retrospective          |
| activation règle            | registry                              | `rule_registry.json`        | EXISTE               | ne pas activer automatiquement |

---

# 3. Point d'intégration n°1 — `scripts/artcb_reason_log.py`

## Code actuel

Fichier :

```text
scripts/artcb_reason_log.py
```

Fonction centrale :

```text
append_reason()
```

Le journal produit actuellement notamment :

```text
ts_ns
kind
chars
sha256
text
includes_thinking
artcb_bound
note
```

Le code actuel calcule déjà un SHA-256 du texte et journalise avec `time.time_ns()`.

### Ce que cela signifie

Le projet possède déjà une **identité temporelle et cryptographique du texte journalisé**.

Mais :

```text
SHA256(text)
```

n'est pas encore :

```text
ReasoningID
```

et encore moins :

```text
ReferenceID
```

Il faut donc éviter de mélanger ces trois identités.

---

## Architecture correcte

```text
text
 │
 ├── text_sha256
 │
 └── canonicalize_text()
          │
          ▼
      ReasoningID
```

Puis :

```text
ReasoningID
     │
     └── REASONING_RECORD
              │
              ├── ReferenceID
              ├── FIRST_REFLEX
              ├── observations
              ├── evidence
              └── result
```

### Modification minimale

Étendre `append_reason()` avec quelque chose du genre :

```text
reasoning_id
task_id
agent_id
node_id
context_hash
reference_ids
first_reflex
earliest_detectable_point
```

**Mais surtout pas `thinking = proof`.**

Le dépôt affirme déjà explicitement que le journal `afterAgentThought` n'est pas une preuve du CoT privé du modèle. Le hook marque lui-même `ui_equals_hook=NOT_PROVEN_BY_ARCHITECTURE`.

C'est une contrainte architecturale qu'il faut conserver.

---

# 4. Point d'intégration n°2 — `agent_context_contract.py`

C'est probablement **le meilleur point d'ancrage du système**.

Fichier :

```text
src/artcb/agent_context_contract.py
```

Fonction :

```text
build_context_contract()
```

Le contrat actuel contient déjà :

```text
chain_height
chain_tip
code_sha
code_branch
release_integrity
agent_id
provider
owner_address
parent_agent_id
task_id
node_id
role
pbft
scope
active_decisions
revoked_decisions
open_bugs
validated_facts
not_proven
constraints
```

Le contrat est explicitement conçu comme :

> ce que l'agent a reçu — pas son raisonnement privé.

C'est exactement ce qu'il faut.

---

## Ajout proposé

Ne pas créer un deuxième système de contexte.

Ajouter au contrat :

```json
"context_snapshot": {
    "context_hash": "...",
    "captured_at_ns": 123456789
}
```

Puis le `REASONING_RECORD` référence :

```json
"context_ref": {
    "context_hash": "...",
    "contract_version": "297.1"
}
```

### Pourquoi ?

Parce qu'un agent doit pouvoir dire :

> « Ce raisonnement a été effectué avec le contexte que j'avais à cet instant. »

Et non :

> « Voici le contexte actuel, que nous avons peut-être modifié depuis. »

C'est une différence fondamentale.

---

# 5. Point d'intégration n°3 — `src/artcb/reasoning/canonical.py`

C'est ici que l'audit devient particulièrement intéressant.

Le dépôt possède déjà :

```text
CanonicalReasoning
```

avec :

```text
canonical_bytes()
reasoning_hash()
reasoning_id()
to_dict()
```

Le `ReasoningID` est dérivé d'une représentation structurelle canonique, et non simplement du texte humain.

Le protocole actuel est :

```text
r334-canonical-reasoning-v2
```

---

## C'est exactement la bonne base pour `REASONING_RECORD`

Le système peut devenir :

```text
Question / observation
        │
        ▼
   IR Encoder
        │
        ▼
CanonicalReasoning
        │
        ├── reasoning_hash
        │
        └── reasoning_id
```

Puis :

```text
reasoning_id
      │
      ▼
REASONING_RECORD
```

### Point très important

Je **ne recommande pas** de créer un autre hash appelé `reasoning_hash_v2`, `reasoning_uid`, etc.

Il existe déjà une identité canonique.

Il faut **réutiliser `ReasoningID`**.

Le rapport R333/R334 confirme également que le texte humain est considéré comme une vue et que des vues linguistiques différentes peuvent correspondre au même raisonnement structurel.

---

# 6. `ReferenceID` — le morceau réellement manquant

J'ai recherché directement dans le dépôt :

```text
FIRST_REFLEX
EARLIEST_DETECTABLE_POINT
ReferenceID
```

Les deux premiers ne sont pas présents comme mécanisme existant.

Pour `ReferenceID`, je n'ai pas trouvé de moteur central correspondant au modèle que nous avons défini.

Donc ici nous sommes bien face à un **nouveau composant architectural nécessaire**.

---

# 7. Où créer `ReferenceID`

Je recommande :

```text
src/artcb/reasoning/references.py
```

avec une abstraction unique :

```text
Reference
```

### Exemple

```json
{
  "reference_id": "REF-000123",
  "type": "source_code",
  "repository": "vgactech/artcb",
  "commit": "6f86fb3f8f6c0084dc244e68934031f4470a3bd4",
  "path": "src/artcb/agent_runtime.py",
  "symbol": "AgentRuntime.commit_event",
  "line_start": 112,
  "line_end": 150,
  "sha256": "...",
  "retrieved_at": "2026-09-17T09:10:00Z",
  "why_referenced": "Cette fonction assure la persistance idempotente de l'événement agent."
}
```

---

# 8. Pourquoi `why_referenced` est indispensable

C'est une amélioration importante par rapport à un simple lien fichier/ligne.

Un agent pourrait écrire :

```text
src/artcb/agent_runtime.py:112
```

Mais un autre agent doit ensuite deviner :

> « Pourquoi cette ligne est-elle citée ? »

Ce n'est pas acceptable pour une mémoire agent destinée à être reprise par d'autres agents.

Il faut donc :

```text
REFERENCE
    │
    ├── où ?
    ├── quelle version ?
    ├── quelle fonction ?
    ├── quelles lignes ?
    ├── quelle empreinte ?
    └── pourquoi ?
```

---

# 9. Les quatre types de `ReferenceID` à implémenter en priorité

## A. Code

```text
type = source_code
```

avec :

```text
repository
commit
path
symbol
line_start
line_end
sha256
```

---

## B. Commande

```text
type = command
```

Exemple :

```json
{
  "reference_id": "REF-000124",
  "type": "command",
  "command": "pytest tests/test_e2e300_thinking_journal.py -q",
  "cwd": "/workspace/artcb",
  "timestamp": "...",
  "exit_code": 0,
  "stdout_sha256": "...",
  "stderr_sha256": "...",
  "duration_ms": 1842
}
```

Cela transforme :

> « J'ai lancé les tests »

en :

> « Voici exactement quel test, dans quel environnement, à quelle date, avec quel résultat. »

---

## C. Document

```text
type = document
```

avec :

```text
path
commit
heading
line_start
line_end
sha256
```

---

## D. Rule

```text
type = rule
```

avec :

```text
rule_id
registry_version
semantic_hash
status
source
```

Cela est essentiel puisque le projet possède déjà Rule Telemetry.

---

# 10. Point d'intégration n°4 — `AgentRuntime.commit_event()`

Fichier :

```text
src/artcb/agent_runtime.py
```

Fonction :

```text
AgentRuntime.commit_event()
```

Cette fonction possède déjà un mécanisme d'idempotence.

Elle stocke notamment :

```text
event_id
agent_id
kind
content_sha256
block_index
block_hash
graph_id
committed_at
status
```

C'est donc un excellent endroit pour rattacher le résultat final d'un `REASONING_RECORD`.

---

## Mais attention

Je ne recommande pas de transformer `commit_event()` en moteur de raisonnement.

Son rôle doit rester :

```text
EVENT
   ↓
idempotence
   ↓
persistence
```

Le `REASONING_RECORD` doit être préparé **avant** le commit.

Donc :

```text
REASONING_RECORD
       │
       ▼
ACTION
       │
       ▼
RESULT
       │
       ▼
commit_event()
```

---

# 11. Point d'intégration n°5 — `/api/v1/agent/events`

Fichier :

```text
src/api/agent_protocol_routes.py
```

Fonction :

```text
agent_event()
```

Le endpoint fait actuellement :

```text
EventBody
 ↓
SHA256(content)
 ↓
MemoRequest
 ↓
ai_memo()
 ↓
commit_event()
```

Le code actuel appelle explicitement `ai_memo()` puis `commit_event()`.

C'est donc **le meilleur point d'entrée API** pour recevoir un `REASONING_RECORD` structuré.

---

# 12. Évolution minimale de `EventBody`

Aujourd'hui :

```text
event_id
kind
content
visibility
tags
session_id
```

Ajouter :

```text
reasoning_id
reference_ids
first_reflex
earliest_detectable_point
task_id
```

Mais avec une règle :

### Ces champs doivent être des métadonnées structurées.

Pas les mélanger artificiellement au texte.

Donc :

```json
{
  "event_id": "...",
  "kind": "observation",
  "content": "...",

  "reasoning": {
    "reasoning_id": "R...",
    "reference_ids": ["REF-123"],
    "first_reflex": "...",
    "earliest_detectable_point": "..."
  }
}
```

---

# 13. Point d'intégration n°6 — `ai_memo()`

Fichier :

```text
src/api/ai_routes.py
```

Fonction :

```text
ai_memo()
```

C'est le deuxième point extrêmement important.

Le système injecte déjà automatiquement un contexte blockchain dans le mémo.

Le code construit actuellement :

```text
AI MEMO
Agent
Session
Timestamp
Tags
ARTCB CONTEXT
content
```

puis encode ce texte et le grave en bloc.

---

## Ce qu'il faut ajouter

Ne pas uniquement injecter le contexte **dans le texte**.

Il faut également conserver une structure machine :

```json
{
  "reasoning_id": "...",
  "context_hash": "...",
  "reference_ids": [],
  "first_reflex": {},
  "earliest_detectable_point": {},
  "evidence_ids": [],
  "retrospective_id": "..."
}
```

dans les métadonnées du bloc.

---

# 14. Pourquoi le texte seul ne suffit pas

Actuellement un mémo ressemble conceptuellement à :

```text
[AI MEMO — BUG]
Agent: ...
Session: ...
Timestamp: ...
Tags: ...

[ARTCB CONTEXT...]
...

Le problème semble être DNS...
```

Pour un humain c'est lisible.

Pour un agent suivant, c'est beaucoup moins fiable.

Il doit parser le texte pour deviner :

```text
quel est le problème ?
quelle observation ?
quelle preuve ?
quelle référence ?
quelle conclusion ?
```

Nous voulons l'inverse :

```text
machine-readable structure
        +
human-readable explanation
```

Les deux doivent coexister.

---

# 15. Point d'intégration n°7 — `/ai/think`

Fichier :

```text
src/api/ai_routes.py
```

Fonction :

```text
ai_think()
```

Le endpoint actuel fait :

```text
question
 ↓
think_text
 ↓
MiningPipeline.run_from_text()
 ↓
graph
 ↓
PoL
 ↓
bloc éventuel
```

C'est ici que le `ReasoningID` peut être produit naturellement.

---

# 16. Mais il faut éviter une erreur architecturale

Le nom :

```text
ai_think()
```

ne doit pas signifier :

```text
ARTCB possède le CoT privé du modèle.
```

Le code actuel est honnête sur cette limitation.

Il faut donc enregistrer :

```text
reasoning_id
```

pour le **raisonnement structuré/surfaced**, pas prétendre avoir enregistré les pensées internes privées du modèle.

C'est parfaitement compatible avec R333/R334.

---

# 17. `FIRST_REFLEX` — où l'implémenter ?

Je recommande **pas dans `ai_think()` lui-même**.

Il doit être une abstraction indépendante :

```text
src/artcb/reasoning/first_reflex.py
```

Fonction centrale :

```text
resolve_first_reflex()
```

Entrées :

```text
task
context
active_rules
observations
```

Sortie :

```json
{
  "trigger": "...",
  "applicability_phase": "TASK_START",
  "action": "...",
  "priority": "P0",
  "rule_id": "RT-002"
}
```

---

# 18. Exemple concret ARTCB

Supposons :

```text
TASK:
Le site principal ne répond plus.
```

Ancien raisonnement :

```text
1. vérifier backend
2. vérifier FastAPI
3. vérifier blockchain
4. vérifier proxy
5. vérifier DNS
```

Le système amélioré :

```text
TASK
 ↓
FIRST_REFLEX
 ↓
DNS + endpoint health
```

Pourquoi ?

Parce que si le symptôme est :

```text
domaine inaccessible
```

une vérification DNS est un signal très précoce.

---

# 19. `EARLIEST_DETECTABLE_POINT`

C'est encore plus intéressant.

Le système doit enregistrer après résolution :

```json
{
  "earliest_detectable_point": {
    "step": 1,
    "signal": "DNS resolution failure",
    "actual_detection_step": 5,
    "avoidable_steps": 4
  }
}
```

Cela ne signifie **pas** :

> supprimer quatre vérifications.

Cela signifie :

> déplacer la bonne vérification plus tôt.

C'est fondamental.

---

# 20. La métrique que je recommande

Ajouter :

```text
actual_steps
mandatory_steps
avoidable_steps
first_detectable_step
first_reflex_step
```

Puis éventuellement :

```text
detection_efficiency =
    avoidable_steps / actual_steps
```

Mais cette métrique doit rester une métrique d'analyse.

Elle ne doit jamais conduire automatiquement l'agent à supprimer :

```text
sécurité
validation
preuves
tests
certification
```

---

# 21. Point d'intégration n°8 — Rule Telemetry

Le projet possède déjà les états :

```text
seen
checked
applied
applied_confirmed
violated
corrected
not_proven
```

et `applied_confirmed` est volontairement protégé contre les simples affirmations/thinking-only. Le rapport R337 le documente explicitement.

C'est exactement le mécanisme qu'il faut utiliser pour le futur apprentissage.

---

# 22. Flux correct pour une nouvelle règle

```text
REASONING
    ↓
OBSERVATION
    ↓
EVIDENCE
    ↓
RETROSPECTIVE
    ↓
LESSON
    ↓
CANDIDATE RULE
    ↓
TEST
    ↓
VALIDATION
    ↓
ACTIVE RULE
```

Et surtout :

```text
thinking
   ≠
validation
```

---

# 23. Le dépôt possède déjà la philosophie nécessaire

Le corpus Rule Telemetry montre déjà que les règles peuvent être distinguées entre :

```text
appliqué
appliqué confirmé
non prouvé
```

et le système refuse de transformer automatiquement une simple réflexion en preuve.

Donc le futur moteur d'apprentissage doit **s'appuyer sur ce système**, pas en créer un parallèle.

---

# 24. Point d'intégration n°9 — `rule_registry.json`

C'est ici qu'il faut être particulièrement prudent.

Le futur agent pourrait produire :

```text
CANDIDATE_RULE
```

mais il ne doit pas directement faire :

```text
CANDIDATE_RULE → ACTIVE
```

Le pipeline doit être :

```text
CANDIDATE
    ↓
semantic_hash
    ↓
dedupe
    ↓
conflict analysis
    ↓
test
    ↓
evidence
    ↓
validation
    ↓
registry
```

L'audit R344 avait justement identifié que la normalisation/déduplication sémantique du corpus n'était pas complètement réalisée. Le rapport signale notamment l'absence de `semantic_hash` et le fait que les marqueurs ne correspondent pas automatiquement à des règles sémantiques uniques.

---

# 25. Point d'intégration n°10 — `ai_routes` + blockchain

Le bloc actuel contient déjà :

```text
learning_source
agent_id
session_id
tags
memo_type
principal_kind
parent_block_index
```

dans `public_symbols`.

C'est l'endroit naturel pour ajouter :

```text
reasoning_id
context_hash
reference_ids
first_reflex_id
retrospective_id
```

### Exemple

```json
{
  "learning_source": "ai:memo:lesson",
  "agent_id": "agent_x",
  "session_id": "sess_x",

  "reasoning_id": "R...",
  "context_hash": "sha256:...",
  "reference_ids": [
    "REF-000123",
    "REF-000124"
  ],
  "first_reflex_id": "FR-0007",
  "retrospective_id": "RET-0042"
}
```

Ainsi la blockchain ne stocke pas seulement :

> « une leçon »

mais :

> **quelle leçon, issue de quel raisonnement, dans quel contexte, avec quelles références et quelle rétrospective.**

---

# 26. Point d'intégration n°11 — les hooks Cursor

Le dépôt possède déjà :

```text
.cursor/hooks/after_agent_thought.py
.cursor/hooks/pre_compact.py
.cursor/hooks/session_start.py
```

Les hooks utilisent déjà `append_reason()`.

C'est donc un excellent endroit pour capturer :

```text
task_id
session_id
timestamp
agent/provider
```

mais **pas pour fabriquer une preuve de raisonnement privé**.

---

# 27. `pre_compact` devient particulièrement important

Le hook `pre_compact` existe déjà.

Il journalise le moment où le contexte est compacté.

C'est intéressant pour notre architecture :

```text
REASONING_RECORD
       │
       ├── context_hash_before_compaction
       │
       └── compaction_event_id
```

Puis après reprise :

```text
new context
   │
   └── new context_hash
```

Cela permettrait de savoir :

> « Ce raisonnement a été produit avant ou après une perte/compaction du contexte ? »

C'est une information extrêmement utile pour diagnostiquer les erreurs de continuité agent.

---

# 28. Le test de cohérence devient alors possible

On pourrait avoir :

```text
TASK-123
 │
 ├── context C1
 ├── reasoning R1
 ├── references REF1..REF4
 ├── first reflex FR1
 ├── actions A1..A5
 ├── evidence E1..E3
 ├── result RES1
 └── retrospective RET1
```

Puis :

```text
RET1
 │
 ├── root_cause
 ├── earliest_detectable_point
 ├── avoidable_steps
 └── candidate_rule
```

C'est exactement le graphe de provenance qui manque actuellement.

---

# 29. Les tests existants à réutiliser

### Context Contract

```text
tests/test_e2e296_context_contract.py
```

Le dépôt le référence directement pour `build_context_contract()`.

Il faut y ajouter :

```text
context_hash stable
task_id conservé
agent_id conservé
reasoning record référence valide
```

---

### Thinking journal

```text
tests/test_e2e300_thinking_journal.py
```

Le test actuel vérifie déjà l'écriture append-only via `append_reason()`.

Il faut ajouter :

```text
reasoning_id
reference_ids
task_id
context_hash
```

---

### Reasoning canonical

Le dépôt possède déjà la batterie R333/R334.

Le rapport indique notamment :

```text
T3 multilingue → PASS
T4 prémisses différentes → PASS
```

avec :

```text
src/artcb/reasoning/canonical.py
tests/test_r333_reasoning_canonical_multilingual.py
```

Il faut donc **réutiliser ces tests**, pas reconstruire l'identité canonique.

---

### Agent Runtime

Le dépôt possède déjà des tests d'idempotence sur `commit_event()`.

Il faudra ajouter :

```text
same reasoning_id + same event → idempotent
same event_id + different reasoning record → conflict
```

---

# 30. Cartographie fonctionnelle finale

Voici la chaîne que je recommande maintenant.

```text
┌──────────────────────────────┐
│ TASK START                   │
│ agent_protocol / ai endpoint │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ build_context_contract()     │
│ agent_context_contract.py    │
└──────────────┬───────────────┘
               │
               ▼
        context_hash
               │
               ▼
┌──────────────────────────────┐
│ RULE RESOLUTION               │
│ rule registry / telemetry    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ FIRST_REFLEX                 │
│ first_reflex.py              │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ OBSERVATION                  │
│ ai_memo / agent_event        │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ CANONICAL REASONING          │
│ reasoning/canonical.py       │
│ → ReasoningID                │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ REFERENCES                   │
│ reasoning/references.py      │
│ → ReferenceIDs               │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ ACTIONS                      │
│ commands / API / tools       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ EVIDENCE                     │
│ telemetry / command results  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ RESULT                       │
│ AgentRuntime.commit_event()  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ RETROSPECTIVE                │
│ earliest_detectable_point    │
│ root cause                   │
│ avoidable steps              │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ CANDIDATE LESSON / RULE      │
└──────────────┬───────────────┘
               │
               ▼
       TEST + COUNTEREXAMPLE
               │
               ▼
       VALIDATED / REJECTED
               │
               ▼
          RULE REGISTRY
```

---

# 31. Ordre de modification minimal

Je recommande de **ne pas modifier dix fichiers simultanément**.

### Phase 1 — fondation

Créer :

```text
src/artcb/reasoning/references.py
src/artcb/reasoning/records.py
```

avec :

```text
Reference
ReferenceID
ReasoningRecord
```

---

### Phase 2 — rattacher au contexte

Modifier :

```text
src/artcb/agent_context_contract.py
```

pour exposer :

```text
context_hash
```

et permettre au `ReasoningRecord` de référencer précisément le contexte.

---

### Phase 3 — rattacher au raisonnement

Modifier :

```text
src/artcb/reasoning/canonical.py
```

**le moins possible**.

Il possède déjà le mécanisme d'identité.

On ajoute surtout un adaptateur :

```text
CanonicalReasoning
        ↓
ReasoningRecord
```

---

### Phase 4 — journal

Modifier :

```text
scripts/artcb_reason_log.py
```

pour enregistrer le `ReasoningRecord`.

---

### Phase 5 — API agent

Modifier :

```text
src/api/agent_protocol_routes.py
```

puis :

```text
src/api/ai_routes.py
```

pour accepter et produire les métadonnées.

---

### Phase 6 — retrospective

Créer :

```text
src/artcb/reasoning/retrospective.py
```

avec :

```text
analyze_task()
find_earliest_detectable_point()
calculate_avoidable_steps()
derive_lesson()
```

---

### Phase 7 — apprentissage

Seulement ensuite :

```text
candidate rule
semantic dedupe
conflict
test
validation
registry
```

---

# 32. Ce que je déconseille absolument

## Ne pas faire ceci

```text
afterAgentThought
       ↓
nouvelle règle
       ↓
ACTIVE
```

Cela transformerait une réflexion en autorité.

---

## Ne pas faire ceci

```text
text SHA
   =
ReasoningID
```

Le dépôt possède déjà un système de raisonnement canonique plus riche.

---

## Ne pas faire ceci

```text
file + line
```

sans :

```text
commit
symbol
why_referenced
sha256
```

Sinon une référence peut devenir ambiguë après modification du code.

---

## Ne pas faire ceci

```text
earliest_detectable = first thing agent happened to check
```

Il faut distinguer :

```text
première chose vérifiée
```

de :

```text
première chose qui aurait objectivement permis de détecter le problème.
```

---

# 33. Une découverte importante pendant cet audit

Le dépôt actuel possède déjà une architecture qui commence à ressembler à un **système de mémoire procédurale**, mais elle est fragmentée entre plusieurs mécanismes.

On trouve actuellement :

```text
ReasoningID
Context Contract
agent_reasoning.jsonl
agent_thoughts.jsonl
precompact.jsonl
AgentRuntime
AI memos
PoL
Rule Telemetry
Rule Registry
Rule Lineage
```

Le problème est donc moins :

> « ARTCB ne mémorise rien »

que :

> **« ARTCB mémorise plusieurs dimensions, mais elles ne sont pas encore reliées par une identité/provenance commune. »**

C'est précisément là que `REASONING_RECORD + ReferenceID + FIRST_REFLEX + EARLIEST_DETECTABLE_POINT` devient utile.

---

# 34. État de chaque composant

| Composant                           | État actuel                      |
| ----------------------------------- | -------------------------------- |
| Context Contract                    | **CODE**                         |
| Context hash                        | **CODE**                         |
| ReasoningID                         | **CODE + tests**                 |
| Human view                          | **CODE**                         |
| Agent reasoning journal             | **CODE + tests**                 |
| afterAgentThought journal           | **CODE**                         |
| Pre-compact journal                 | **CODE**                         |
| Agent event idempotence             | **CODE + tests**                 |
| Rule Telemetry                      | **CODE + tests**                 |
| Rule lineage                        | **PARTIEL**                      |
| ReferenceID central                 | **ABSENT**                       |
| ReasoningRecord structuré           | **ABSENT**                       |
| FIRST_REFLEX                        | **ABSENT**                       |
| EARLIEST_DETECTABLE_POINT           | **ABSENT**                       |
| Retrospective engine                | **ABSENT/PARTIEL**               |
| Automatic lesson extraction         | **PARTIEL**                      |
| Automatic candidate-rule generation | **ABSENT comme boucle complète** |
| Automatic semantic dedupe           | **PARTIEL**                      |
| Automatic validation → active rule  | **DOIT RESTER CONTRÔLÉE**        |

---

# 35. Conclusion de l'audit

La cartographie confirme l'hypothèse de l'audit précédent, mais avec une précision supplémentaire :

### Le point central ne doit pas être `FIRST_REFLEX`.

Le véritable objet central doit être :

```text
REASONING_RECORD
```

et autour de lui :

```text
                     REASONING_RECORD
                            │
       ┌────────────┬───────┼─────────┬─────────────┐
       ▼            ▼       ▼         ▼             ▼
  ContextHash   ReasoningID References Reflex     Evidence
       │            │          │         │            │
       └────────────┴──────────┴─────────┴────────────┘
                            │
                            ▼
                         Result
                            │
                            ▼
                     Retrospective
                            │
                            ├── root cause
                            ├── earliest detectable point
                            ├── avoidable steps
                            └── lesson
                                      │
                                      ▼
                               Candidate Rule
```

Et le rôle de `FIRST_REFLEX` devient très clair :

> **ce n'est pas le raisonnement complet ; c'est la première action procédurale déterministe qu'une règle recommande lorsqu'un signal donné apparaît.**

C'est ce qui permet ensuite de mesurer :

```text
Signal apparu
     ↓
FIRST_REFLEX
     ↓
détection
     ↓
résolution
     ↓
rétrospective
     ↓
apprentissage
```

Le dépôt possède déjà les fondations nécessaires pour construire cela sans remettre en cause `ReasoningID`, `Context Contract`, `AgentRuntime` ou Rule Telemetry. Les changements minimaux sont donc concentrés autour de **deux nouveaux objets (`Reference`, `ReasoningRecord`) et deux nouveaux mécanismes (`FIRST_REFLEX`, `Retrospective`)**, puis leur branchement aux points d'entrée existants.

**Point de vigilance actuel :** le HEAD a changé depuis l'audit précédent avec le commit VPQC2 du 17 septembre ; les anciennes cartographies ou rapports qui mentionnent `0483b309...` doivent désormais être considérés comme historiques et non comme une description du code courant. Le nouveau rapport VPQC2 confirme par ailleurs explicitement que `CERTIFIED_100=false`.

La prochaine étape technique logique est donc **l'audit d'implémentation de niveau ligne** : déterminer, pour chacun de ces nouveaux objets, les lignes d'insertion exactes, les imports, les structures de données existantes à réutiliser, les tests à créer et surtout les risques de régression — avant toute modification du dépôt.
