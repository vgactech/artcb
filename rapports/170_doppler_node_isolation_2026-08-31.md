# Rapport 170 — Isolation Doppler par nœud + écart live vs `main` PR #38

**Horodatage UTC :** 2026-08-31T15:15:00Z  
**Branche :** `cursor/e2e170-node-secret-isolation-475d`  
**origin/main vérifié :** `376b0e4c887dfd0ea671cd61ceb522dfb0e80a48` (PR **#38 MERGED**)  
**Commit code 170 :** `6b92dba`  
**Aucune VM OVH ou AWS créée.**  
**Aucun token, mot de passe console, application secret n’est reproduit ici.**  
**Certification :** `READY FOR NEXT TEST` — **NOT MAINNET CERTIFIED**.

Les secrets collés dans le chat (OVH application secret, consumer key, mot de passe console AWS) doivent être **rotés** : ils ont transité en clair dans la conversation.

---

## A. État Git

```
origin/main     376b0e4c  Merge PR #38 e2e169-secure-live-provenance
cette branche   (HEAD après commits 170)
live OVH1       5b4b24ae  branch=main   ← PROBE LIVE, ≠ origin/main
```

PR #38 : mergée (30 fichiers, +1361/−14). Le rapport 169 reste **historiquement correct** (`live = 5b4b24ae = main d’alors`).  
**Aujourd’hui** `live_git_sha == origin/main` est **faux**.

`git_status` au run 170 : **dirty** (`git_status_clean=false`) — code 170 pas encore commité. Manifeste : `working_tree_diff_hash` enregistré. `dependency_lock.source=pip_freeze` (118 paquets, sans liboqs dans ce runtime).

---

## B. Code modifié (pourquoi)

| Fichier | Avant | Après | Pourquoi |
|---------|-------|-------|----------|
| `src/artcb/node_registry.py` | — | 3 nœuds, 3 projets Doppler, allowlist | D-029 isolation |
| `scripts/provision_doppler_node_projects.py` | — | `POST /v3/projects` si token personnel | créer les coffres |
| `scripts/ovh_api_inventory.py` | — | `/me` + cloud sans imprimer les clés | inventaire réel |
| `scripts/check_ovh.py` | signature = AK+AS+CK+… | AS+CK+METHOD+URL+BODY+TS | signature OVH officielle |
| `src/artcb/live.py` | défaut HTTP ; projet unique | défaut HTTPS Bearer ; `ARTCB_NODE_ID` | P0 HTTP + isolation |
| `scripts/run_sim170_node_isolation.py` | — | probe SHA + Doppler + OVH2 | pas d’invention |
| `tests/test_e2e170_node_isolation.py` | — | 3 projets distincts, Stripe pas sur nœud | non-mélange |
| `docs/DOPPLER_NODE_ISOLATION.md` | — | mapping public | ops |
| `.cursor/rules/artcb-live-node.mdc` | « pas de 2ᵉ VM » | isolation + comptes 2/3 sans VM | D-029 |

Tokenomics D-024…D-027 **inchangées**. V-01…V-07 **toujours ⏳**.

---

## C. Simulations — classes obligatoires

Dossier réel : `simulations/20260831T151201Z_e2e170_node_isolation/`  
`invented=false` `certified_distributed_mainnet=false` `sha_match_current_main=false` `new_ovh_machine=false`

| Test | Classe | Résultat | Limitation |
|------|--------|----------|------------|
| Live SHA vs `origin/main` | **PROBE LIVE** | `5b4b24ae` ≠ `376b0e4c` | **DÉMONTRÉ** écart |
| HTTPS `/health` + `/api-keys/me` | **PROBE LIVE** | 200 / `kid_abad2468682059ef` | self-signed |
| Création 3 projets Doppler | **PROBE LIVE** | **403** service token | token personnel requis |
| OVH2 `/me` nic `vc491276-ovh` | **PROBE LIVE** | 200, email `vgac4237@gmail.com` | — |
| OVH2 Public Cloud / VPS / IP | **PROBE LIVE** | **0** | pas de nœud 2 compute |
| OVH1 CK Cursor/Doppler | **PROBE LIVE** | 403 credential invalid/expired | nœud 1 SSH inchangé |
| AWS `aws login` | **NON TESTÉ** | navigateur / access keys absents | headless |
| 4 nœuds WAN | **NON TESTÉ** | — | 0 VM supplémentaire |
| T1–T8 settlement 169 | **historique** | inchangé | localhost |
| V-01…V-07 | **NON TESTÉ** | provisoires | — |

168 reste **LOCAL ADVERSARIAL + LIVE PROBE**, pas un settlement live distribué.

---

## D. Logs bruts

`run.log` 170 : start `15:12:01Z`, `failures=1` (`doppler_projects_not_created`), `sha_match=False`, `ovh2_me=200`.

`19_live_probe.json` :

- `expected_origin_main_sha` = `376b0e4c…`
- `live_git_sha` = `5b4b24ae…`
- `sha_match_current_main` = **false**
- `https_me` = 200, `key_id` = `kid_abad2468682059ef` (scopes read/write/mining — **toujours pas rotée**)

`11_doppler_provision.json` : token type `service_token` name `artcb-node-1` ; trois créations HTTP 403 ; `projects_after` = `[artcb-blockchain]` seulement.

`13_ovh2_inventory.json` : `cloud_projects=[]`, `instances=[]`.

Staging local (hors git, mode 0600) : `~/.artcb/nodes/ovh-node-2.env` et `aws-node-3.env`. Le mot de passe console AWS n’est **pas** poussé vers Doppler.

---

## E. Invariants 170

| ID | État |
|----|------|
| origin/main connu | PASS |
| live health HTTP+HTTPS | PASS **PROBE LIVE** |
| live SHA = `origin/main` actuel | **FAIL** (écart PR #38) |
| 3 projets Doppler créés | **FAIL** (403, attendu avec ce token) |
| OVH2 `/me` | PASS |
| OVH2 sans VM | PASS (constat) |
| Stripe/Bob hors projet nœud | PASS (code + tests) |
| 4 VM | **NON TESTÉ** |
| V-01…V-07 locked | **NON TESTÉ** / provisoires |
| Tokenomics 21M / pas de 210k | non modifié |

---

## F. Sécurité

| Pri | Item | État 170 |
|-----|------|----------|
| P0 | OVH ≠ `main` **actuel** | **NOUVEAU GAP** (était résolu en 169) |
| P0 | Bearer HTTP | **PARTIEL** : défaut SDK/bootstrap = HTTPS:8443 ; `:8000` encore public |
| P0 | 3 coffres Doppler | **NON RÉSOLU** (403) — mapping + staging prêts |
| P0 | multi-node live | **NON RÉSOLU** (0 VM extra) |
| P1 | CK OVH historique expirée | **NOUVEAU** — nœud 1 toujours joignable en SSH/health |
| P1 | secrets collés dans le chat | **À ROTER** (OVH2 app secret + AWS console) |
| P1 | clé agent 365 j / mining | inchangé |
| P1 | V-01…V-07 | **NON RÉSOLU** |
| P2 | signature OVH check_ovh | **RÉSOLU** (sans AK dans le hash) |

---

## G. Anciennes failles

| Faille | État |
|--------|------|
| 169 live=main | **obsolète** après PR #38 |
| provenance pip freeze | conservée 170 |
| HTTP Bearer SDK | défaut HTTPS |
| 4 process ≠ 4 VM | toujours vrai |
| list/delete API keys | inchangé 169 |
| Let’s Encrypt | toujours absent |

---

## H. Questions encore nécessaires avant mainnet

Inchangées : consensus 1–8, tokenomics 9–15, identité 16–21, TPM 22–26, démo 27–30.  
**Ajout 170 :** comment créer les 3 projets Doppler sans service token Cursor ; qui paie / crée la première VM `vc491276-ovh` ; access keys AWS vs `aws login` navigateur.

---

## I. Certification

```
READY FOR NEXT TEST
NOT MAINNET CERTIFIED
```

Pytest ce runtime (C `libartcb_chain.so` compilé ici, **sans** liboqs) : **617 passed / 20 skipped / 2 failed**.  
Les 2 fails = `test_e2e169` 503 `api-keys` en fin de suite (singleton FastAPI en mode bootstrap) — **41 passed** en run isolé 168+169+170+MCP.  
625 verts de 169 ≠ ce VM froid. 617 verts ≠ mainnet.


---

## Tableau final

| Item | Statut |
|------|--------|
| PR 38 dans `main` `376b0e4c` | RÉSOLU (constat GitHub) |
| Live = `main` **actuel** | **NON RÉSOLU** (encore 5b4b24ae) |
| Mapping 3 projets Doppler | RÉSOLU (code) |
| Création Doppler réelle | NON RÉSOLU (403) |
| OVH2 compte réel | RÉSOLU (PROBE `/me`) |
| OVH2 VM | NON RÉSOLU (0 instance — volontaire) |
| AWS3 login CLI | NON RÉSOLU (navigateur) |
| Rotation secrets collés chat | NON RÉSOLU |
| 4 machines | NON RÉSOLU |
| V-01…V-07 | NON RÉSOLU |
| Double règlement WAN | **BLOQUANT MAINNET** |
| Déploiement `376b0e4c` sur `:34` | non fait (pas d’ordre deploy) |

Prochaines actions : coller `DOPPLER_PERSONAL_TOKEN` (ou créer les 3 projets à la main) → relancer `provision_doppler_node_projects.py` ; **rotater** le secret OVH2 et le mot de passe AWS collés ici ; access keys IAM `node_artcb_3_agent` ; seulement ensuite une VM sur `vc491276-ovh` si tu le demandes ; redéployer le nœud 1 sur `376b0e4c` **sur ordre explicite**.
