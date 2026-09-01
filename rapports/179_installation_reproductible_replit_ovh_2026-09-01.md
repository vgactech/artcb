# Rapport 179 — installation reproductible Replit / OVH et timeout PQC

Date : 2026-09-01  
Périmètre : dépôt ARTCB, Replit Autoscale, installation locale et OVH2/OVH4.  
Exclusion explicite : OVH1 `152.228.144.34` n'est pas modifié ni redéployé.

## Diagnostic

Le blocage observé n'était pas un défaut du protocole HTTP ni du port 5000.
Le chemin d'installation mélangeait plusieurs opérations lentes :

1. `pip install -r requirements.txt` incluait `liboqs-python`.
2. `liboqs-python` peut compiler liboqs depuis les sources avec CMake et GCC.
   Cette compilation peut dépasser dix minutes sur Replit.
3. Le démarrage pouvait aussi créer un venv, installer les paquets, compiler
   la bibliothèque C et construire le frontend avant que l'API soit réellement
   disponible.
4. Le script de synchronisation Git tentait un checkout sur un workspace
   contenant des modifications locales. Le checkout échouait et la release
   pouvait alors annoncer un SHA différent du code effectivement chargé.

Le log de boot confirme le second cas : `checkout` a été refusé parce que
`requirements.txt` était modifié localement. L'application a néanmoins démarré
ensuite sur le port 5000.

## Correctif durable

- `scripts/install_python_dependencies.sh` installe le socle API sans
  `liboqs-python`, vérifie les imports et applique des timeouts pip.
- `liboqs-python` reste dans l'inventaire complet `requirements.txt`, mais son
  installation est optionnelle et isolée :
  `ARTCB_INSTALL_PQC=1 ARTCB_PQC_TIMEOUT=300`.
- `pyproject.toml` classe liboqs-python dans l'extra `pqc`, afin que
  `pip install -e .` n'impose pas une compilation native au socle.
- `install.sh`, Docker, `start_api.sh`, Replit et OVH utilisent le chemin
  runtime commun.
- `npm ci` est utilisé quand `frontend/package-lock.json` existe.
- `scripts/verify_installation.sh` donne une preuve reproductible : imports
  API, versions crypto, build frontend et symbole C attendu.
- Le boot Replit conserve le snapshot et n'installe pas PQC par défaut.
  Le port et `/live` restent disponibles sans attendre CMake.
- La synchronisation Git refuse maintenant un checkout si le workspace est
  sale ; elle conserve le snapshot et le journalise au lieu de l'écraser.
- Les compilations natives liboqs Replit/OVH sont bornées par
  `ARTCB_PQC_TIMEOUT`, avec fallback Ed25519/X25519 si elles échouent.

## Commandes opérateur

### Replit — après un clone ou pour réparer les dépendances

```bash
cd /home/runner/workspace
ARTCB_INSTALL_PQC=0 bash scripts/install_python_dependencies.sh
bash scripts/verify_installation.sh
```

Ne pas lancer `pip install -r requirements.txt` directement dans le boot
Autoscale : cette commande inclut volontairement la dépendance source PQC.
Le workflow de publication reste :

```bash
bash scripts/replit_autoscale.sh
```

### Installation complète locale ou machine OVH

```bash
git clone https://github.com/vgactech/artcb.git
cd artcb
ARTCB_INSTALL_PQC=0 bash install.sh
bash scripts/verify_installation.sh
```

### Tentative PQC explicitement demandée

```bash
ARTCB_INSTALL_PQC=1 ARTCB_PQC_TIMEOUT=300 bash install.sh
bash scripts/verify_installation.sh
```

Un timeout PQC n'est pas un timeout de démarrage API. Il laisse le socle
installé et l'application utilisable avec le fallback autorisé par D-032.

### OVH2 / OVH4

Les scripts de déploiement installent les outils système, compilent liboqs de
façon bornée, puis exécutent `install.sh` avec le binding PQC optionnel :

```bash
bash scripts/deploy_ovh2.sh <IP_OVH2> <BRANCHE_CONTROLEE>
bash scripts/deploy_ovh4.sh <IP_OVH4> <BRANCHE_CONTROLEE>
```

Ne pas utiliser ces commandes avec `152.228.144.34`. Les scripts refusent
déjà cette IP pour OVH2/OVH4 ; OVH1 reste le témoin legacy conformément à
D-036.

## Protocoles conservés

- Architecture Git A : pas de `git reset --hard` flottant vers un tip.
- Pas de création automatique de wallet, seed, mot de passe ou passphrase.
- Aucun appel automatique à `POST /setup/init-node`.
- D-032 est conservé : ML-DSA-65 prioritaire quand disponible, Ed25519
  temporairement accepté jusqu'au 2026-12-31, fallback signalé par `/health`.
- `pqc.available` n'est pas présenté comme preuve d'un AND hybride global.
- TenSEAL simulé et absence de liboqs ne bloquent pas le bootstrap API.
- Aucun changement ni redéploiement d'OVH1.

## Preuves de validation

- Audit de dépendances : 0 critical, 0 high, 0 moderate, 0 low.
- Tests ciblés Replit/autostart : 25 passed.
- Build frontend TypeScript/Vite : réussi.
- Après redémarrage : `/live` 200, `/api/v1/health` 200,
  `/ready` 503 attendu sans identité de nœud.

## Action de maintenance

À chaque nouveau clone, utiliser `install.sh` ou
`scripts/install_python_dependencies.sh`, jamais une commande pip ad hoc.
Le rapport et l'autoprompt doivent rester associés aux scripts afin que le
prochain agent conserve la séparation runtime/PQC et les garde-fous de sécurité.