# R398 — Audit 6 domaines : cartographie FAIT / RESTE À FAIRE
**Date :** 2026-09-20T22:30:00Z  
**SHA HEAD :** 3f02555 (main)  
**CERTIFIED_100 :** false  
**Avancement global estimé :** 76 %

---

## Domaine 1 — Audit/mapping : ce que le langage IA ARTCB fait déjà

### Ce qui EST FAIT ✅

| Module | Ce qu'il fait | R / SHA |
|--------|--------------|---------|
| `src/artcb/ir/encoder.py` | Encode tout texte en graphe IR (relations, concepts, patterns) — rule-based | Phase 1 |
| `src/artcb/ir/llm_encoder.py` | Path B : enrichissement LLM via IBM Bob CLI | R371 |
| `src/artcb/reasoning/langage_battery.py` | Batterie de tests du langage (matrice C2D, cross-compare) | R316/R320 |
| `src/artcb/reasoning/first_reflex.py` | Moteur réflexe R350–R354 — classification REFLEX_MEMORY/SECURITY/PQC | R350–R354 |
| `src/artcb/memory/concept_network.py` | Graphe conceptuel persistant — liens sémantiques inter-concepts | R-arch |
| `src/artcb/memory/concept_store.py` | Store de concepts typés (entités, actions, attributs, relations) | R-arch |
| `src/artcb/agents/explorer.py` + `critic.py` | Agents duels : Explorer (encode) + Critic (contre-analyse) | R-arch |
| `src/artcb/reasoning/record.py` | Enregistrement forensic de chaque raisonnement (ID, SHA, timestamp) | R390 |
| `src/artcb/reasoning/canonical.py` | Forme canonique des concepts pour dédoublonnage cross-graphe | R-arch |
| `src/artcb/ir/concept_lexicon.py` | Lexique de 1000+ concepts normalisés | R-arch |
| `rules/rule_corpus_index.json` | 230 entrées CR-* (RULE/DECISION/SPEC/LESSON/CHECK/CONVENTION) | R375/R381 |
| `rules/rule_registry.json` | 20 règles RT-* opérationnelles | R375 |
| `src/artcb/rules/telemetry.py` | Télémétrie corpus — counts, coverage, divergences | R375 |
| Logs `logs/316_langage_ia_matrix_latest.json` | Matrice de comparaison croisée C2D live | R316 |
| Logs `logs/322_c2d_multihote_latest.json` | Comparaison multi-hôte C2D | R322 |

### Ce qui RESTE À FAIRE ❌

| Manque | Description |
|--------|-------------|
| Analyse sémantique en temps réel | Résultats IR non exposés en live dans le frontend (GraphPage affiche le graphe mais pas les inférences courantes) |
| Comparaison croisée graphes | `reasoning/canonical.py` existe mais pas d'endpoint `/api/v1/ir/compare` public |
| Agent-ID dans les compteurs telemetry | `agent_id=Bob/Cursor` absent des compteurs R375 (limites documentées) |
| Classification CR-* manuelle | 230 entrées scan-auto, non classifiées par domaine sémantique |

---

## Domaine 2 — Log forensic nanoseconde : règles auto-activées à chaque modification

### Ce qui EST FAIT ✅

| Composant | Rôle | R |
|-----------|------|---|
| `src/artcb/trace/ns.py` (MODULE_VERSION 1.0.0) | Trace nanoseconde — `now_wall_ns()` + `now_mono_ns()` — every HTTP hit + book write | R390 |
| `src/artcb/trace/agent_run.py` (MODULE_VERSION 1.1.0) | `AgentExecutionRecord` — enregistre chaque run agent avec SHA, duration_ns, outcome | R396-B |
| `tests/conftest.py` | Hook pytest → `pytest_trace.jsonl` — toutes les suites de tests traçées | R396-C |
| `.bob/hooks/stop.py` | Auto-feedback R392 à la fin de chaque tour Bob + `AUDIT_STATUS` persisté | R396-A |
| `.bob/hooks/post_tool_use.py` | Trace post-outil dans `bob_tool_usage.jsonl` | R390 |
| `src/artcb/logging_config.py` | Config logging structuré JSON + nanoseconde | R390 |
| `MODULE_VERSION` | Présent sur **175 modules** (R390 auto-versioning) | R390 |
| `src/artcb/network/eligibility_gate.py` MODULE_VERSION 1.1.0 | Seul module avec version > 1.0.0 à ce jour (R397) | R397 |

### Ce qui RESTE À FAIRE ❌

| Manque | Description | Priorité |
|--------|-------------|---------|
| Auto-bump MODULE_VERSION après chaque modif | Actuellement manuel — seul R397 bumpe 1.0.0→1.1.0 | HAUTE |
| Tests domaines mainnet live avant validation | DV-01…DV-07 : DV-01 C, DV-02 C, DV-06 B, DV-07 C encore bloqués | HAUTE |
| Fingerprint SHA-256 par module re-généré sur chaque commit | L-053 : procédure définie mais pas automatisée dans CI | MOYENNE |
| Logs systemd nœuds live lus après chaque déploiement | Manuel — pas de centralisation Loki/Grafana | BASSE |

---

## Domaine 3 — Versioning fichier/module après chaque modification

### Ce qui EST FAIT ✅

- **R390 :** `MODULE_VERSION = '1.0.0'` ajouté sur 175 modules — automatiquement injecté à la création.
- **R397 :** Seul module avec version bumée post-R390 : `eligibility_gate.py` → `1.1.0`.
- Convention : `R<n>` dans le commentaire de version identifie la raison du bump.

### Ce qui RESTE À FAIRE ❌

| Manque | Description |
|--------|-------------|
| Bump automatique | Aucun script ne bump automatiquement la version du module modifié. C'est manuel. |
| Changelog par module | Pas de `CHANGELOG_<module>.md` — seuls les rapports R-* servent de trace |
| Script `bump_module_version.py` | À créer : `scripts/artcb_bump_module_version.py <fichier>` — incrémente PATCH |

**⚡ Action recommandée (TASK-VERSIONING) :** créer `scripts/artcb_bump_module_version.py` qui :
1. Lit `MODULE_VERSION` du fichier
2. Incrémente PATCH (1.0.0 → 1.0.1 ou 1.1.0 → 1.1.1)
3. Met à jour le commentaire `# R<n> — <raison>`
4. Émet un log dans `data/trace/module_version_history.jsonl`

---

## Domaine 4 — Frontend : P2P, Memory IA — AVANT / APRÈS (R398)

### AVANT (HEAD b146d5c)

| Fichier | Ce qui existait |
|---------|----------------|
| `frontend/src/pages/Memorize.tsx` | Page complète d'encodage/pool distribué visible dans l'app |
| `frontend/src/components/AgentPanel.tsx` | Composant "Agents duels" (Explorer/Critic) affichable |
| `frontend/src/api/client.ts` | `fetchP2PStatus`, `fetchP2PPeers`, `addP2PPeer`, `syncP2PAll`, `fetchPoolStatus`, `fetchPoolJobs`, `createPoolJob`, `processAllPoolIncoming`, `finalizePoolJob`, `fetchPoolPreferences`, `savePoolPreferences`, `runPoolMining` (12 fonctions) |
| `translations.ts` interface | `nav_memorize`, `nav_network`, `nav_agent_memory`, 18 clés `memorize_*` |
| `Home.tsx` | Lien checklist → `/memorize` |

### APRÈS (HEAD 3f02555) ✅

| Élément | État |
|---------|------|
| `Memorize.tsx` | ❌ SUPPRIMÉ |
| `AgentPanel.tsx` | ❌ SUPPRIMÉ |
| 12 fonctions P2P/Pool dans `client.ts` | ❌ SUPPRIMÉES — remplacées par commentaire explicatif |
| Interface `Translations` | Clés retirées (commentaires) — locales pas nettoyées (Partial<Translations>, sans impact TS) |
| `Home.tsx` checklist | `/memorize` → `/graph` |
| Backend P2P + Pool + AgentMemory | ✅ CONSERVÉS — `src/artcb/p2p/`, `src/artcb/pool/`, `src/artcb/memory/` intacts |
| Endpoints API `/p2p/*`, `/pool/*` | ✅ CONSERVÉS côté serveur |

---

## Domaine 5 — Auto-feedback / rétrospective après chaque tâche

### Ce qui EST FAIT ✅

| Composant | Détail |
|-----------|--------|
| `.bob/hooks/stop.py` (R396-A) | Lance `scripts/artcb_r392_auto_feedback.py --since HEAD~1` à chaque fin de tour |
| `scripts/artcb_r392_auto_feedback.py` | Analyse git diff, tests PASS/FAIL, génère un bloc avant/après dans `data/trace/bob_turns.jsonl` |
| `AUDIT_STATUS` persisté | `ok` / `failed` / `incomplete` — visible dans les logs |
| Distinction parallèle | Le feedback est lancé en **subprocess non-bloquant** — ne mélange pas le développement ARTCB avec la rétrospective |
| `FAIL-OPEN` | Une panne de feedback ne bloque pas le tour Bob |

### Ce qui RESTE À FAIRE ❌

| Manque | Description |
|--------|-------------|
| Rapport `.md` auto-généré | Le feedback écrit dans `bob_turns.jsonl` mais pas de rapport markdown horodaté auto |
| Points forts/faibles structurés | Format libre actuel — pas de template `FORCE / FAIBLESSE / ACTION_NEXT` normalisé |
| Métriques "fonctionnalités utilisées par ARTCB" | `bob_tool_usage.jsonl` existe mais pas d'agrégation par feature ARTCB |
| Retesté en live | La rétrospective locale n'inclut pas un re-test sur les nœuds live — à brancher sur TASK-006 |

---

## Domaine 6 — Cartographie des rules télémétriques par catégorie/domaine

### État actuel (R375/R381)

Architecture deux niveaux existante :

```
CORPUS  = CR-* (230 entrées) — scanner automatique — rules/rule_corpus_index.json
REGISTRY = RT-* (20 règles)  — opérationnel       — rules/rule_registry.json
```

### Classification actuelle des CR-* (R381)

| Statut | Count | Description |
|--------|-------|-------------|
| RULE | ~80 | Règle normative |
| DECISION | ~45 | Décision utilisateur D-* |
| LESSON | ~53 | Leçon L-* |
| SPEC | ~20 | Spécification technique |
| CHECK | ~15 | Gate de vérification |
| CONVENTION | ~10 | Convention de nommage/code |
| QUESTION | ~7 | Question ouverte |

### Domaines non encore organisés ❌

Les CR-* sont dans `rule_corpus_index.json` mais sans `domain` tag. Les domaines prévus :

| Domaine | Exemples de règles |
|---------|-------------------|
| `CRYPTO_PQC` | D-032, D-034, V-PQC-1/2, liboqs |
| `BIOMETRIE` | R372–R378, L-047, TASK-001 |
| `CONSENSUS_BFT` | DV-01…DV-07, L-044, L-045, PBFT |
| `TOKENOMICS` | D-014–D-025, V-01…V-07, HBP |
| `IDENTITE_HUMAINE` | R373, L-047, wallet_per_human |
| `RESEAU_P2P` | D-037–D-045, DV-04 |
| `FORENSIC_TRACE` | R390–R396, L-052, L-053 |
| `FRONTEND_UX` | R359, R379, R389, R398 |
| `PROTOCOLE_AGENT` | R371, R392, hooks Bob IDE |

### Ce qui RESTE À FAIRE ❌

**TASK-RULES-DOMAINS :** ajouter un champ `"domain"` dans chaque entrée CR-* de `rule_corpus_index.json` :

```json
{
  "id": "CR-0047",
  "type": "LESSON",
  "source": "LEÇONS_APPRISES_ARTCB",
  "ref": "L-047",
  "status": "ACTIVE",
  "domain": "BIOMETRIE"   ← NOUVEAU CHAMP
}
```

Script à créer : `scripts/artcb_r399_domain_tagging.py` — règles de classification automatique par mots-clés (pqc/liboqs → CRYPTO_PQC, biometric/fingerprint/bch → BIOMETRIE, etc.) + validation manuelle.

---

## Résumé global FAIT / RESTE

| Domaine | FAIT | RESTE | % |
|---------|------|-------|---|
| IA analyse/comparaison croisée | Encodeur IR + agents duels + batterie tests | Endpoint compare, agent-ID telemetry | 70% |
| Forensic nanoseconde auto | ns.py + AgentRunRecord + conftest trace | Auto-bump version, CI fingerprint | 65% |
| Versioning module unitaire | 175 MODULE_VERSION 1.0.0 | Auto-bump PATCH + changelog | 50% |
| Frontend nettoyé | P2P/Pool/Memorize/AgentPanel supprimés | Locales translations nettoyées | 90% |
| Auto-feedback rétrospective | stop.py R392 + AUDIT_STATUS | Rapport .md auto + métriques feature | 60% |
| Rules télémétriques par domaine | 230 CR-* corpus + 20 RT-* registry | Domain tagging 9 catégories | 45% |

**Prochaine tâche prioritaire suggérée :** TASK-VERSIONING (script bump auto) + TASK-RULES-DOMAINS (domain tagging) en parallèle, puis reprendre TASK-001 FAR/FRR et TASK-006-LIVE-VALIDATION.

---

## device_wallet_limit — diagnostic de l'erreur utilisateur

Le message `{"code":"device_wallet_limit","wallet":"w-55fe5464a470b6ed","fingerprint":"97a0b640…"}` est **attendu et correct**.

**Cause :** le binding `device_fingerprint → wallet` est persisté dans `data/wallet_device_bindings.json`. Une mise à jour du code ne supprime pas ce binding — c'est voulu (protection anti-fraude L-049).

**Pour reset propre (test uniquement) :**
```bash
# Option 1 — endpoint admin (R379)
DELETE /api/v1/admin/device-binding/fingerprint/97a0b640...
Authorization: Bearer <ARTCB_ADMIN_KEY>

# Option 2 — reset manuel (dev)
# Éditer data/wallet_device_bindings.json et supprimer l'entrée "97a0b640…"
```

**Ne jamais activer `ARTCB_ALLOW_MULTI_WALLET=true` en production** — réservé dev/test uniquement.

**Invariant maintenu :** `unique_human_proven=false` dans tous les cas — WebAuthn ≠ identité humaine unique mondiale (L-047).
