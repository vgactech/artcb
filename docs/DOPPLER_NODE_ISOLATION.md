# Isolation Doppler par nœud réel ARTCB

**Règle :** un projet Doppler par compte cloud / nœud réel.  
Le projet `artcb-blockchain` reste le coffre **partagé** (Stripe, Bob, GitHub, LLM).  
Il ne doit plus recevoir les clés OVH-2 ni AWS-3.

| node_id | Affichage | Doppler | Compte | Compute |
|---------|-----------|---------|--------|---------|
| `ovh-node-1` | node artcb 1 | `artcb-ovh-node-1` | compte OVH historique (clés Cursor/Doppler actuelles **CK expirée**) | `152.228.144.34` GRA11 — **existe** |
| `ovh-node-2` | node artcb 2 | `artcb-ovh-node-2` | nic `vc491276-ovh` (`vgac4237@gmail.com`) | **aucun** projet Public Cloud / VPS / IP au moment de l’inventaire 170 |
| `aws-node-3` | node artcb 3 | `artcb-aws-node-3` | AWS `599128160879` IAM `node_artcb_3_agent` | **aucun** — CLI `aws login` nécessite un navigateur |

## Création

Le token Cursor `artcb-node-1` est un **service token** : lecture/écriture de `artcb-blockchain/dev` seulement. `POST /v3/projects` → **403**.

```bash
# Token personnel Doppler (jamais dans git ni dans le chat)
export DOPPLER_PERSONAL_TOKEN=...
PYTHONPATH=src python3 scripts/provision_doppler_node_projects.py
```

Puis un **service token distinct** par projet (L-036) : Cursor, nœud 1, nœud 2, AWS.

## Secrets

- OVH 1 : `OVH_*` + `SSH_PRIVATE_KEY` + `ARTCB_API_KEY` du nœud 1 → `artcb-ovh-node-1`
- OVH 2 : clés « Agent-Autonome node artcb 2 » → `artcb-ovh-node-2` uniquement
- AWS 3 : access keys IAM (pas le mot de passe console) → `artcb-aws-node-3`
- Staging local agent : `~/.artcb/nodes/<node_id>.env` mode `0600` — **hors git**

Variable d’aiguillage : `ARTCB_NODE_ID=ovh-node-1|ovh-node-2|aws-node-3`

## Ce que 170 ne fait pas

- Ne crée **pas** de VM OVH ni d’instance AWS (aucun nœud 2/3 à déployer tant que le compute n’existe pas).
- Ne mélange **pas** Stripe/Bob dans un projet nœud.
- Ne redéploie **pas** `main` sur `:34` sans ordre explicite.
