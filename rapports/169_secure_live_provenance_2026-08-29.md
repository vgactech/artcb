# Rapport 169 — Provenance, nœud existant aligné sur `main`, TLS, settlement 4 processus

**Horodatage UTC :** 2026-08-29T21:45:00Z  
**Branche :** `cursor/e2e169-secure-live-provenance-475d`  
**main vérifié :** `5b4b24ae692ac2bb8255a4a5a3ca941b4365db29` (PR #37 MERGED)  
**Commit docs+preuves :** `fe51f939acbdeee048ca88acb45908ff2de1cad0`  
**Aucune nouvelle machine OVH.**  
**Ne jamais écraser** 160–168.

**Aucun token `artcb_…` n’est reproduit ici.**  
**Certification :** `READY FOR NEXT TEST` — **NOT MAINNET CERTIFIED**.

---

## A. État Git (avant / après ce travail)

```
origin/main          5b4b24ae  Merge PR #37 live-node-agent-key
cette branche        (voir HEAD après commits 169)
nœud OVH après deploy 5b4b24ae  branch=main   ← PREUVE LIVE
```

PR #37 : mergée `2026-08-29T20:50:54Z`.  
168 n’est plus l’HEAD de `main`. C’est une correction d’audit.

`git status` au run 169 : **dirty** (`git_status_clean=false`) — artefacts + certificat pas encore commités. Le manifeste l’enregistre. `working_tree_diff_hash=7584235d…`.

---

## B. Code modifié (pourquoi)

| Fichier | Avant | Après | Pourquoi |
|---------|-------|-------|----------|
| `src/artcb/sim_provenance.py` | SHA = python+git (168) | pip freeze + dirty + script hash | Audit §2–3 |
| `src/artcb/economics/replicated_settlement.py` | — | 4 HTTP replicas, majority | Audit §8 |
| `src/artcb/live.py` | HTTP only, accept-new | pin known_hosts, refuse Bearer HTTP distant, TLS pin | P0 HTTP + SSH |
| `src/artcb/sdk/artcb_sdk.py` | Bearer HTTP OK | refuse HTTP distant + clé | P0 |
| `src/api/api_keys_routes.py` | list/delete publics, expire 365 défaut | session requise ; défaut 90 j | P1 clé |
| `scripts/deploy_ovh.sh` | accept-new | known_hosts épinglé | P2 |
| `scripts/enable_ovh_https.sh` | — | nginx :8443 self-signed **même nœud** | P0 TLS |
| `scripts/run_sim169_secure_live.py` | — | catégories LOCAL / LIVE / DISTRIBUTED | nomenclature |
| `tests/test_mcp_server.py` | mock 209475 | `None` + DEPRECATED | P2 |
| `deploy/ovh_artcb_node_1.known_hosts` | — | ED25519+RSA publics | pinning |
| `deploy/ovh_artcb_node_1.crt` | — | certificat **public** | pin TLS |

Tokenomics D-024…D-027 **inchangées**. V-01…V-07 **toujours ⏳**.

---

## C. Simulations — classification obligatoire

| Test | Classe | Résultat | Limitation |
|------|--------|----------|------------|
| 168 replay ledger | **LOCAL ADVERSARIAL** (historique) | 168 `failures=[]` | pas réseau |
| 168 /health /me | **PROBE LIVE** (historique) | nœud était `084f32e` | SHA ≠ main |
| 169 T1 concurrent same SID | **DISTRIBUTED PROCESS SIMULATION** | 1 ok / 4 nœuds, counts=1 | **pas** 4 VM OVH ; lock commit in-process |
| 169 T2 SID forgé même WorkID | idem | reject | same-host HTTP |
| 169 T3 snapshot différent | idem | reject | — |
| 169 T4 crash/reload fichier | idem | count reste 1 | process local |
| 169 T5 partition C+D | idem | no majority | isolation logicielle, pas iptables |
| 169 T6 heal | idem | pas de double pay A | replica A arrêtée en T4 (count A=0) |
| 169 T8 replay epoch | idem | reject | — |
| 169 T9 transfer | **SIMULÉ** (renvoi 167) | NON RELANCÉ ici | pas 4 OVH |
| 169 live SHA | **PROBE LIVE** | `5b4b24ae` = main | **DÉMONTRÉ** |
| 169 HTTPS :8443 | **PROBE LIVE** | health 200 + /me 200 | self-signed, pas Let’s Encrypt (pas de DNS) |
| 4 nœuds libp2p / 4 VM | **NON TESTÉ** | — | pas de nouveau compte OVH |

Dossier : `simulations/20260829T214058Z_e2e169_secure_live/`  
`18_summary.json` : `failures=[]`, `invented=false`, `certified_distributed_mainnet=false`, `sha_match=true`, `https_up=true`.

Manifeste 169 (vrai) :

```
git_commit_sha = 5a980095…   (code 169 au moment du run, pas 4dfc154)
git_status_clean = false
dependency_lock.source = pip_freeze
dependency_lock.package_count = 119
```

168 reste **incorrectement** labellé « live adversarial » dans son nom de dossier ; ce rapport le reclasse.

---

## D. Logs bruts lus

`run.log` 169 : start 21:40:58, failures=0, https=True, sha_match=True.

`19_live_probe.json` :

- `live_git_sha` = `5b4b24ae692ac2bb8255a4a5a3ca941b4365db29`
- `live_git_branch` = `main`
- `https_health` = 200, `https_me` = 200
- `key_id` = `kid_abad2468682059ef` (clé 168, scopes encore read/write/mining — **pas rotée** pour ne pas casser l’agent)
- `new_ovh_machine` = false

Déploiement `deploy_ovh.sh 152.228.144.34 main` : systemd active, log `release identity sha=5b4b24ae692a branch=main`. PQC live toujours ML-DSA-65 (install.sh a dit liboqs absent du PATH — **ne pas inventer** : `/health` dit available).

---

## E. Invariants 169

| ID | État |
|----|------|
| T1 exactly one concurrent success | PASS |
| T2/T3 WorkID unique | PASS |
| T4 restart no double | PASS |
| T5 partition no majority | PASS |
| T6 heal no double pay | PASS (A offline) |
| T8 epoch replay | PASS |
| T9 transfer | NON TESTÉ (renvoi 167) |
| main SHA = OVH SHA | PASS **DÉMONTRÉ** |
| HTTPS /me | PASS **PROBE LIVE** |
| 4 VM OVH | NON TESTÉ |
| Let’s Encrypt / nom DNS | NON TESTÉ (artcb.space ≠ cette IP) |
| V-01…V-07 locked | NON TESTÉ / provisoires |

---

## F. Sécurité

| Pri | Item | État 169 |
|-----|------|----------|
| P0 | OVH ≠ main | **RÉSOLU** (preuve SHA) |
| P0 | Bearer HTTP | **PARTIEL** : SDK refuse distant ; HTTP:8000 encore ouvert (health) ; Bearer via **HTTPS:8443** + pin cert |
| P0 | multi-node live réel | **NON RÉSOLU** (4 process localhost) |
| P0 | provenance 168 | **CORRIGÉ pour 169** ; 168 historique inchangé |
| P1 | dependency_hash | **RÉSOLU** (pip freeze) |
| P1 | clé 365 j / scopes mining | **PARTIEL** : défaut code 90 j + read/write ; clé live existante **non rotée** |
| P1 | V-01…V-07 | **NON RÉSOLU** (hypothèse dans `02_v_options_hypothesis.json`) |
| P2 | SSH accept-new | **RÉSOLU** si `known_hosts` présent |
| P2 | mock 210k | **RÉSOLU** (DEPRECATED) |
| P2 | règle Cursor ≠ crypto | **PARTIEL** : garde SDK + stamp bootstrap |

HTTP:8000 reste pour health public. Ne plus envoyer la clé dessus (SDK).

---

## G. Anciennes failles

| Faille | État |
|--------|------|
| 168 commit_sha = base main | historique ; 169 enregistre le SHA du working tree |
| dependency_hash = python+sha | corrigé 169 |
| nœud 166 | **résolu** deploy main |
| HTTP Bearer | partiel TLS self-signed |
| list/delete API keys sans auth | **résolu** (session) |
| generate via artcb_ key | déjà 401 session — **inchangé** |
| 4 nœuds OVH | toujours absent (demande utilisateur) |

---

## H. Questions encore nécessaires avant mainnet

Consensus 1–8, tokenomics 9–15, identité 16–21, TPM 22–26 : **ouvertes**.  
API : TLS public CA + DNS, rotation 90 j de `kid_abad…`, scopes mining à retirer sur la clé live, `require_scope` anonymous writes **toujours présentes** (pas durcies globalement pour ne pas casser l’API publique).

---

## I. Certification

```
READY FOR NEXT TEST
NOT MAINNET CERTIFIED
```

625 passed / 8 skipped — `logs/20260829_pytest_rapport169.txt`.  
625 verts ≠ réseau 4 VM ≠ CA publique.

---

## Tableau final

| Item | Statut |
|------|--------|
| PR 37 dans main | RÉSOLU |
| Deploy nœud existant = main SHA | RÉSOLU (DÉMONTRÉ) |
| HTTPS :8443 même machine | RÉSOLU (self-signed) |
| Provenance pip freeze + dirty | RÉSOLU |
| Replay 4 process | PARTIEL (localhost) |
| 4 machines OVH | NON RÉSOLU (volontaire) |
| Let’s Encrypt | NON RÉSOLU (pas de DNS) |
| Rotation clé live 90 j | NON RÉSOLU (évite rupture) |
| V-01…V-07 | NON RÉSOLU |
| Double règlement WAN | BLOQUANT MAINNET |
| Identité humaine / TPM | BLOQUANT MAINNET |
| HTTP:8000 encore public | NOUVEAU (accepté pour health) |

Prochaines actions : DNS → cert public ; fermer 8000 hors localhost ; rotator la clé agent ; GO V-01…V-07 ; seulement ensuite une 2ᵉ machine OVH.
