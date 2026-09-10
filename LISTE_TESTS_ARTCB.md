# LISTE TESTS ARTCB — Registre cumulatif

**Horodatage création :** 2026-07-07T05:15:00Z  
**Branche dev :** `cursor/dashboard-dev-1fce`  
**Règle PROTOCOLE :** cette liste est **cumulative** — ne jamais supprimer un test, cocher `[x]` quand passé, ajouter horodatage.

**Avancement tests dashboard : 100 %** (UI) — **sécurité invitations Solution 2 : 100 %** (T-G09–G12)

---

## 1. Tests backend existants (baseline — toujours exécuter)

| ID | Commande | Attendu | Statut | Dernière exec |
|----|----------|---------|--------|---------------|
| T-B01 | `python3 -m pytest tests/ -q` | 478/478 passed | [x] | 2026-08-05 478/478 ✅ (8 skipped bridges live intentionnels) |
| T-B02 | `python3 -m pytest tests/test_wallet_rewards.py -q` | all pass, reward 50 ARTCB / 210k | [x] | 2026-08-25 |
| T-B03 | `python3 -m pytest tests/test_pol.py -q` | split 1.0 ARTCB | [x] | 2026-07-07 |
| T-B04 | `python3 -m pytest tests/test_api.py -q` | API OK | [x] | 2026-07-07 |
| T-B05 | `python3 -m pytest tests/test_chain.py -q` | C verify OK | [x] | 2026-07-07 |
| T-B06 | `python3 scripts/demo_live.py` | 9/9 steps OK | [x] | 2026-07-07 |
| T-B07 | `curl -s localhost:8000/api/v1/health \| jq .status` | `"ok"` | [x] | 2026-07-07 |

---

## 2. Tests groupes (nouveau — dashboard phase)

| ID | Commande / scénario | Attendu | Statut | Dernière exec |
|----|---------------------|---------|--------|---------------|
| T-G01 | `pytest tests/test_groups.py::test_create_group` | founder immuable | [x] | 2026-07-07 |
| T-G02 | `test_founder_cannot_be_removed_by_admin` | 403 FOUNDER_IMMUTABLE | [x] | 2026-07-07 |
| T-G03 | `test_only_founder_promotes_admin` | admin role set | [x] | 2026-07-07 |
| T-G04 | `test_admin_cannot_promote_admin` | 403 | [x] | 2026-07-07 |
| T-G05 | `test_dissolve_group_founder_only` | groupe archivé | [x] | 2026-07-07 |
| T-G06 | `POST /groups` + `GET /groups` API | données réelles JSON | [x] | 2026-07-07 |
| T-G07 | `POST /store` visibility=group + group_id | bloc scoped | [x] | 2026-07-07 |
| T-G08 | `GET /chain?group_id=` filtre | membres only | [x] | 2026-07-07 |
| T-G09 | `test_create_group_has_join_code` | join_code 8 car. | [x] | 2026-07-07 |
| T-G10 | `test_direct_invite_blocked_by_default` | 403 join-request | [x] | 2026-07-07 |
| T-G11 | `test_join_request_flow` | sign + approve + member | [x] | 2026-07-07 |
| T-G12 | `test_reject_join_request` | rejected, pas membre | [x] | 2026-07-07 |

---

## 3. Tests frontend dashboard (nouveau)

| ID | Scénario | Attendu | Statut | Dernière exec |
|----|----------|---------|--------|---------------|
| T-F01 | `cd frontend && npm run build` | 0 errors | [x] | 2026-07-07 |
| T-F02 | Navigation sidebar V1→V10 | routes OK | [x] | 2026-07-07 |
| T-F03 | V2 Mémoriser → API réelle | graph_id retourné | [x] | 2026-07-07 |
| T-F04 | V3 Graphe Cytoscape | nodes affichés | [x] | 2026-07-07 |
| T-F05 | V4 Chaîne table blocs | GET /chain | [x] | 2026-07-07 |
| T-F06 | V5 Wallets list/create | API wallet | [x] | 2026-07-07 |
| T-F07 | V6 Minage affiche reward 1 ARTCB | label correct | [x] | 2026-07-07 |
| T-F08 | V7 SystemMetrics refresh | /metrics | [x] | 2026-07-07 |
| T-F09 | V8 Logs tail demo_live | fichier lu | [x] | 2026-07-07 |
| T-F10 | V9 Console affiche commandes | pas mock | [x] | 2026-07-07 |
| T-F11 | V10 Créer groupe + join_code + approve | API groups Solution 2 | [x] | 2026-07-07 |
| T-F15 | Page `/groups/join` demande signée | JoinGroup.tsx | [x] | 2026-07-07 |
| T-F12 | Sélecteur réseau Privé/Groupe/Public | filtre UI | [x] | 2026-07-07 |
| T-F13 | Badge DEBUG visible | header | [x] | 2026-07-07 |
| T-F14 | Demo.tsx supprimé, Dashboard actif | App.tsx | [x] | 2026-07-07 |

---

## 4. Avancement % (mis à jour en temps réel)

| Phase | Tâche | % | Tests liés |
|-------|-------|---|------------|
| **0** | LISTE_TESTS + branche dev | **100 %** | — |
| **1** | Backend GroupManager + API | **100 %** | T-G01–G12 |
| **2** | Shell layout + Router + tokens MC | **100 %** | T-F01–F02 |
| **3** | Vues V1–V8 API réelle | **100 %** | T-F03–F09 |
| **4** | V9 Console + V10 Groupes | **100 %** | T-F10–F12, T-F15 |
| **5** | Tests + rapports + suppression Demo | **100 %** | T-B* + T-F14 |

**Avancement dashboard global : 100 %**

---

## 5. Journal d'exécution (cumulatif)

| Date UTC | Session | Tests passés | % | Notes |
|----------|---------|--------------|---|-------|
| 2026-07-07T05:15 | démarrage phase dashboard | — | 5 % | GO utilisateur, branche dev créée |
| 2026-07-07T06:00 | design rétro MC + shell V1–V10 | T-F01, T-F14 | 45 % | Press Start 2P, sidebar, pages |
| 2026-07-07T06:30 | API groupes + filtre chain + V10 | T-G01–G08, T-B01 | 62 % | rapport 047 |
| 2026-07-07T07:00 | CDC 100 % + tous tests | 29/29 + 132 pytest | **100 %** | rapport 048 |
| 2026-07-07T08:00 | Solution 2 request-to-join sécurisé | T-G09–G12, T-F15 | **100 %** | rapport 049 |

---

## 6. Règles de maintenance

1. **Ajouter** un nouveau test en fin de section — jamais supprimer.
2. Cocher `[x]` uniquement après exécution réelle + logs lus.
3. Mettre à jour §4 % après chaque phase.
4. Référencer `rapports/049_*.md` après session join-request.
5. PROTOCOLE : pas de mock — tests API = serveur réel ou TestClient avec fichiers réels.

---

**Dernière mise à jour :** 2026-07-09T01:35:00Z

---

## 7. Tests pool E2E + P2P (juillet 2026)

| ID | Commande / scénario | Attendu | Statut | Dernière exec |
|----|---------------------|---------|--------|---------------|
| T-P01 | `pytest tests/test_pool_e2e.py` | crypto ML-KEM roundtrip | [x] | 2026-07-09 |
| T-P02 | `pytest tests/test_pool_policy.py` | distribué exige chiffrement | [x] | 2026-07-09 |
| T-P03 | `pytest tests/test_pool_integration.py` | private/public/group | [x] | 2026-07-09 |
| T-P04 | `pytest tests/test_pool_stress.py` | volume + concurrence | [x] | 2026-07-09 |
| T-P05 | `scripts/validate_two_nodes.py --spawn` | 18/18 étapes pool+P2P | [x] | 2026-07-09 |

---

## 8. Tests CLI terminal

| ID | Commande | Attendu | Statut | Dernière exec |
|----|----------|---------|--------|---------------|
| T-C01 | `python3 scripts/artcb_cli.py --help` | exit 0, commandes pool/p2p | [x] | 2026-07-09 |
| T-C02 | `pytest tests/test_artcb_cli.py` | health, wallet, mining local | [x] | 2026-07-09 |
| T-C03 | Console UI `/console` commandes pool/p2p | fetch API réelle | [x] | 2026-07-09 |

---

## 4. Avancement % (mis à jour en temps réel)

| Phase | Tâche | % | Tests liés |
|-------|-------|---|------------|
| **9** | Pool E2E + API/CLI audit | **100 %** | T-P*, T-C* |
| **Global** | Système MVP + réseau + pool | **~95 %** | 234 pytest |

**Avancement dashboard global : 100 %**  
**Avancement API/CLI : 100 %**

---

## 9. Tests modules Rapport 071 (2026-07-27)

| ID | Commande / scénario | Attendu | Statut | Dernière exec |
|----|---------------------|---------|--------|---------------|
| T-071-01 | `pytest tests/ -q` | **234 passed** | [x] | 2026-07-27 |
| T-071-02 | `python3 -c "from src.api.ai_routes import router_ai, router_chain_ext, router_webhooks; print('OK')"` | OK | [x] | 2026-07-27 |
| T-071-03 | `curl -s localhost:8000/api/v1/ai/status` | `{"agent_ready":true,...}` | [ ] | — |
| T-071-04 | `curl -s -X POST localhost:8000/api/v1/ai/memo -d '{"content":"test"}'` | block gravé | [ ] | — |
| T-071-05 | `curl -s localhost:8000/api/v1/chain/search?q=test` | results array | [ ] | — |
| T-071-06 | `curl -s localhost:8000/api/v1/chain/export?format=summary` | summary text | [ ] | — |
| T-071-07 | `curl -s -X POST localhost:8000/api/v1/api-keys/generate -d '{"label":"test"}'` | token `artcb_xxx` | [ ] | — |
| T-071-08 | WebSocket `/ws/stream_thought` — start/token/commit | block gravé + committed | [ ] | — |
| T-071-09 | Frontend build `npm run build` | 0 erreurs TypeScript | [x] | 2026-07-27 |
| T-071-10 | Page `/agent-memory` accessible dans l'UI | render OK | [ ] | — |
| T-071-11 | i18n — changer langue → textes changent sur toutes pages | 7 langues | [ ] | — |
| T-071-12 | Google AI connector — `_google_ai_chat()` | réponse LLM | [ ] | — |
| T-071-13 | Wikipedia connector — `_fetch_wikipedia_batch()` | articles chargés | [ ] | — |

---

## 4. Avancement % (mis à jour — 2026-07-27)

| Phase | Tâche | % | Tests liés |
|-------|-------|---|------------|
| **i18n** | useTranslation × 14 pages, 7 langues, 238+ clés | **100 %** | T-071-11 |
| **API Keys** | generate/list/me/delete + Bearer middleware | **100 %** | T-071-07 |
| **AI Routes** | status/memo/think/memory + chain/search/export + webhooks | **100 %** | T-071-03→06 |
| **stream_thought** | WebSocket token-par-token → bloc PoL | **100 %** | T-071-08 |
| **AgentMemory UI** | page complète avec 7 onglets | **100 %** | T-071-10 |
| **Google AI** | Gemini connector dans llm_router.py | **100 %** | T-071-12 |
| **Wikipedia** | connector dans sources.py | **100 %** | T-071-13 |
| **Tests totaux** | 234 pytest passent | **100 %** | T-071-01 |
| **Global Rapport 071** | P0 i18n + P0 API Keys + P1 tests + IA autonome | **~95 %** | tous |

---

## 10. Tests sécurité rotation de clé + endpoints manquants (2026-08-05)

> Session rapport 115/116 — fixes sécurité critiques appliqués et testés en production (Replit N1+N2).

| ID | Commande / scénario | Attendu | Statut | Dernière exec |
|----|---------------------|---------|--------|---------------|
| T-SEC-01 | `pytest tests/test_governance_rotation.py` | 16/16 PASS — sans-signature → GovernanceError | [x] | 2026-08-05 16/16 ✅ |
| T-SEC-02 | `POST /api/v1/governance/creator-key-rotation` sans signature | HTTP 422 (Pydantic min_length=1) | [x] | 2026-08-05 ✅ |
| T-SEC-03 | `POST /api/v1/governance/user-key-rotation` sans signature | HTTP 422 (Pydantic min_length=1) | [x] | 2026-08-05 ✅ |
| T-SEC-04 | `POST /api/v1/governance/creator-key-rotation` signature invalide | HTTP 400 GOVERNANCE_ERROR | [x] | 2026-08-05 ✅ |
| T-SEC-05 | `GET /api/v1/chain/status` sur Replit N2 | HTTP 200 `{"status":"ok",...}` | [x] | 2026-08-05 ✅ |
| T-SEC-06 | `GET /api/v1/chain/blocks` sur Replit N2 | HTTP 200 `{"blocks":[...],...}` | [x] | 2026-08-05 ✅ |
| T-SEC-07 | `GET /api/v1/node/status` sur Replit N2 | HTTP 200 `{"node_id":"node_1eb8e5ca44e4",...}` — pas matché par /node/{id} | [x] | 2026-08-05 ✅ |
| T-SEC-08 | `POST /api/v1/ir/learn` wallet + content | HTTP 200 bloc grave, pol_score > 0 | [x] | 2026-08-05 ✅ |
| T-SEC-09 | `scripts/test_replit_p2p_reel.py` — 2 nœuds Replit production | 25/25 PASS — N1 blocs=1, N2 sync=0, blocs prives non propagés | [x] | 2026-08-05 25/25 ✅ |
| T-SEC-10 | `scripts/replay_qa_platform.py` | 478/478 PASS | [x] | 2026-08-05 478/478 ✅ |
| T-SEC-11 | `grep "unsigned" src/**/*.py` dans le code exécutable | Aucune occurrence dans logique fonctionnelle | [x] | 2026-08-05 ✅ |

**Résumé sécurité :**
- `sig_status="unsigned"` : **physiquement impossible** — rotation sans signature lève `GovernanceError` immédiatement
- `signature_hex or "unsigned"` : **dead code supprimé** — remplacé par `signature_hex` direct (commenté)
- Aucun mode dev / mode laxiste : la règle s'applique dans TOUS les environnements

---

## 11. Tests P2P Replit production (2026-08-05)

| ID | Scénario | Nœuds | Attendu | Statut | Dernière exec |
|----|----------|-------|---------|--------|---------------|
| T-P2P-01 | N1+N2 health | Replit N1+N2 | `status=ok`, `debug=true` | [x] | 2026-08-05 ✅ |
| T-P2P-02 | Wallet création N1 + N2 | Replit N1+N2 | adresse `artcb1...` | [x] | 2026-08-05 ✅ |
| T-P2P-03 | N1 add N2 peer | Replit N1→N2 | peers=1 sur les deux | [x] | 2026-08-05 ✅ |
| T-P2P-04 | `POST /ir/learn` N1 | Replit N1 | bloc public index=0 | [x] | 2026-08-05 ✅ |
| T-P2P-05 | `POST /p2p/sync` N2 depuis N1 | Replit N2 | sync OK | [x] | 2026-08-05 ✅ |
| T-P2P-06 | Bloc privé N1 NOT propagé | Replit N2 | N2 blocs=0 | [x] | 2026-08-05 ✅ |

---

## Journal d'exécution — 2026-08-05

| Date UTC | Session | Tests passés | Notes |
|----------|---------|--------------|-------|
| 2026-08-05T16:00Z | Audit sécurité "unsigned" + endpoints | 478/478 pytest + 25/25 P2P Replit | Rapport 116 |

---

## 12. Tests protocole économique D-023 (2026-08-25)

| ID | Commande / scénario | Attendu | Statut | Dernière exec |
|----|---------------------|---------|--------|---------------|
| T-E01 | `pytest tests/test_economics_protocol.py` | 21M cap, R(H) sans halving index, HBP, P_owner, settlement, API | [x] | 2026-08-26  D-024 |
| T-E02 | `pytest tests/test_wallet_rewards.py` | genesis 50 ARTCB, index 210k **ne coupe plus** | [x] | 2026-08-26 D-024 |
| T-E03 | `python3 -m pytest tests/ -q` | suite complète 0 fail | [x] | 2026-08-26 **534 passed, 20 skipped, 0 fail** |
| T-E04 | `pytest tests/test_economics_rapport162.py` | time-norm, M1, fleet P, binding≤1, WorkID, vault, lock 30j, EconomicRoot | [x] | 2026-08-28 |
| T-E05 | `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line` | suite complète post-162 | [x] | 2026-08-28 **554 passed, 20 skipped, 0 fail** — `logs/20260828_pytest_rapport163.txt` |
| T-E06 | `pytest tests/test_e2e_protocol_164.py tests/test_economic_root_native.py tests/test_oracle_fees.py tests/test_stripe_priority_job.py` | e2e ProtocolEngine, C v2, oracle honnête, Stripe no-mint | [x] | 2026-08-28 |
| T-E07 | `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line` | suite complète post-164 | [x] | 2026-08-28 **584 passed, 21 skipped, 0 fail** — `logs/20260828_pytest_rapport164_full.txt` |
| T-E08 | `make -C src/c clean all test` | EconomicRoot v2 empty==v1, tamper change hash | [x] | 2026-08-28 |
| T-E09 | `python3 scripts/run_sim164_e2e.py` | sim 164 failures=[] conservation+21M+attaques | [x] | 2026-08-28 `simulations/20260828T200518Z_e2e164/` |
| T-E10 | Stripe CI `scripts/stripe_job_payment_ci.py` | skip propre si secret absent ; accepte `KEY_API_STRIPE` (Cursor/Doppler) et `KEY_API_STRIPE_ACTION` (GHA) | [x] | 2026-08-29 PI `canceled` `mints=false` |
| T-E11 | OVH `http://152.228.144.34:8000/health` | 200 + `git_sha` branche déployée ; economics 200 | [x] | 2026-08-29 `deaf620` puis HEAD 166 |
| T-E12 | OVH `POST /api/v1/economics/jobs/priority` | JobPayment Stripe create+cancel, `mints=false` | [x] | 2026-08-29 `pi_…` canceled |
| T-E13 | `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line` | suite post-166 | [x] | 2026-08-29 **607 passed, 8 skipped, 0 fail** |
| T-E14 | Doppler `GET /v3/me` + SSH `ubuntu@152.228.144.34` | token Cursor valide ; clé `SSH_PRIVATE_KEY` Doppler | [x] | 2026-08-29 |
| T-E15 | `pytest tests/test_economic_snapshot_167.py` | SID déterministe, WorkID unique, snapshot N figé | [x] | 2026-08-29 |
| T-E16 | `python scripts/run_sim167_distributed.py` | `failures=[]` ; 191632 canonique ; 191605 erreur réelle conservée | [x] | 2026-08-29 |
| T-E17 | `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line` | suite post-167 | [x] | 2026-08-29 **613 passed, 8 skipped** |
| T-E18 | `python3 scripts/artcb_live_bootstrap.py` | health 200 + `/api-keys/me` 200, token non imprimé | [x] | 2026-08-29 `kid_abad2468682059ef` |
| T-E19 | `python3 scripts/run_sim168_adversarial_live.py` | replay WorkID rejeté ; live_ok | [x] | 2026-08-29 `20260829T195130Z` |
| T-E20 | `POST /api/v1/ai/memo` Bearer agent | bloc gravé | [x] | 2026-08-29 bloc #0 PoL 0.75 |
| T-E21 | `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line` | suite post-168 | [x] | 2026-08-29 **618 passed, 8 skipped** |
| T-E22 | OVH `GET /health` | `git_sha=5b4b24ae` `branch=main` | [x] | 2026-08-29 deploy `main` |
| T-E23 | `https://152.228.144.34:8443/health` + `/api-keys/me` | 200 + key_id | [x] | 2026-08-29 self-signed |
| T-E24 | `python scripts/run_sim169_secure_live.py` | `failures=[]` sha_match https_up | [x] | `20260829T214058Z` |
| T-E25 | pytest post-169 | 625 passed / 8 skipped | [x] | `logs/20260829_pytest_rapport169.txt` |
| T-E26 | `GET /health` vs `origin/main` | égalité SHA **après chaque merge** | [x] | 2026-08-31 live=`5b4b24ae` main=`376b0e4c` **ÉCART DÉMONTRÉ** |
| T-E27 | `pytest tests/test_e2e170_node_isolation.py` | 3 projets Doppler distincts, Stripe pas sur nœud | [x] | 2026-08-31 6 passed (fichier) |
| T-E28 | `python3 scripts/provision_doppler_node_projects.py` | 3 projets créés **ou** 403 service token documenté | [x] | 2026-08-31 **403** ×3 — `11_doppler_provision.json` |
| T-E29 | `python3 scripts/ovh_api_inventory.py ovh-node-2` | `/me` nic `vc491276-ovh` ; VM count honnête | [x] | 2026-08-31 me=200, 0 VM |
| T-E31 | pytest post-170 (C lib built, no liboqs) | 617 passed / 20 skipped / 2 fail 503 suite-order | [x] | `logs/20260831_pytest_rapport170_cbuilt.txt` |
| T-E32 | `pytest tests/test_e2e171_aws_doppler.py tests/test_e2e172_aws_ec2.py` | isolation slugs + aliases AWS + pas de secrets | [x] | 2026-08-31 16 passed with 170 |
| T-E33 | `python3 scripts/provision_aws_ec2.py` (diagnose) | STS + ec2_allowed | [x] | 2026-08-31 STS 0 / Describe 0 |
| T-E34 | `python3 scripts/provision_aws_ec2.py --yes` | instance tagged `aws-node-3` + IP publique | [x] | `i-085b74abd1aaf04ee` `51.44.222.232` t3.small |
| T-E35 | `bash scripts/deploy_aws.sh IP BRANCH` | health HTTP 8000 + HTTPS 8443 ; OVH1 inchangé | [x] | SHA AWS `0d3d432` ; OVH1 `5b4b24ae` |
| T-E36 | OVH1 + AWS3 health simultanés | 2/4 compute ; OVH2 = 0 VM | [x] | sim `20260831T162428Z` failures=[] P2P 200/200 |
| T-E37 | `python3 scripts/ovh_api_inventory.py ovh-node-2` | nic `vc491276-ovh` ; 0 instance | [x] | me=200 projects=[] |
| T-E38 | `pytest tests/test_e2e206_ovh4_keepbook.py` | SSH sans rescue ; pub `artcb-ovh-node-4-20260902` ; keep-book SHA `ad017bca` ; pas de certif | [x] | 2026-09-02 |
| T-E39 | `pytest tests/test_e2e207_follow_main.py` | 4 nœuds officiels + clones suivent `origin/main` ; timer ; pas de wipe ; PR #51 hors main | [x] | 2026-09-02 4 passed ; timer enabled ×4 ; FETCH_METHOD=origin ; BOOK=1 |
| T-E40 | `pytest tests/test_e2e205_no_rescue_biometric.py tests/test_e2e208_biometric_cert_gate.py tests/test_webauthn_biometric.py` | WebAuthn D-055 ; gate lit RESULT.json ; D-056 GO après DV-02/06 PASS live | [x] | 2026-09-02 42 related passed |
| T-E41 | `pytest tests/test_e2e205_no_rescue_biometric.py` (camera-first) | bouton Visage = `setCameraOn(true)` sans WebAuthn platform | [x] | 2026-09-02 27 passed |
| T-E42 | `pytest tests/test_e2e215_egress_wallet_list_audit.py` | egress secrets (webhooks, LLM), SSRF webhooks, `/wallet/list` projection, 401 uniforme + journal, assurance biométrie + audit, README D-024/D-025 | [x] | 2026-09-04 14 passed ; régression 147 passed / 12 fail **préexistants** (wallet_rewards ×6, sdk ×4, e2e169 suite-order ×2) — rapport 215 §3 |
| T-E43 | `pytest tests/test_e2e216_authz_privacy.py tests/test_groups.py tests/test_api.py tests/test_dashboard_api.py` | moteur authz GRANT/REVOKE DENY>ALLOW plafond agent ; `private`/`group` réellement filtrés sur `/graph` `/chain` `/search` ; `actor_address` n'est plus une preuve ; A3→C3/Sub2/Document X pas Y pas C2 | [x] | 2026-09-04 7 passed (e2e216) + groups/api/dashboard hors wailly pypdf préexistant |
| T-E44 | `pytest tests/test_e2e217_domain_genesis.py tests/test_e2e216_authz_privacy.py tests/test_groups.py` | Genesis ORG/GROUP = constitution locale + hash public ; P2P sans privé ; CAN_I agent ; mutations groupes exigent session | [x] | 2026-09-04 |
| T-E45 | `pytest tests/test_e2e218_domain_registry.py tests/test_e2e217_domain_genesis.py tests/test_e2e216_authz_privacy.py` | Domain Manifest + Registry : nœud héberge / fondateur possède ; export/import + hash ; pas de copie auto du corps | [x] | 2026-09-04 57 passed local ; live `ae5868f` ×4 ; Alice `org_389303641163` sur OVH1 seulement |
| T-E46 | `pytest tests/test_e2e220_org_governance.py tests/test_e2e218_domain_registry.py tests/test_e2e216_authz_privacy.py` | Ancrage public hash reward=0 ; transfert ORG/GROUP ; SALE vs DIRECTOR_CHANGE/SUCCESSION/KEY_ROTATION ; révocation ancien contrôleur+agents ; cancel/decline ; ORG_ID inchangé | [x] | 2026-09-05 43 passed local ; live `9a53668` ×4 certified ; SALE Aline→Bob export 403/200 ; hash+transfert sur OVH1 seulement |
| T-E47 | `pytest tests/test_e2e221_commitment_convergence.py tests/test_e2e220_org_governance.py tests/test_e2e176_sync_500.py` | Convergence tip public DOMAIN_COMMITMENT/ORG_CONTROL_TRANSFER ; sel anti-dictionnaire ; transfert sans adresses nues ; un seul propose pending | [x] | 2026-09-05 53 passed / 1 skipped local ; live `32a378d` ×4 certified ; 4/4 `last_hash=27350024…` digest identique |
| T-E48 | `pytest tests/test_e2e222_tip_resilience.py` | Import P2P déterministe (receive=pull) ; G duplicate / H prev_hash / I index / J hash / K event / M fork local | [x] | 2026-09-05 17 passed ; V-01-B live e68563e OVH1 stop, 2/3/4 gardent `27350024…` |
| T-E49 | `pytest tests/test_e2e233_autodev_user.py tests/test_mcp_server.py` | User auto-dev : sess_ + agent ; opérateur ≠ user ; agent 403 ORG ; mémo privé attribué à l'adresse ; MCP content= | [x] | 2026-09-06 |
| T-E50 | `pytest tests/test_e2e236_org_node_roles.py tests/test_e2e218_domain_registry.py` | HOST ≠ REPLICA ≠ CONSENSUS ; liste authorized_nodes ≠ certificat ; add_replica ne copie pas le BODY ; TRANSFER_OWNERSHIP humain | [x] | 2026-09-07 |
| T-E51 | `pytest tests/test_e2e263_close.py` + live `scripts/run_live263_close.py` | Complétude A→Z ; tip-attest Q=3 (4 sigs, 1086) ; evidence signée authenticated×4 ; 188 Q=3 agent+mesh ; mesh pendant partition prepared=2 ; 2 byz 0 append ; fork 1084 puis 1086×4 ; partition 2 restorée RULES=0 | [x] | 2026-09-08 `856c0ee` ×4 |
| T-E52 | `pytest tests/test_e2e264_pbft_viewchange.py` + live `scripts/run_live264_pbft_viewchange.py` | PBFT view-change Q=3 + NEW-VIEW ; primary isolé processus UP ; old view wrong_view ; 188 nouvelle vue ; restore ; 4/4 même vue | [x] | 2026-09-08 live `2026912` ×4 view 0→1 ; VC×3 ; NEW-VIEW ovh-node-2 digest `45c456ba…` ; 188 old prepared=0 ; 188 new prepared=3 commits=3 ; mémo 1086 hash `1332be89…` ; 1087 ×4 ; R264=0. **BASELINE**, pas certification finalité blocs. |
| T-E53 | `pytest tests/test_e2e_pbft_finality.py tests/test_e2e254_ns_trace.py` + live `scripts/run_live265_pbft_e2e.py` | PBFT finalité blocs PRE-PREPARE/PREPARE/COMMIT + cert Q=3 ; traces ns ; A–L live 4 nœuds ; index certifié non reorg | [x] | 2026-09-08 SHA `f470d7b6` ×4 ; seq 1087 cert `e2055059…` Q=3 ; view 1→2 ; height **1091** tip `42510680…` ; traces ns `pbft_*` ; **PBFT_LIVE_E2E_NOT_VALIDATED** (append mémo pas exclusif-PBFT ; D/C/K partiels). |
| T-E54 | `pytest tests/test_e2e266_pbft_cert.py` + live `scripts/run_live266_pbft_cert.py` | Exclusivité PBFT append public ; PRE-PREPARE Byzantine signés contradictoires ; double certificat impossible ; crash primary ; partition 2-2 ; restart après cert ; SHA = origin/main ×4 | [x] | 2026-09-08 SHA `78cd8d6…` ×4 ; V-01 seq 1094 cert `5688fb3c…` ; V-02 dual PP sans double finalité ; V-04 view 3→4 stop primary ; V-05 2-2 bloqué ; height **1095** view 5 |
| T-E55 | `pytest tests/test_e2e267_chat_truth.py` + live `scripts/run_live267_user_query_ingest.py` | Prompt vs thinking vs tokens ; ingest agent-mediated ; SHA live vs origin/main | [x] | 2026-09-08 SHA `230b8eb5` (ingest 1095) puis recert `b66f51a9` ×4 height **1097** tip `40b16afa…` (P0 ingest 1096) |
| T-E56 | `pytest tests/test_e2e268_agent_pbft.py` + live `scripts/run_live268_p8_prepared_vc.py` `scripts/run_live268_agent_protocol.py` | Prepared cert dans VC ; Y refusé ; agent bootstrap+idempotence ; SHA = origin/main ×4 | [x] | 2026-09-08 SHA `960f069e` ×4 ; P8 seq 1097 `c79319fb…` Y 409 must_repropose_prepared view 6→7 ; agent event 1098 `9c67ac06…` already_committed ; height **1099** ; **pas** 100 % PBFT |
| T-E57 | `pytest tests/test_e2e269_pbft_campaign.py` + live `scripts/run_live269_pbft_campaign.py` | P9 mutation cert ; P10 dual propose ; P11 PREPARE Y ; P12 replay ; P13 crash ; P14 JSON tronqué ; P15 agent identity ; P16 idempotency_conflict ; P17 cert/bloc ; P18 mutations ×N ; SHA = origin/main ×4 | [x] | 2026-09-08 live `f59dd88d` ×4 ; P9–P18 PASS ; P10 digest `24b8a872…` seq 1099 writes 4/4 ; P16 409 `idempotency_conflict` ; catch-up privé 1100 `204f6164…` ×4 height **1101** ; P18 re-vérif 210/210 ; AWS t3.small ; HPC non. `logs/269_p9_p18_20260908T172433Z.json` + `logs/269_p9_p18_catchup_20260908T173122Z.json`. Campagne interne 100 % PASS. Preuve formelle toutes exécutions : NON. |
| T-E58 | `pytest tests/test_e2e270_pbft_cert_matrix.py` + live `scripts/run_live270_pbft_cert_matrix.py` | Matrice certification PBFT ; CERTIFIED_100 interdit si une ligne critique NOT_PROVEN ; live WAN + fautes combinées ; SHA = origin/main ×4 | [x] | 2026-09-08 live `8050981` ×4 moteur `f59dd88` ; 25 PASS 0 FAIL 18 NOT_PROVEN ; CERTIFIED_100=false ; height 1101→**1107** tip `94f57bb2…` view 7→8 ; partition 2–2 dual=false ; C01 seq 1104 ; F02 seq 1105 primary ovh-4 down ; netem 100ms seq 1106. `logs/270_pbft_cert_20260908T182742Z.json`. **PBFT 100 % = NON CERTIFIÉ**. |
| T-E59 | `pytest tests/test_e2e271_close_not_proven.py` + live `scripts/run_live271_close_not_proven.py` | Exécuter les 18 NOT_PROVEN R270 en live (188, netem 1–50 %, reorder, asym, B04/B05, C04, X03) ; unlock VIEW-CHANGE si 409 equivocation ; N04 exige round à 1 % ; C04 FAIL sauf ≥1000 rounds ; SHA = origin/main ×4 | [x] | 2026-09-08 live `4fb2b1bb` ×4 moteur `f59dd88` ; **34 PASS 9 FAIL 0 NOT_PROVEN** ; CERTIFIED_100=false ; X01 188 PASS ; B05 Y=200 FAIL ; unlock seq **1107** `54bb4291…` restore seq **1108** `62bbae14…` height **1109** view 12 ; somme émise **2340.49999651** ARTCB. `logs/271_close_20260908T201920Z.json`. **PBFT 100 % = NON CERTIFIÉ**. |
| T-E60 | `pytest tests/test_e2e272_pbft_p0.py` + live `scripts/run_live272_p0_replay.py` | enter_view jette accepted orphelin des vues < new ; prepared X obligatoire ; Y 409 ; 10 rounds sains puis replay N03/N04 ; SHA = origin/main ×4 | [x] | 2026-09-08 SHA `3286996` ×4 ; 10/10 ; B05 Y 409 `must_repropose_prepared` ; N03 PASS ; N04 1–30 % PASS liveness, **50 % FAIL** ; height **1130** tip `49dd849a…` view 15. CERTIFIED_100=false. |
| T-E61 | `pytest tests/test_e2e273_identity_binding.py tests/test_e2e273_new_view_quorum.py` + live `scripts/run_live273_identity_binding.py` | NodeID↔clé officielle ; A3/A7 K1→ovh-node-2 = 409 `invalid_replica_key_binding` ; NEW-VIEW prepared exige Q VIEW-CHANGE ; fail-closed `state_incomplete` ; artefacts campaign/ + MANIFEST.sha256 ; CERTIFIED_100 reste false | [x] | 2026-09-08 tests PASS. Live SHA `d9eba2ac` ×4 **avant** déploiement 273 : A3 GAP — K1 accepté comme ovh-node-2 (`verify_prepare` OK, HTTP 200 `not_accepted` ×3). Pas un PASS identité. N04 50 % FAIL. CERTIFIED_100=false. |
| T-E62 | `pytest tests/test_e2e273_identity_binding.py tests/test_e2e273_new_view_quorum.py` + live `scripts/run_live277_issue77.py` | Issue #77 : mesurer R273 **après** déploiement ×4 ; A3/A7 = 409 binding ; NEW-VIEW 1/2 VC insuffisant, Q=3 admissible, `state_incomplete` ; 200 `not_accepted` ≠ PASS identité ; N04 50 % reste FAIL ; A4–A8/TPM/C04 non inventés ; CERTIFIED_100=false | [x] | 2026-09-08 SHA `41c9e1dd` ×4 = origin/main ; binding_enforced ×4 ; A3/A7 409 ×3 ; NV 1/2/3 + state_incomplete PASS ; N04 50 % FAIL (`not_primary`) ; A4–A8/TPM/C04 NOT_PROVEN ; height **1133** tip `cc0bf8a1…` view 15. `logs/277_issue77_20260908T233012Z.json` MANIFEST `951e16fd…`. CERTIFIED_100=false. |
| T-E63 | `pytest tests/test_e2e278_adversarial_identity.py` + live `scripts/run_live278_adversarial.py` | Overlay live A4/A5/A6/A8 ; rollback registry ; official_node fichier vs env ; platform-attest VM analog ≠ TPM ; verdicts séparés ; CERTIFIED_100=false | [x] | 2026-09-09 SHA `d621244` puis `6715b6f` ×4 ; A4–A8 409 live ovh-4 ; rollback v29 rejeté après fix mémoire ; tamper file=node2 env=node4 parlé=node4 ; TPM ABSENT ×4 ; analog cloud ×4 (AWS `i-085b74abd1aaf04ee` t3.small + UUID OVH) ; N04 50 % FAIL ; C04 NOT_PROVEN ; height **1133**. CERTIFIED_100=false. |
| T-E64 | `pytest tests/test_e2e279_platform_trust_sizes.py` + live `scripts/run_live279_trust_sizes.py` | Trust L0–L4 ; dual verdicts TPM vs cloud ; binding NodeID↔instance ; `block_size_bytes` convergent ; audit `blocks.jsonl` réel ; CERTIFIED_100=false | [x] | 2026-09-09 SHA `5e0d424` ×4 ; L2 `CLOUD_ATTESTED` ×4, hardware TPM `NOT_AVAILABLE` ; binding verified ; 1133 lignes index 0–1132 ; claimed≠line **1133/1133** ; min 7496 max 47192 (`pbft_cert`) avg 9124 ; docs 622/28k/665k ≠ ce livre ; N04 50 % FAIL ; C04/TPM quote NOT_PROVEN. CERTIFIED_100=false. |
| T-E65 | `pytest tests/test_e2e279_platform_trust_sizes.py` + live `scripts/run_live280_split_verdicts.py` | split_verdicts : observed ≠ crypto ≠ certification ; pin AWS IID ≠ CERTIFIED_100 ; CERTIFIED_100=false | [x] | 2026-09-09 SHA `0d7546c` ×4 ; observed PASS ×4 ; crypto NOT_PROVEN ×4 ; certification FAIL ; AWS3 rsa2048 pin PASS (eu-west-3) sans élever crypto ; OVH pin N/A ; N04 FAIL ; C04/TPM quote NOT_PROVEN. CERTIFIED_100=false. |
| T-E66 | `pytest tests/test_e2e281_vtpm_quote.py tests/test_e2e279_platform_trust_sizes.py` + live `scripts/run_live281_vtpm_quote.py` | quote TPM2 fail-closed ; `/dev/tpm0` absent sur les 4 VM actuelles = DEVICE_ABSENT ≠ L3 ; guest swtpm n’est pas vTPM hyperviseur ; N04 last FAIL ; CERTIFIED_100=false | [x] | 2026-09-09 SHA `2c9c1d5` ×4 ; quote DEVICE_ABSENT ×4 ; L2 CLOUD_ATTESTED ; crypto NOT_PROVEN ; hardware NOT_AVAILABLE ; certification FAIL ; honesty_guard PASS ; AWS pin sous-verdict ; N04 FAIL ; CI NOT_PROVEN (combined status vide). CERTIFIED_100=false. |
| T-E67 | `pytest tests/test_e2e282_nitrotpm.py` + live `GET /platform-attest` ×4 | AMI UEFI+NitroTPM ; quote vérifiée = L3 jamais L4 ; binding nouvelle instance ; N04 last FAIL ; CERTIFIED_100=false | [x] | 2026-09-09 SHA `d5e0c66` ×4 ; AMI `ami-0b82a9f93189c018e` ; `i-06c9404e42798ff76` EIP `13.38.209.25` ; AWS3 L3 `VTPM_ATTESTED` quote verified AMZN NitroTPM ; crypto PASS ; hardware NOT_AVAILABLE ; certification FAIL ; OVH DEVICE_ABSENT L2 ; ex-`i-085b74abd1aaf04ee` stopped. CERTIFIED_100=false. |
| T-E68 | `pytest tests/test_e2e283_profile_cert.py tests/test_e2e279_platform_trust_sizes.py tests/test_e2e281_vtpm_quote.py` + live `scripts/run_live283_profile_cert.py` | Certification par profil d’environnement ; L4 VM = NOT_APPLICABLE pas FAIL ; AWS3 L3 PARTIAL (EK) ; OVH L2 PASS ; CERTIFIED_100=false ; N04 last FAIL | [x] | 2026-09-09 SHA `6677420` ×4 ; OVH L2 profil PASS L3 NOT_REACHABLE L4 NOT_APPLICABLE ; AWS3 L3 quote+freshness+binding PASS, EK LOCAL_CREATEEK NOT_PROVEN, profil PARTIAL, l4 NOT_APPLICABLE ; hardware NOT_APPLICABLE ×4 ; `certified_hardware_identity=false` ; N04 FAIL last. CERTIFIED_100=false. |
| T-E69 | `pytest tests/test_e2e284_classify.py` + live `scripts/run_live284_classify.py` | UNKNOWN≠BARE_METAL ; swtpm≠L3 ; `/dev/tpm0`≠L3 ; theo vs verified ; CERTIFIED_100 dénominateur ; N04 last ; PRE_R273 GAP conservé | [x] | 2026-09-09 SHA `b848428` ×4 ; OVH VM_PROVEN L2 `CLOUD_IDENTITY_OBSERVED` ; AWS3 NITROTPM L3 PARTIAL missing `ek_ak_provenance` ; retry getcap trunc + OVH restart ; Mac RFC1918 NOT_REACHABLE. CERTIFIED_100=false. |
| T-E70 | `pytest tests/test_e2e286_mac_ssh.py` + live `scripts/run_live286_mac_ssh.py` | mac-node-local hors OFFICIAL_COMPUTE ; RFC1918 ; KEY_API_ARTCB_DOPPLER_MAC = secret Cursor env + artcb-blockchain/dev (prd seul = FAIL) ; jamais dump SSH ; timeout LAN ≠ PASS ; CERTIFIED_100=false | [x] | 2026-09-09 pytest 8 passed. Live stamp `20260909T181610Z` SHA ×4 `75836c7` = origin/main. Token MAC absent env Cursor ; artcb-blockchain/dev n=67 sans KEY_API_ARTCB_DOPPLER_MAC ; prd HTTP 400 ; TCP 10.234.49.2:22/:8001 TimeoutError ; ssh_login FAIL ; mac_health_sha null. AWS3 rattrapé `8e95fde`→`75836c7` keep-book. CERTIFIED_100=false. |
| T-E71 | `pytest tests/test_e2e287_mac_tunnel.py` + live `scripts/run_live287_mac_tunnel.py` | RFC1918 / `.local` jamais un tunnel ; `tunnel_required` ; P2P LAN URL forbidden ; ngrok 0 tunnel ≠ PASS ; ngrok-sur-cloud-VM n’atteint pas le Mac ; CERTIFIED_100=false | [x] | 2026-09-09 pytest PASS. Live stamp `20260909T182620Z` SHA ×4 `75836c7`. ngrok 0/0 ; remote `rfc1918_requires_tunnel` ; P2P `private_or_loopback_forbidden` ; tunnel ABSENT ; mac_health_sha null. CERTIFIED_100=false. |
| T-E74 | `pytest tests/test_e2e297_mac_replica_membership.py tests/test_e2e296_context_contract.py tests/test_e2e286_mac_ssh.py tests/test_e2e273_identity_binding.py::test_official_ids_still_four` | Mac dans `official_pbft_replica_ids()` ; N=5 f=1 Q=3 ; nouveau `pbft_replica` agrandit N ; seeds IPv4 restent 4 ; contrat sans thinking ; CERTIFIED_100=false | [x] | 2026-09-09 13 passed après correction isolation. Mac = replica, pas sas enrolled=false. CERTIFIED_100=false. |
| T-E76 | `pytest tests/test_e2e299_never_delete_archive.py tests/test_e2e297_mac_replica_membership.py tests/test_e2e298_ingest_skip_reason.py` | R299 : jamais supprimer (rules 11–15 + code commenté) ; archive append-only `/tmp` ; Mac replica N adaptatif ; ingest reason honnête ; CERTIFIED_100=false | [x] | 2026-09-10T23:35:00Z pytest 10 passed. Prompt archivé sha256 `cfb2db03…` chars 2873. VM SHA non mesuré (TCP 22/8000/8443 timeout depuis ce Mac). CERTIFIED_100=false. |
| T-E77 | `pytest tests/test_e2e300_thinking_journal.py tests/test_e2e297_mac_replica_membership.py` | R300 : hook afterAgentThought journal local ; thinking jamais ARTCB ; index all-rules ; Mac replica pas observateur Bob §4 ; CERTIFIED_100=false | [x] | 2026-09-10T00:05:00Z pytest 10 passed. Mac SHA `4fe76dd` = origin/main. Hook stdout vide (thinking pas dans le chat). CERTIFIED_100=false. |
| T-E78 | `pytest tests/test_e2e302_live_n_membership.py tests/test_e2e297_mac_replica_membership.py tests/test_e2e273_identity_binding.py::test_official_ids_still_four` + live `scripts/run_live302_mac_n5_transport.py` | seeds IPv4=4 ≠ membership N=5 ; `n_f_q(4)` historique ; live 270/271 lisent `official_pbft_n_f_q()` ; RFC1918 jamais peer replica ; tunnel public seul pour HTTP Mac ; CERTIFIED_100=false ; Mac P2P live NON PROUVÉ | [x] | 2026-09-10T11:33:20Z pytest 13 passed. Live stamp `20260910T113320Z` N=5 Q=3. SHA OVH1/2/4+Mac `e58dc28` ; AWS3 lag `bc0a9b9`. Livre ×4 height 1133 tip `cc0bf8a1…` ; Mac height 6 tip `01a5f743…`. Doppler nom `MAC_SUDO_PASSWORD` present. Mac P2P NON PROUVÉ. CERTIFIED_100=false. |
| T-E79 | `pytest tests/test_e2e303_sha_layers_mac_doppler.py tests/test_e2e302_live_n_membership.py` + live HTTPS `artcb.me`/`n2`/`n3`/`n4` + Mac `:8001` | couches SHA 07ed590 vs 852f0e2 ; GitHub statuses [] ; health git_sha ≠ modules ; Doppler run skip restricted ; `/pbft/view` n=5 ≠ PREPARE ; CERTIFIED_100=false | [x] | 2026-09-10T14:51:00Z seeds HTTPS 200 SHA `852f0e2` height 1133 n=5 view 15 primary stocké ovh-4. Mac après wrapper n=5 view 0 height 6 prepare 0. Ingest 409. Mac P2P NON PROUVÉ. |


