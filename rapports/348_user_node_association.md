# R348 — USER↔NODE (audit + scaffold)

**UTC:** 2026-09-14T17:50:00Z  
**Référence R347 :** inchangée · **R345 :** untouched  
**CERTIFIED_100:** false · **UNIQUE_HUMAN:** false

## Audit croisé

`/wallet/create` + `HumanRegistry` + `NodeIdentity` + `device_wallet_limit` :

- Create wallet = DEVICE_CLIENT only  
- HumanRegistry = présent, non requis pour R348  
- NodeIdentity = contexte challenge  
- device_wallet_limit = **non** utilisé par l’API User↔Node  

## Livré

- Spec `docs/ARTCB_USER_NODE_ASSOCIATION_V1.md`  
- Core `user_node_association.py` (I5 forbid privkey)  
- Routes HTTP challenge / associate / status  
- Tests unitaires  

## Non livré (volontaire)

- R349 USER↔WALLET  
- UNIQUE_HUMAN  
- Preuve live multi-nœud de l’association  
- Modification de R345
