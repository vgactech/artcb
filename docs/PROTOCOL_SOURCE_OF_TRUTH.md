# Source de vérité protocolaire — hiérarchie et règle de lecture

**Origine :** rapport 214 (anomalie n°1 : le README décrivait un halving et des
allocations fondateurs que D-024 / D-025 ont retirés ; le code suivait déjà les
décisions). Le problème n’était pas le code, c’était **plusieurs documents qui
prétendaient tous décrire le protocole**.

## Hiérarchie (du plus au moins autoritaire)

| Rang | Source | Rôle | Qui l’écrit |
|---|---|---|---|
| 1 | `DECISIONS_UTILISATEUR_ARTCB` (D-0xx) | Ce que l’opérateur a **décidé** (GO explicite) | Opérateur uniquement |
| 2 | Spécifications (`TOKENOMICS_ARTCB`, `CAHIER_DES_CHARGES_ARTCB`, `validation/DV-*/SPEC.md`) | Comment la décision se traduit en règles | Agent, après GO |
| 3 | Code (`src/artcb/**`, constantes `IMMUTABLE_*`, `devnet_validation.py`) | Ce qui **s’exécute** | Agent, PR |
| 4 | Tests (`tests/test_e2eNNN.py`, `LISTE_TESTS_ARTCB.md`) + `validation/DV-*/RESULT.json` | Ce qui est **prouvé** localement / mesuré live | Agent ; RESULT.json seulement après mesure |
| 5 | Live (`/health` des 4 nœuds officiels, `git_sha`, `certified_distributed_mainnet`) | Ce qui **tourne** | Timer follow-main |
| 6 | Rapports (`rapports/NNN_*.md`) | Ce qui a été **observé et discuté** à une date | Agent ; jamais réécrits après coup |
| 7 | `README.md`, FAQ, docs de vulgarisation | Reflet — **jamais** une source | Agent |

## Règles

1. **Un rang inférieur ne peut pas contredire un rang supérieur.** Si le README dit
   « halving » et D-024 dit « pas de halving », c’est le README qui est faux.
2. **« Présent dans le README » ≠ « implémenté ».** Seuls les rangs 3-5 disent ce qui existe.
3. **Un commit ≠ une exécution.** Le SHA live d’un nœud (`/health.git_sha`) est la seule
   preuve qu’un nœud exécute ce commit. Le bootstrap `scripts/artcb_live_bootstrap.py`
   le mesure au début de chaque tâche.
4. **Une décision non prise n’est pas « D-0xx ».** Une proposition d’agent s’écrit
   « proposition » dans un rapport ; elle devient D-0xx **seulement** quand l’opérateur
   la valide dans `DECISIONS_UTILISATEUR_ARTCB`.
5. **Les rapports « chat et simulation » (ex. 212-214) sont du rang 6.** Ils contiennent
   des idées, des audits et des simulations. Rien n’y est implémenté par le fait d’y être écrit.
6. **Certification** : `certified_distributed_mainnet` vient de `certification_gate()`
   sur les `RESULT.json` réels, jamais d’un texte.

## Matrice obligatoire dans chaque rapport de correction

Pour toute règle touchée, une ligne :

`Règle | Décidée (D-0xx) | Simulée (sim/rapport) | Codée (fichier) | Testée (test) | Live (SHA)`

Une case vide se lit « non ». Elle ne se remplit pas par déduction.

## Application immédiate (2026-09-04)

- README §Tokenomics réécrit pour refléter D-024 / D-025 (rang 7 aligné sur rang 1-3).
- `GROUPES_RESEAUX_ARTCB.md` marqué **obsolète** (rang 6 historique, pas une spec).
- Biométrie : le libellé « reconnaissance faciale » remplacé par « vérification de
  présence faciale locale » ; niveaux d’assurance exposés par l’API (`assurance`,
  `unique_human_proven=false`).
- Autorisation (rapport 216) : le moteur `src/artcb/authz/` est du **rang 3**
  (code). Ce n’est pas une D-0xx. Consensus ≠ autorisation.
- Domaines (rapports 217-218) : `REPLICATION_MATRIX` + `DomainRegistry` sont du
  **rang 3**. Un nœud **héberge** un domaine ; le fondateur le **possède**.
  Un `append_block` public `reward=0` ancre le hash (rapport 220 / P-218-2).
  Contrôleur ≠ fondateur historique. Ce n’est pas une D-0xx.
  Rapport 221 : ces blocs **étendent le tip** des pairs (convergence). Les
  adresses de transfert ne sont plus dans le bloc public. Contact officiel
  `official@artcb.space`.
  Rapport 222 : `decide_public_import()` unique (receive = pull). V-01 n'est
  pas une certification Byzantine.
- Auto-dev (rapport 233) : clé opérateur `artcb_` ≠ session humaine `sess_`.
  Un agent Cursor/Bob n'est un user que sous `sess_` + `X-ARTCB-Agent-Id`.
  Les mémos auto-dev sont `visibility=private`. Pas de D-0xx. PoUC/KCG
  (rapports 230–232) restent rang 6 — ne pas coder.
  Rapport 236 : `authorized_nodes` = déclaration. Certificat nœud signé
  fondateur = preuve. HOST_ONLY ≠ REPLICA ≠ CONSENSUS. TRANSFER_OWNERSHIP
  reste humain. Réplication privée automatique et consensus ORG **non
  certifiés**. 857 passed / 9 skipped ≠ maturité protocolaire 97 %.
- Rapports 237–238 (rang 6) : Reasoning Fee figé (237) ; cadastre + lettres
  (238). 239–243 : code GO-A…H puis B/D/I/E/K/M sur `main` `2696f2e`.
  **GO-K/M 238 ≠ GO-K/M 242–243** (lettres réutilisées). Rapport 244 :
  4 officiels déjà sur `2696f2e` ; `ProducerMonitor` **non** branché API ;
  V-01-B producteur **non** exécuté. Pull anonyme toujours clair.
- Rapport 245 : mot `GO` → câblage `ProducerFailoverRuntime` (défauts off,
  `append_implemented=false`). Pas une D-0xx. Pas d'append live.
- Rapport 246 : brief Bob (1c2b873 / GO-M 21/23 / pas de push) contredit par
  live `2696f2e` ×4. GO-M 23/23. ROADMAP Phase 15 à jour. Pas de redeploy.
- Rapport 247 : livre écrit. OVH1 height 8 tip `f646c510…` (idx 5–7
  `cbff6e66` / `a9e411c3` / `f646c510`). Pairs 2/3/4 restent `27350024`
  (import 222). Wipe non. GO-E produce off. SHA `c1d8027` = `origin/main`.
- Rapport 248 : `/ai/memo` + KCG utilisés en live. Avant = 0 mémo / 0 K.
  Bloc 8 `623d6e78…` `ai_memo_05a709e390c3` `K_0b844c03`. Bootstrap lit
  désormais `/ai/memory` + `/kcg/stats`. Search MVP = SequenceMatcher
  (faux positifs). KCG local, pas répliqué. Pas de D-0xx.
- Rapport 249 : ingest repo scoped. 1065 lots → OVH1 height 1074
  tip `3d1231cd…`. Public / private chaîne ; org+groupe = body privé +
  catalogue public. `GET /ai/ingest/file`. Secrets non inlinés. Pas de D-0xx.
