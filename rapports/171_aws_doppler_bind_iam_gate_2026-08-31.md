# Rapport 171 — Binding Doppler `artcb-2` / `artcb3` + gate IAM AWS (pas de VM)

**Horodatage UTC :** 2026-08-31T15:45:00Z  
**Branche :** `cursor/aws-node-3-doppler-e769`  
**origin/main vérifié :** `a71a6d3` (PR **#39** 170 mergée)  
**Live OVH1 `/health` :** `5b4b24ae` branch=`main` — **≠** origin/main  
**Aucune VM OVH-2. Aucune instance EC2.**  
**Aucun token, mot de passe, access key n’est reproduit ici.**  
**Certification :** `READY FOR NEXT TEST` — **NOT MAINNET CERTIFIED**.

Le mot de passe console IAM collé dans le chat a servi au **premier login** (expiration / reset obligatoire). Il a été **changé** et n’est stocké que dans `~/.artcb/nodes/aws-node-3.env` (0600). **Rotater** aussi le secret d’application OVH-2 (re-collé dans le chat).

---

## A. État Git / live

```
origin/main     a71a6d3   Merge PR #39 e2e170-node-secret-isolation
cette branche   (HEAD 171)
live OVH1       5b4b24ae  branch=main   ← PROBE LIVE, ≠ origin/main
```

Pas de redéploiement du nœud 1 (pas d’ordre deploy).

---

## B. Doppler — slugs réels (créés dans l’UI, pas par l’agent)

Le token Cursor `artcb-node-1` reste un **service token** : `POST /v3/projects` → 403.  
L’utilisateur a créé deux projets et injecté les service tokens dans les secrets Cursor :

| Secret Cursor | Token name (`GET /v3/me`) | Projet listé | Nœud |
|---------------|---------------------------|--------------|------|
| `DOPPLER_TOKEN` | `artcb-node-1` | `artcb-blockchain` | partagé + OVH1 |
| `KEY_API_ARTCB_DOPPLER_2` | `artcb2` | **`artcb-2`** | ovh-node-2 |
| `KEY_API_ARTCB_DOPPLER_3` | `ARTCB NODE 3` | **`artcb3`** | aws-node-3 |

`artcb-2/dev` et `artcb3/dev` : configs `dev` verrouillées (pas de `prd`).  
Écriture allowlist **200** (sans `DOPPLER_*` réservés, sans mot de passe console, sans Stripe/Bob).

Coffre dédié `artcb-ovh-node-1` : **toujours non créé**. OVH1 reste sur `artcb-blockchain`.

---

## C. OVH 2 — compte réel, pas de machine

`PYTHONPATH=src python3 scripts/ovh_api_inventory.py ovh-node-2`

- `/me` **200** : nic `vc491276-ovh`, email `vgac4237@gmail.com`, state `complete`
- `/cloud/project` **200** : **[]**
- instances : **[]**
- IP `152.228.144.34` = nœud 1 uniquement

Aucune VM créée (validation Public Cloud en attente, ordre utilisateur).

---

## D. AWS 3 — login console OK, compute interdit

AWS CLI v2.36.34 installé (`~/.local/bin/aws`). Profil `artcb-node-3`, région `eu-west-3`.

`aws login` (navigateur DISPLAY=:1) : IAM user sign-in compte `599128160879` / `node_artcb_3_agent`.  
Premier mot de passe **accepté** puis page `changepassword` (IAMUserChangePassword). Nouveau mot de passe local only.

Console Home **200** (us-east-2 puis EC2 eu-west-3). Probe IAM Security credentials + EC2 Instances :

| Action | Résultat |
|--------|----------|
| `iam:GetLoginProfile` | AccessDenied |
| `iam:ListAccessKeys` | AccessDenied — « no identity-based policy allows the action » |
| `iam:ListMFADevices` | AccessDenied |
| `ec2:DescribeInstanceStatus` | AccessDenied |
| AWS Health widget | pas de permission |
| `RunInstances` | **non tenté** (Describe déjà refusé) |

L’IAM n’a **que** `IAMUserChangePassword`. Impossible de créer une access key ni une instance depuis cet agent.

À faire **côté compte AWS (root / admin)** :

1. Attacher à `node_artcb_3_agent` : `AmazonEC2FullAccess` (ou policy eu-west-3 minimale) + `iam:CreateAccessKey`/`ListAccessKeys` sur lui-même.
2. Ou créer des access keys en root et les mettre en secret Cursor `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (pas dans le chat).
3. Relancer `PYTHONPATH=src python3 scripts/provision_aws_ec2.py --yes` puis `bash scripts/deploy_aws.sh IP BRANCH`.

---

## E. Code 171

| Fichier | Pourquoi |
|---------|----------|
| `src/artcb/node_registry.py` | slugs réels `artcb-2` / `artcb3` ; token env par nœud ; config `dev` |
| `src/artcb/live.py` | `resolve_doppler_token` / config par `ARTCB_NODE_ID` |
| `scripts/provision_doppler_node_projects.py` | bind projets existants + écriture allowlist |
| `scripts/provision_aws_ec2.py` | diagnostic STS/EC2 ; `--yes` seulement si EC2 autorisé |
| `scripts/deploy_aws.sh` | deploy SSH aws-node-3 (n’envoie pas OVH1) |
| `tests/test_e2e171_aws_doppler.py` | isolation slugs + pas de secrets |
| `docs/DOPPLER_NODE_ISOLATION.md` | mapping réel |
| D-029 amendé + **D-030** | IAM gate |

Tokenomics D-024…D-027 **inchangées**. V-01…V-07 **toujours ⏳**.

---

## F. Invariants 171

| ID | État |
|----|------|
| origin/main connu | PASS (`a71a6d3`) |
| live health HTTP+HTTPS | PASS **PROBE LIVE** |
| live SHA = origin/main | **FAIL** (5b4b24ae ≠ a71a6d3) |
| artcb-2 bound | PASS (écriture secrets OVH2) |
| artcb3 bound | PASS (IDs publics AWS, pas le mot de passe) |
| Stripe absent des coffres nœud | PASS |
| OVH2 sans VM | PASS |
| AWS EC2 lancée | **FAIL / volontaire** — IAM |
| 4 machines | **NON TESTÉ** |
| V-01…V-07 | **NON TESTÉ** |

---

## G. Certification

```
READY FOR NEXT TEST
NOT MAINNET CERTIFIED
```

Prochaines actions (ordre) :

1. Admin AWS : politiques EC2 + access keys (ou secrets Cursor). **Ne plus coller le mot de passe console dans le chat.**
2. Relancer `provision_aws_ec2.py --yes` + `deploy_aws.sh`.
3. OVH2 : attendre l’apparition Public Cloud, **puis** ordre explicite de VM.
4. `DOPPLER_PERSONAL_TOKEN` pour extraire OVH1 hors de `artcb-blockchain`.
5. Redéployer le nœud 1 sur `origin/main` **sur ordre explicite**.
