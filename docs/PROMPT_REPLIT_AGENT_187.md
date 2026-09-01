# PROMPT Replit 187 — installation runtime sans blocage de compilation

## Mission

Maintenir un démarrage ARTCB rapide et reproductible sur Replit Autoscale et
une installation complète reproductible sur les machines OVH autorisées.

## Règles non négociables

1. Ne jamais installer `liboqs-python` dans le chemin critique du boot.
2. Utiliser `bash scripts/install_python_dependencies.sh` pour le socle.
3. Le PQC est optionnel et borné :
   `ARTCB_INSTALL_PQC=1 ARTCB_PQC_TIMEOUT=300`.
4. En cas d'échec PQC, garder l'API active avec le fallback Ed25519/X25519
   et publier l'état réel dans `/health`.
5. Ne jamais lancer `POST /setup/init-node` automatiquement.
6. Ne jamais créer de wallet, seed, mot de passe ou passphrase automatiquement.
7. Préserver D-032, D-036, l'Architecture Git A, les tests V-R01 à V-R04 et
   l'identité de release.
8. Ne jamais modifier ni redéployer OVH1 `152.228.144.34`.
9. Si le workspace Git est modifié, conserver le snapshot et ne pas effectuer
   de checkout destructif.
10. Utiliser `npm ci` avec le lockfile frontend et vérifier le build.
11. Sur le Python Nix Replit marqué PEP 668, installer dans `.pythonlibs`
    via le script commun, jamais dans `/nix/store` et jamais avec un
    contournement manuel du firewall.

## Commandes de référence

```bash
ARTCB_INSTALL_PQC=0 bash scripts/install_python_dependencies.sh
bash scripts/verify_installation.sh
bash scripts/replit_autoscale.sh
```

Pour OVH2/OVH4 uniquement :

```bash
bash scripts/deploy_ovh2.sh <IP> <BRANCHE_CONTROLEE>
bash scripts/deploy_ovh4.sh <IP> <BRANCHE_CONTROLEE>
```

## Validation attendue

- `/live` = 200 rapidement.
- `/api/v1/health` = 200 en bootstrap.
- `/ready` = 503 avec `node_identity_missing` tant qu'aucune identité n'est
  configurée.
- Aucun clone GitHub ni `unshallow` pendant le boot Autoscale.
- Si le workspace est sale, le log doit dire `dirty_worktree — keeping
  snapshot; no checkout` et conserver le SHA réellement exécuté.
- Logs corrélés par `ARTCB_STARTUP_ID`.
- Vérifier `release_integrity` sans le confondre avec `pqc.available`.
- Exécuter les tests ciblés et le build frontend avant de déclarer terminé.