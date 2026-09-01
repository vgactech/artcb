# Rapport 181 — Installation reproductible après clone et compilation C

**Date :** 2026-09-01  
**Dépôt :** `vgactech/artcb`  
**Commit de départ vérifié :** `af33b58` — `rapport conversation 180`  
**Mode :** DEBUG, sandbox Replit, sans wallet/seed/passphrase généré  
**Périmètre :** installation runtime, boot Autoscale, bibliothèque C, tests et build frontend  

## 1. Objectif

Reprendre le dépôt conformément à `PROTOCOLE_ARTCB`, `AUTO_PROMPT_ARTCB` et
`docs/PROMPT_REPLIT_AGENT_187.md`, en supprimant les blocages d'installation
observés après un clone :

- ne pas compiler `liboqs-python` dans le chemin critique ;
- ne pas forcer une compilation NumPy incompatible avec Python 3.13 ;
- ne pas dépendre de `python -m pip` quand le Python Nix est séparé de pip ;
- conserver les paquets dans un espace inscriptible hors `/nix/store` ;
- compiler la bibliothèque C avec les flags injectés par Nix ;
- garder Replit Autoscale sans clone GitHub, `unshallow` ou création de venv.

Le `ARTCB_REPLIT_PIN_SHA` fourni par l'opérateur (`e6ad…`) doit rester dans
Replit Secrets. Il n'est pas copié dans `.replit` et n'est pas utilisé comme
une clé de checkout.

## 2. Diagnostic avant

### 2.1 Installation Python

La première exécution :

```text
ARTCB_INSTALL_PQC=0 bash scripts/install_python_dependencies.sh
```

a échoué parce que le Python enveloppé Nix ne contenait pas le module `pip`.
Le fallback `pip3` existait pourtant dans le PATH.

Après ajout du fallback pip, l'installation a démarré mais a été interrompue
à 180 secondes pendant la construction source de `numpy-1.26.4`. La contrainte
`numpy<2.0` n'avait pas de wheel adaptée à Python 3.13.

### 2.2 Bibliothèque C

`make chain` a d'abord échoué sur `openssl/evp.h`, puis après activation des
dépendances système sur :

```text
undefined reference to `main'
undefined reference to `EVP_MD_CTX_new'
```

La cause était double :

1. `LDFLAGS ?= -shared -lcrypto` était neutralisé par les `LDFLAGS` injectés
   par l'environnement ;
2. `CFLAGS ?= ... -fPIC` était neutralisé de la même manière.

## 3. Modifications appliquées

### 3.1 `requirements.txt`

**Avant :**

```text
numpy>=1.24.0,<2.0
```

**Après, lignes 53–55 et 78–79 :**

```text
numpy>=1.24.0,<2.0; python_version < "3.12"
numpy>=2.0.0; python_version >= "3.12"
```

Python 3.11 conserve la série NumPy 1.x ; Python 3.12+ peut prendre une wheel
NumPy 2.x au lieu de compiler NumPy depuis les sources.

### 3.2 `scripts/install_python_dependencies.sh`

**Avant, lignes 35–36 :**

```text
PIP_TIMEOUT="${ARTCB_PIP_TIMEOUT:-180}"
...
run_bounded "$PIP_TIMEOUT" "$PYTHON" -m pip install
```

**Après, lignes 35–53 et 98–103 :**

- détection de `python -m pip` ;
- fallback contrôlé vers `ARTCB_PIP`, `pip3`, puis `pip` ;
- vérification que la version Python de pip correspond à l'interpréteur choisi ;
- usage de `${PIP_COMMAND[@]}` pour l'installation runtime et PQC ;
- installation dans le site utilisateur si le `purelib` Python est sous
  `/nix/store`, sans écrire dans `/nix/store`.

`liboqs-python` reste exclu du socle et uniquement activable par :

```bash
ARTCB_INSTALL_PQC=1 ARTCB_PQC_TIMEOUT=300 \
  bash scripts/install_python_dependencies.sh
```

### 3.3 `scripts/replit_autoscale.sh`

**Avant :** chemins figés Python 3.11 et 3.12.  
**Après, lignes 55–59 :**

```bash
for d in \
  "$REPL_DIR"/.pythonlibs/lib/python*/site-packages \
  "$HOME"/.pythonlibs/lib/python*/site-packages; do
```

Le boot trouve ainsi aussi Python 3.13 sans créer de venv.

### 3.4 `src/c/Makefile`

**Avant :**

```make
CFLAGS ?= -Wall -Wextra -O2 -fPIC
LDFLAGS ?= -shared -lcrypto
...
$(CC) $(CFLAGS) $(SRC) -o $(TARGET) $(LDFLAGS)
```

**Après, lignes 2–4 et 14 :**

```make
CFLAGS ?=
CFLAGS += -Wall -Wextra -O2 -fPIC
LDFLAGS ?=
LDLIBS ?= -lcrypto
...
$(CC) $(CFLAGS) $(LDFLAGS) -shared $(SRC) -o $(TARGET) $(LDLIBS)
```

Les flags externes restent conservés, les options obligatoires sont ajoutées,
et `-lcrypto` arrive après les sources.

## 4. Exécutions et logs

Chaque exécution a été journalisée puis relue conformément au protocole :

| Exécution | Résultat |
|---|---|
| `logs/20260901_runtime_install.log` | Échec initial : Python/pip indisponible |
| `logs/20260901_runtime_install_after_fix.log` | Timeout NumPy source à 180 s |
| `logs/20260901_runtime_install_numpy_markers.log` | **Succès**, runtime installé, PQC ignoré |
| `logs/20260901_verify_installation_after_node.log` | **Succès**, API import + `npm ci` + build frontend |
| `logs/20260901_make_chain_after_openssl.log` | Échec headers OpenSSL avant activation système |
| `logs/20260901_make_chain_after_makefile_fix.log` | Échec flags link |
| `logs/20260901_make_chain_after_cflags_fix.log` | **Succès**, `libartcb_chain.so` compilée |
| `logs/20260901_pytest_replit_economics_final.log` | **68/68 PASS** ciblés |
| `logs/20260901_pytest_full.log` | **679 PASS, 22 skipped, 3 failures** |

La vérification frontend a produit un build Vite réussi :

```text
✓ 122 modules transformed.
✓ built in 6.41s
```

## 5. Tests complets — écarts explicitement conservés

Les trois échecs ne sont pas masqués :

1. `tests/test_e2e169_secure_live.py::test_api_key_list_and_revoke_require_session`
   reçoit `503 bootstrap` lorsque le clone n'a aucune identité de nœud.
2. `tests/test_e2e169_secure_live.py::test_expired_key_rejected` reçoit aussi
   `503 bootstrap` dans le même contexte.
3. `tests/test_p2p_api.py::test_p2p_status` attend `ML-KEM-768`, alors que
   liboqs n'est volontairement pas installé dans ce chemin et que le nœud
   annonce honnêtement le fallback `X25519-fallback`.

Ces résultats sont cohérents avec `docs/PROMPT_REPLIT_AGENT_187.md` :
le bootstrap doit rester sans identité et l'installation PQC ne doit pas
bloquer l'API. Ils ne constituent pas une régression des quatre fichiers
modifiés. Une passe ultérieure peut isoler les tests « nœud configuré » et
paramétrer l'attente crypto selon la capacité réellement disponible.

## 6. État avant / après

| Élément | Avant | Après |
|---|---|---|
| Installation runtime | pip non résolu puis NumPy compilé jusqu'au timeout | **Succès**, NumPy 2.5.2 wheel Python 3.13 |
| PQC au boot | Risque de compilation dans le chemin critique | **Exclu**, fallback explicite |
| Site Python Nix | tentative possible vers `/nix/store` | site utilisateur `.pythonlibs` |
| Python Replit | chemins 3.11/3.12 figés | glob Python 3.x |
| C ABI | `make chain` bloqué par flags externes | `libartcb_chain.so` compilée |
| Frontend | non vérifié dans ce clone | `npm ci` + Vite build **OK** |
| Tests ciblés | bibliothèque C absente | **68/68 PASS** |
| Tests complets | non exécutés | **679 PASS / 22 skip / 3 écarts documentés** |
| OVH1 / wallets / init-node | inchangés | inchangés |

## 7. Consignes de publication Replit

Configuration déjà présente dans `.replit` :

```toml
run = "bash scripts/replit_autoscale.sh"
[deployment]
run = ["bash", "scripts/replit_autoscale.sh"]
deploymentTarget = "autoscale"
```

Conserver le pin fourni dans le Secret Replit :

```text
ARTCB_REPLIT_PIN_SHA=e6ad5d714792523565bb7386c2823a156d703874
```

Après publication, vérifier uniquement :

```bash
curl -sS https://artcb--vgac42.replit.app/live
curl -sS https://artcb--vgac42.replit.app/api/v1/health
curl -sS -o /dev/null -w "%{http_code}" \
  https://artcb--vgac42.replit.app/api/v1/wallet/list
```

Ne pas lancer `init-node`, ne pas créer de wallet automatiquement, ne pas
compiler liboqs au boot et ne pas redéployer OVH1.

## 8. Conclusion

Le blocage de compilation persistant avait trois causes indépendantes :
résolution de pip, NumPy sans wheel pour Python 3.13 et flags C écrasés par
Nix. Les trois chemins sont maintenant traités dans le dépôt, avec une
validation d'installation réussie, une bibliothèque C compilée et 68 tests
ciblés passants. Les trois écarts de la suite complète restent visibles et
expliqués plutôt que transformés en faux succès.