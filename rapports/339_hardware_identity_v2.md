# R339 — Hardware Identity v2 + parallel OPEN live

**UTC:** 2026-09-13T20:55:00Z  
**CERTIFIED_100:** false

## Corrections retenues (audit opérateur)

- Ne pas exiger tous les IDs : inventaire → classification → empreinte → NodeKey → certificat.
- Fingerprint ≠ attestation ; 100 IDs ≠ TPM.
- SSD/MAC/RAM = secondaires ; motherboard change → revalidation.
- H0–H4 ; H1 autorisation limitée ; H2 = external + binding ; H3/H4 = RoT natif attesté.
- `UNSUPPORTED_HARDWARE` (C04 natif) ≠ `NODE_UNAUTHORIZED`.
- APPLE_T2 / APPLE_SE distincts de TPM ; jamais inventer.
- Clé SSH-like (Ed25519) + challenge ; privée jamais réseau.
- OS reinstall sans RoT → recovery ceremony.

## Mesure Mac (ce tour)

| Champ | Valeur |
| --- | --- |
| model | MacBookAir7,1 |
| assurance_h | H1 |
| native_c04 | UNSUPPORTED_HARDWARE |
| rot_kind | NONE |
| fingerprint_v2_16 | 8dc65fe353a2b6f4 |
| c04_pass | false |

Artefacts: `logs/R339/mac_inventory.json`, `enrollment_bundle.json`, `docs/ARTCB_HARDWARE_IDENTITY_V2.md`.

## Live parallèle (ouverts non abandonnés)

| Item | Verdict |
| --- | --- |
| SHA ×4 | `9724811b06beabe867763ea8c7f7adb7545dae52` |
| Public tip ×4 | equal index **1177** hash `d428d7cc…` |
| C2-D / fanout | PASS (logs/R339/c2d.json) |
| #86 org_body_multinode | **NOT_PROVEN_acl_session** |
| #86 tips_equal / auto_vc / pollution | PASS partiel (r331) |
| Anti-Sybil | sample_count=**45** ; quantity_gate_50=false ; campaign_certified=false |
| #77 N04 | not_proven (:22 CLOSED) |
| #77 C04 this Mac | UNSUPPORTED_HARDWARE (honest) |

Ingest: full prompt archived ; new_only mémo block **1177** (295 chars signals) ; short 175 earlier block 1175.

## Livré code

- `src/artcb/platform/mac_hardware_inventory.py`
- `scripts/artcb_r339_mac_hardware_enrollment.py`
- `tests/test_r339_mac_hardware_inventory.py`
- Rules `RT-HW-H1`, `RT-HW-BINDING`
- Fix import `artcb.rules` for PYTHONPATH=src

## Encore OPEN (continuer parallèle)

1. NodeCertificate CA + registry challenge API  
2. H2 FIDO/external binding  
3. #86 ACL org body multi-node  
4. #77 N04 when SSH ; C04 on capable hardware  
5. Anti-Sybil ≥50 samples then stats (not auto-certify)  
6. Telemetry engine depth ; Genesis private ; langage IA ; V-01…V-07 ; #87 order  

Jamais wipe. Jamais software→C04 PASS.
