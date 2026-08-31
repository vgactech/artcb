# Isolation Doppler par nœud réel ARTCB

**Règle :** un projet Doppler par compte cloud / nœud réel.  
Le projet `artcb-blockchain` reste le coffre **partagé** (Stripe, Bob, GitHub, LLM).  
Il ne doit plus recevoir les clés OVH-2 ni AWS-3.

| node_id | Affichage | Doppler (slug réel 171) | Token Cursor | Compute |
|---------|-----------|-------------------------|--------------|---------|
| `ovh-node-1` | node artcb 1 | `artcb-blockchain` (coffre dédié `artcb-ovh-node-1` **non créé** — token service `artcb-node-1`) | `DOPPLER_TOKEN` | `152.228.144.34` GRA11 — **existe** |
| `ovh-node-2` | node artcb 2 | **`artcb-2`** | `KEY_API_ARTCB_DOPPLER_2` | nic `vc491276-ovh` — **aucun** Public Cloud / VPS / IP (validation OVH en cours) |
| `aws-node-3` | node artcb 3 | **`artcb3`** | `KEY_API_ARTCB_DOPPLER_3` | AWS `599128160879` IAM `node_artcb_3_agent` — EC2 `eu-west-3` (aliases Cursor `AWS_API_KEY_AGENT_3`) |

Les slugs 170 (`artcb-ovh-node-2`, `artcb-aws-node-3`) n’existent pas : l’utilisateur a créé `artcb-2` et `artcb3` dans l’UI Doppler. Le registre suit la réalité.

## Création / binding

`POST /v3/projects` avec un service token → **403**. Les projets 2 et 3 existent déjà :

```bash
PYTHONPATH=src python3 scripts/provision_doppler_node_projects.py
# lie artcb-2 et artcb3, écrit les secrets allowlist, refuse Stripe/Bob
```

Coffre dédié OVH1 : `DOPPLER_PERSONAL_TOKEN` (personnel) toujours requis.

## Secrets

- OVH 2 : clés « Agent-Autonome node artcb 2 » → `artcb-2` / `dev` uniquement
- AWS 3 : identifiants publics + **access keys** (pas le mot de passe console) → `artcb3` / `dev`
- Staging local : `~/.artcb/nodes/<node_id>.env` mode `0600` — **hors git**
- Mot de passe console AWS : **local only**, jamais Doppler / git / chat

Aiguillage : `ARTCB_NODE_ID=ovh-node-1|ovh-node-2|aws-node-3`

## AWS — IAM élargi (172)

Session suivante 2026-08-31 : politiques `AdministratorAccess` + `AmazonEC2FullAccess` + `IAMFullAccess` + `IAMUserChangePassword`.  
Secrets Cursor `AWS_API_KEY_AGENT_3` / `AWS_API_CLI_AGENT_3` (pas les noms standard). STS + Describe* **OK**.

```bash
PYTHONPATH=src python3 scripts/provision_aws_ec2.py --yes
bash scripts/deploy_aws.sh IP BRANCH
PYTHONPATH=src python3 scripts/run_sim172_aws_ec2.py --yes
```

Le mot de passe console n’entre **pas** dans Doppler / git / chat.

## Ce que 172 ne fait pas

- Ne crée **pas** de VM OVH 2 (compte sans Public Cloud — validation en cours).
- Ne redéploie **pas** `main` sur `:34` sans ordre explicite.
- Ne mélange **pas** Stripe/Bob dans `artcb-2` / `artcb3`.
- Ne certifie **pas** 4 nœuds WAN ni V-01…V-07.
