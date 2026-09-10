# Rapport 305 — Audit complet : Cursor Machine, Bob IDE, mémoire & thinking sur ce Mac

**Date :** 2026-09-10  
**SHA origin/main :** `edf1083`  
**Auteur :** Bob (agent local, session 305)  
**Méthode :** lecture exhaustive des fichiers `.cursor/`, `data/trace/`, `~/.cursor/projects/`, rapports 285–304, code hooks, canvases, règles mdc  
**Périmètre :** audit uniquement, zéro modification  

---

## 1. Architecture de la machine — deux agents, un seul Mac

Ce Mac fait tourner **deux agents distincts sur la même machine** :

| Agent | Identité | Port | Processus | Rôle |
|---|---|---|---|---|
| **Bob IDE** | `deyi` / workspace `/Users/deyi/.bob/playground` | — | Cursor IDE | Développement, code, conversation |
| **ARTCB node** | `mac-node-local` | **8001** | uvicorn via launchd `me.artcb.node` | Nœud blockchain ARTCB (replica PBFT officiel depuis R297b) |

Ces deux agents partagent le **même dépôt git**, la **même IP LAN** (`10.234.49.2`), les **mêmes fichiers**. Ils n'ont pas le même rôle ni les mêmes disciplines de relecture.

---

## 2. Ce que Cursor a fait sur cette machine — inventaire complet

### 2.1 Infrastructure déployée (sessions 285–303)

| Session | Ce qui a été fait | Fichiers |
|---|---|---|
| **285** | Déploiement mac-node-local : launchd plist, secrets Doppler `artcb-1/prd`, clé SSH `cursor_mac_node`, enregistrement `node_registry.py` | `deploy/mac_node_local_launchd.plist`, `src/artcb/node_registry.py` |
| **286** | Clarification isolation Doppler : `KEY_API_ARTCB_DOPPLER_MAC` = secret Cursor **ET** dans `artcb-blockchain/dev` | `docs/DOPPLER_NODE_ISOLATION.md` |
| **287** | Documentation tunnel RFC1918 : `10.234.49.2` injoignable depuis VMs cloud, tunnel obligatoire sur le Mac | `rapports/287_mac_rfc1918_tunnel_20260909.md` |
| **288** | PR #83 tunnel mac-node : spécification WireGuard/ngrok | `rapports/288_pr83_tunnel_mac_node_20260909.md` |
| **297** | Promotion Mac = replica PBFT officiel (N=5 f=1 Q=3). `official_pbft_replica_ids()` adaptif. `official_pbft_n_f_q()` | `src/artcb/node_registry.py`, `tests/test_e2e297_mac_replica_membership.py` |
| **298** | Commit push + mesure live. Ingest honnête (`ingest_skipped=true` documenté) | `rapports/298_push_main_live_20260910.md` |
| **299** | Règle "jamais supprimer code/règles". Révocation = barré + horodatage. Archive `turn_prompts.jsonl` | `rapports/299_never_delete_mac_replica_20260910.md` |
| **300** | 3 hooks Cursor créés. Journal thinking local. Canvas `flux-thinking-regles`. Règle relecture de tous les fichiers | `.cursor/hooks/`, `scripts/artcb_reason_log.py`, `data/trace/` |
| **301** | Documentation glossaire mdc/hooks. Sudo Mac = Doppler `artcb-1/prd` uniquement | `rapports/301_glossaire_mdc_hooks_acces_20260910.md` |
| **301b** | Fix : sudo Mac dans Doppler `MAC_SUDO_PASSWORD` seulement | — |
| **302** | Fix seeds ≠ membership. `n_f_q(4)` remplacé par `official_pbft_n_f_q()` dans runners. `pbft_reachable_http_map()` | `src/artcb/node_registry.py`, `scripts/run_live270/271`, `tests/test_e2e302_live_n_membership.py` |
| **302b** | Follow-main SSH ×4 nœuds (depuis une autre session). SHA `07ed590` documenté | `rapports/302b_follow_main_sha_20260910.md` |
| **303** | Fix Doppler restricted (`MAC_SUDO_PASSWORD` casse `doppler run`). Wrapper script. Mac reload n=5 | `scripts/artcb_mac_doppler_run.sh`, `rapports/303_github_audit_sha_layers_mac_view_20260910.md` |

### 2.2 Correction critique du nœud Mac (session 303)

Le problème le plus impactant opérationnellement :

**Cause :** `MAC_SUDO_PASSWORD` est un secret `restricted` dans Doppler `artcb-1/prd`.  
Un `doppler run` standard tente de lire **tous** les secrets → crash immédiat.  
launchd `KeepAlive=true` → boucle d'échecs infinie.

**Correctif :** [`scripts/artcb_mac_doppler_run.sh`](scripts/artcb_mac_doppler_run.sh)
```bash
# 1. liste les noms seulement (pas les valeurs)
# 2. filtre MAC_SUDO_PASSWORD de la liste
# 3. lance doppler run --only-secrets <liste filtrée>
# jamais --plain
```

**Impact :** Le service `me.artcb.node` est **UP** et stable depuis ce correctif.

---

## 3. Mémoire — ce qui fonctionne réellement

### 3.1 Les 4 couches de mémoire sur ce Mac

```
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 1 — CoT privé du modèle                             │
│  Génération : backend Cursor (cloud)                        │
│  Stockage   : JAMAIS sur le disque Mac                      │
│  Export     : 0 % (pas d'API documentée)                    │
│  Statut     : INACCESSIBLE                                  │
└─────────────────────────────────────────────────────────────┘
           ↓ (après génération, Cursor peut surfacer)
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 2 — Thinking surfacé (blocs UI chat)               │
│  Génération : backend Cursor, puis affiché dans le chat     │
│  Capture    : hook afterAgentThought → data/trace/          │
│               agent_thoughts.jsonl (append-only, gitignored)│
│  Statut     : ✅ FONCTIONNEL — 402 entrées, 274 662 chars   │
│  Limite     : copie APRÈS le backend, pas le CoT privé      │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 3 — Transcript machine (tool calls + chat)          │
│  Chemin     : ~/.cursor/projects/Users-deyi-bob-playground/ │
│               agent-transcripts/*.jsonl                     │
│  Contenu    : 488 lignes, ~1 Mo, roles user/assistant       │
│  Statut     : ✅ PRÉSENT sur le disque                      │
│  Limite     : chat + tools uniquement, pas le CoT privé     │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 4 — Mémoire on-chain ARTCB (mémos)                  │
│  Chemin     : POST /api/v1/ai/memo (OVH1 via bootstrap)     │
│  Contenu    : user_query uniquement, includes_thinking=false│
│  Statut     : ⚠️ 409 equivocation ce tour (ingest_skipped)  │
│  Limite     : thinking/system/tokens JAMAIS on-chain        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Journal de trace local — état mesuré

| Fichier | Lignes | Contenu | Status |
|---|---|---|---|
| `data/trace/agent_thoughts.jsonl` | **402** | Thinking surfacé (hook) | ✅ actif |
| `data/trace/agent_reasoning.jsonl` | **1** | Journal processus agent | ✅ créé |
| `data/trace/precompact.jsonl` | **3** | Compactions mémoire | ✅ actif |
| `data/trace/turn_prompts.jsonl` | **16** | Prompts utilisateur archivés | ✅ actif |
| `data/trace/ns.jsonl` | **167** | Traces nanoseconde HTTP/PBFT | ✅ actif |

**Total thinking capturé :** 274 662 caractères sur 402 entrées de thinking surfacé.

### 3.3 Compactions mémoire détectées

3 compactions enregistrées dans `precompact.jsonl` :

| # | Déclencheur | % contexte | Tokens | Messages |
|---|---|---|---|---|
| 1 | auto | **92.0 %** | 235 517 / 256 000 | 385 |
| 2 | auto | **90.9 %** | 232 653 / 256 000 | 224 |
| 3 | auto | **93.3 %** | 238 959 / 256 000 | 210 |

**Observation :** les compactions arrivent systématiquement **au-dessus de 90 %** du context window de 256 000 tokens. C'est la perte de mémoire **dans** le tour — le hook `preCompact` date exactement ce moment.

---

## 4. Hooks Cursor — architecture et état

### 4.1 Les 3 hooks installés

**Fichier de config :** [`.cursor/hooks.json`](.cursor/hooks.json)

```json
{
  "afterAgentThought"  → ".cursor/hooks/after_agent_thought.py",
  "preCompact"         → ".cursor/hooks/pre_compact.py",
  "sessionStart"       → ".cursor/hooks/session_start.py"
}
```

| Hook | Déclencheur | Ce qu'il fait | Destination |
|---|---|---|---|
| `afterAgentThought` | Après un bloc thinking affiché | Copie le texte surfacé avec sha256 + ts_ns | `data/trace/agent_thoughts.jsonl` |
| `preCompact` | Avant résumé Cursor (contexte > ~90%) | Enregistre % contexte, tokens, nb messages | `data/trace/precompact.jsonl` |
| `sessionStart` | Nouvelle conversation Composer | Réinjecte la liste de TOUS les fichiers de règles | additional_context |

### 4.2 Ce que les hooks ne peuvent PAS faire

- **Capturer le CoT privé** : il naît sur le backend Cursor, pas sur le Mac. `afterAgentThought` reçoit uniquement le thinking que Cursor choisit de "surfacer" (afficher).
- **Bloquer la compaction** : `preCompact` est observationnel seulement.
- **Empêcher la perte mémoire** : il date seulement le moment où elle se produit.

### 4.3 Canvases créés pour documenter le flux

Deux canvases dans `~/.cursor/projects/Users-deyi-bob-playground/canvases/` :

| Canvas | Sujet |
|---|---|
| `flux-thinking-regles.canvas.tsx` | Carte visuelle des 6 étapes du flux thinking + 8 fichiers de règles |
| `thinking-local-journal.canvas.tsx` | Tableau des 8 couches mémoire, comparaison Bob vs agent Cursor, stat 3 couches thinking |

---

## 5. Règles Cursor — architecture et fiabilité

### 5.1 Les 5 fichiers `.mdc`

| Fichier | `alwaysApply` | Contenu principal |
|---|---|---|
| `artcb-live-node.mdc` | ✅ **true** | Nœud live OVH obligatoire à chaque prompt, protocole PBFT, règles 1–49 |
| `artcb-read-all.mdc` | ✅ **true** | Index de relecture de TOUS les fichiers à chaque tour |
| `mac-node-local.mdc` | ❌ false | Historique mac-node-local (R285→R303), interdits |
| `aws-node-3.mdc` | ❌ false | Config aws-node-3 |
| `ovh-node-4.mdc` | ❌ false | Config ovh-node-4 |

**Problème identifié (L-042) :** `mac-node-local.mdc`, `aws-node-3.mdc`, `ovh-node-4.mdc` ont `alwaysApply: false`. Avant R300, l'agent ne les voyait pas automatiquement. Correctif : `artcb-read-all.mdc` (`alwaysApply: true`) force la relecture explicite de tous les fichiers à chaque tour, compensant les `false`.

### 5.2 `sessionStart` hook — injection à chaque session

À chaque nouvelle conversation Composer, le hook injecte la liste complète des 15 fichiers de règles à relire :
```
.cursor/rules/*.mdc × 5
AUTO_PROMPT_ARTCB
PROTOCOLE_ARTCB
LEÇONS_APPRISES_ARTCB
STANDARD_NAMES_ARTCB
ROADMAP_GENERAL_ARTCB
INDEX_ARTCB
CONFIGURATION_ARTCB
CHECKLIST_PRE_DEV_ARTCB
QUESTIONS_OUVERTES_ARTCB
CAHIER_DES_CHARGES_ARTCB
```

**Limite :** le hook injecte la **liste** (noms de fichiers), pas le contenu. L'agent doit encore ouvrir chaque fichier.

---

## 6. Différence Bob IDE vs agent Cursor ARTCB

| Critère | Bob IDE | Agent Cursor ARTCB |
|---|---|---|
| Identité | `deyi`, workspace Bob | Agent ARTCB, workspace playground |
| Relecture règles | Question locale → peu de fichiers | Obligatoire TOUS les fichiers, 1re→dernière ligne, chaque tour |
| `alwaysApply` mac/aws/ovh | N/A (pas de ces règles) | `false` mais compensé par `artcb-read-all.mdc` |
| Nœud ARTCB | ✅ même machine, même code | ✅ même launchd `me.artcb.node` |
| Thinking | Non stocké (Bob standard) | `afterAgentThought` → `data/trace/agent_thoughts.jsonl` |
| Mémoire between sessions | Résumé de contexte standard | + `data/trace/` append-only + mémos on-chain |
| Mac = observateur | §4 original Bob session 285 | **Barré 2026-09-10T00:05:00Z** — replica officiel R297b |

**Point clé :** Bob a documenté le Mac correctement dans la session 285 (launchd, Doppler, RFC1918). Le `§4 observateur` était la seule erreur. L'agent Cursor l'a corrigé en R297b. Le correctif est barré-horodaté dans `mac-node-local.mdc`.

---

## 7. Ce qui a fonctionné dans Bob IDE

Les éléments suivants ont été **produits ou validés dans Bob IDE** (cette session et les précédentes) :

| Élément | Session | Statut |
|---|---|---|
| GO-B/D/I/E/K/M — 98 tests verts | 240–243 | ✅ |
| Rapports 240–244 | 240–244 | ✅ |
| `git push` SHA `2696f2e` → `main` | 243 | ✅ |
| Rapport 304 audit CERTIFIED_100=false | 304 | ✅ |
| `git push` SHA `edf1083` → `main` | 304 | ✅ |
| Explication architecture Mac comme nœud | 305 (ce rapport) | ✅ |

Bob IDE **ne participe pas** au consensus PBFT. Il utilise le même dépôt que le nœud ARTCB, mais les opérations Bob (édition de code, tests, git) sont **orthogonales** au consensus.

---

## 8. Lacunes et points non résolus

| # | Lacune | Impact | Résolution possible |
|---|---|---|---|
| L1 | CoT privé 0 % exportable | La pensée profonde du modèle est perdue | Non résolvable (contrainte Cursor) |
| L2 | Thinking surfacé ≠ CoT privé | 402 entrées capturées mais partiel | Honnête, documenté |
| L3 | `sessionStart` injecte les noms, pas le contenu | L'agent peut oublier d'ouvrir les fichiers | Ouvrir systématiquement à chaque tour |
| L4 | `agent_reasoning.jsonl` = 1 seule entrée | Journal processus très peu alimenté | Appeler `artcb_reason_log.py` plus souvent |
| L5 | Tunnel RFC1918 absent | Mac ne peut pas rejoindre le P2P | WireGuard/ngrok à démarrer sur le Mac |
| L6 | Ingest 409 equivocation | Prompts pas on-chain | Résoudre WorkID/SettlementID conflit |
| L7 | `turn_prompts.jsonl` = 16 entrées | Historique incomplet | Règle 42b : écrire systématiquement à chaque tour |
| L8 | Compaction tous les ~200–385 messages | Perte mémoire fréquente | Non évitable, mais datée par `preCompact` |

---

## 9. Ce qui aurait pu être précisé

Points que tu aurais pu mentionner mais qui ne l'ont pas été explicitement :

1. **Le transcript machine dans `~/.cursor/`** contient 488 lignes (33 messages user + 454 assistant) depuis la session R297–R303. C'est le seul endroit où le chat complet est stocké localement — mais pas le CoT privé.

2. **Le canvas Cursor** (`~/.cursor/projects/.../canvases/`) : deux canvases ont été créés (session 300) pour visualiser le flux thinking et la comparaison Bob/agent. Ils ne sont pas dans le repo git — ils sont dans le profil Cursor local.

3. **`data/trace/ns.jsonl`** : 167 traces nanoseconde de tous les appels HTTP du nœud local (health, pbft, consensus_status). C'est la trace de bas niveau du nœud, pas du thinking.

4. **La règle 40** (`artcb-live-node.mdc`) interdit explicitement de dire que les thinking sont on-chain. Cette distinction est critique et souvent confondue.

5. **`~/.doppler/`** : le token Doppler CLI est stocké ici (session globale). C'est ce token qui permet à `doppler run` de fonctionner sans variable d'environnement explicite.

6. **MCP server ARTCB** (`.cursor/mcp.json`) : un serveur MCP est configuré pour pointer vers `http://localhost:8000`. Il n'est pas actif en production (le nœud est sur `:8001`, pas `:8000`). Potentielle confusion à corriger.

---

*Zéro modification. CERTIFIED_100=false.*
