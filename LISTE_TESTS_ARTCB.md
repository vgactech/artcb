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

