# ARTCB ORG / KYB Specification v1 (R343)

**Status:** SPEC + scaffold — **CERTIFIED_100=false** · **BETA**  
**UTC:** 2026-09-14T16:55:00Z

## Separation

```text
HumanIdentity / KYC   ≠   OrgIdentity / KYB
ORG_CREATED ≠ ORG_VALIDATED ≠ ORG_REWARD_ELIGIBLE
```

Creator **cannot** self-validate. Validators subject to `ValidatorConflictOfInterest`.

## Status machine

| Status | Meaning |
| --- | --- |
| ORG_CREATED | genesis created |
| KYB_PENDING | dossier submitted |
| KYB_IN_REVIEW | validator(s) reviewing |
| KYB_MORE_INFO | extra docs requested |
| KYB_APPROVED | dossier accepted |
| ORG_ACTIVE | operational |
| ORG_SUSPENDED | suspended |
| ORG_REVOKED | validation withdrawn |
| ORG_EXPIRED | renewal required |

## Document catalog (versioned, jurisdiction policy)

- Existence: registry extract, registration number, legal form, seat
- Tax: TAX_ID / TAX_REGISTRATION / TAX_STATUS_PROOF (not universal “tax notice”)
- Directors / legal representatives
- **UBO** (Ultimate Beneficial Owners) — required
- Address proofs when required
- `bank_account_proof` vs `bank_account_destination` (IBAN etc.)

**Never put raw KYB documents on the public chain** — private encrypted store + hash/commitment only (extends OrgGenesis public_commitment).

## Objects (to implement)

`OrgApplication`, `DocumentRequirement`, `DocumentSubmission`, `ValidatorAssignment`,
`ValidatorDecision`, `RiskAssessment`, `ConflictCheck`, `OrgValidation`

## Reward gate

```text
ORG_VALIDATED (+ policy) → reward eligibility
else → economic rewards blocked (internal use may remain)
```
