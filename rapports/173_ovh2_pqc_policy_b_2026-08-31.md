# Rapport 173 — OVH2 live + politique crypto B (ML-DSA-65 prioritaire)

**Horodatage UTC :** 2026-08-31T18:52:12Z  
**Branche :** `cursor/ovh2-pqc-policy-b-16d8`  
**Commit déployé OVH2/AWS3 :** `65f2a3a31351da2fa7c840956b86de38902b4a3a`  
**OVH1 :** `5b4b24ae692ac2bb8255a4a5a3ca941b4365db29` — **non redéployé**  
**Simulation :** `simulations/20260831T185212Z_e2e173_ovh2_pqc_policy_b` `failures=[]`  
**Certification :** `READY FOR NEXT TEST` — **NOT MAINNET CERTIFIED**.

Aucun secret n’est reproduit ici. Les V-01…V-07 **tokenomics** restent provisoires. Les validations distribuées sont **DV-01…DV-07** (choix de protocole, pas un PASS).

---

## A. Décisions gelées

| ID | Choix utilisateur | Contenu |
|----|-------------------|---------|
| D-032 | **B** (+ C si PQC présent) | ML-DSA-65 prioritaire ; Ed25519 temporaire jusqu’au 2026-12-31T00:00:00Z ; `hybrid:ed25519+ML-DSA-65` dès que liboqs est là ; anti-downgrade par `peer_id` ; pas de négociation implicite |
| D-033 | DV profil B | DV-01 C, DV-02 C, DV-03 B, DV-04 C, DV-05 C, DV-06 B, DV-07 C |
| V éco | inchangé | Snapshot / transfer / grace / retire / finality / H_adult / HBP toujours ⏳ |

IAM : droits larges **conservés** en phase test (ordre utilisateur). Moindre privilège **non appliqué**.

---

## B. Machines live (PROBE LIVE, pas inventé)

| Nœud | IP | SHA `/health` | HTTP | HTTPS | PQC | `protocol_version` | bootstrap |
|------|----|---------------|------|-------|-----|--------------------|-----------|
| OVH1 | `152.228.144.34` | `5b4b24ae692ac2bb8255a4a5a3ca941b4365db29` `main` | 200 | 200 | ML-DSA-65 | absent (code ancien) | false |
| OVH2 | `151.80.107.29` | `65f2a3a31351da2fa7c840956b86de38902b4a3a` `cursor/ovh2-pqc-policy-b-16d8` | 200 | 200 | ML-DSA-65 | `173-devnet-1` | false |
| AWS3 | `51.44.222.232` | `65f2a3a31351da2fa7c840956b86de38902b4a3a` `cursor/ovh2-pqc-policy-b-16d8` | 200 | 200 | ML-DSA-65 | `173-devnet-1` | false |

OVH2 instance : `node-artcb-ovh-2` id `6470522e-1561-4741-9254-5f58b909eeb9` GRA11 d2-8 projet `1fc10a3fb27d4511a8c7873cd16243f2` nic `vc491276-ovh`.  
AWS3 : `i-085b74abd1aaf04ee` eu-west-3 **t3.small** (pas t3.large).  
Nœud 4 : **non défini**. Live compute = **3/4**.

OVH1 `p2p_node_id` live reste le placeholder historique `artcb1_REMPLACER_PAR_VOTRE_ADRESSE`.

---

## C. Politique crypto officielle `artcb-devnet-1`

```
preferred     = ML-DSA-65
temporary     = Ed25519 until 2026-12-31T00:00:00Z
hybrid        = ed25519+ML-DSA-65 when liboqs present (messages high-value)
anti_downgrade= peer that advertised ML-DSA-65 cannot later present Ed25519-only
silent_downgrade_forbidden = true
network_id    = artcb-devnet-1
protocol_version = 173-devnet-1
genesis_hash  = genesis-artcb-v2   (identifiant déclaré, pas un hash de bloc live)
```

Négociation : **aucune implicite**. Un pair sans suite (OVH1 ancien) est classé `ed25519_temporary_allowed` pendant la fenêtre.  
Messages high-value (hybride si PQC local) : `block_append`, `node_identity`, `settlement`, `peer_handshake`.  
Messages low-value : `health`, `peer_register_unsigned`.

AWS3 n’est **plus** en fallback Ed25519 : liboqs natif + `OQS_INSTALL_PATH=/home/ubuntu/_oqs` → `pqc.available=true`, `local_suite=hybrid:ed25519+ML-DSA-65`.

---

## D. P2P (connectivité, pas consensus)

Enregistrement public croisé (6 directions) : **HTTP 200 / registered=true**.

| Nœud | peer_count après 173 |
|------|----------------------|
| OVH1 | 3 (dont doublon AWS3 hérité du probe 172 — fingerprint différent) |
| OVH2 | 2 (OVH1 + AWS3) |
| AWS3 | 3 (OVH1 ×2 + OVH2) |

OVH2 a enregistré OVH1 avec suite `ed25519_temporary_allowed` et AWS3 avec `hybrid:ed25519+ML-DSA-65` — politique B observée.

**PROBE P2P ≠ réplication d’état ≠ quorum ≠ finalité.** DV-04 C exige 4 nœuds live à hash d’état identique : **non PASS**.

---

## E. Correctif runtime

Le checkout 173 cassait uvicorn (`IndentationError` dans `_bootstrap_health_response`). Corrigé en `65f2a3a`. AWS3 et OVH2 relancés **sans toucher OVH1**.

OVH2 : `POST /setup/init-node` localhost, seed sauvée `0600` sur l’instance, **jamais affichée**, wallet hybride, health `healthy`.

---

## F. Rotation secrets (après preuve d’accès)

| Plateforme | Accès validé | Rotation |
|------------|--------------|----------|
| AWS STS + EC2 describe | account `599128160879`, instance running `51.44.222.232` | **oui** : nouvelle access key, ancienne **Inactive**, Doppler `artcb3` mis à jour, profil local `artcb-node-3` mis à jour. IAM **AdministratorAccess inchangé**. Secrets Cursor `AWS_API_KEY_AGENT_3` / `AWS_API_CLI_AGENT_3` **périmés** — à remplacer par l’opérateur. |
| OVH2 API (Doppler `artcb-2`) | instance ACTIVE + SSH | **application secret non rotaté** : l’API OVH ne permet pas de faire tourner le secret d’application en place sans recréer l’app et casser le consumer key. À faire dans l’espace client OVH si l’opérateur le confirme. |
| OVH1 live key | `/me` 200 `kid_abad2468682059ef` | non rotatée (nœud de référence, non redéployé). |
| Stripe | absent des coffres nœud | inchangé |

---

## G. Tests

`tests/test_e2e170` … `173` : **21 passed**.  
Sim 173 : `failures=[]`, `invented=false`, `certified_distributed_mainnet=false`.

PR GitHub : création refusée (`must be a collaborator`) — même contrainte que 172.

---

## H. Ce qui n’est pas démontré

```
[OPEN] DV-01…DV-07 (lettres choisies, pas certifiées)
[OPEN] V-01…V-07 tokenomics
[OPEN] SHA homogène (volontaire : OVH1 conservé pour inter-version)
[OPEN] réplication d’état / settlement WAN
[OPEN] consensus / quorum / finalité
[OPEN] 4e machine
[FAIL for mainnet] certification mainnet
```
