# Optional Artifact Projection Handoff: WS-CON-001

## Status

Deferred and not approved for implementation. Merged WS-XINT-001 D7 and
`REV_CON_HANDOFF.md` supersede the earlier mandatory contribution-evidence
design.

## Core boundary

Core Review/ContributionRecord creation has no synchronous or asynchronous ART
prerequisite. REV supplies the stabilized versioned Submission/packet artifact
digest through locked canonical facts. CON copies that value into
`ContributionRecord.artifact_hash` and does not load, verify, rehash, bind, or
project artifact bytes.

ART outage or integrity uncertainty may block a Review only where REV's own
stabilized packet contract requires it before judgment. Once REV supplies the
canonical decision facts, CON does not call ART and cannot translate storage
failure into `needs_revision`, `reject`, a missing contribution, or a missing
award.

## Optional future projection

A deterministic contribution-evidence document may be proposed later as a
post-commit asynchronous projection. If approved:

- projection status and failure lifecycle remain separate from Review,
  ContributionRecord, CompensationAward, CompensationFulfillmentReceipt, and
  CompensationStatusProjection truth;
- CON owns deterministic document semantics and the projection relation only;
- ART owns preparation, scratch, admission, provider execution, verification,
  binding, receipts, recovery, retention, and provider abstraction;
- AUTH owns the exact optional action, fixed service admission, evaluator, and
  activation;
- PostgreSQL remains canonical; the artifact is an export, not source truth;
- storage failure is retryable projection failure and never a product rollback.

## Required fresh approval

CON-09A/09B cannot start from this planning document alone. A future chunk must
refresh and internally review:

- the then-current ArtifactStore v2/admission/verification/recovery contracts;
- one named ART write capability and, independently, any read capability;
- exact document schema, media type, retention, disclosure, and replay rules;
- one separately registered optional binding ActionId mapped to the stable
  `artifact.binding.create` PermissionId;
- exact extension of the existing `workstream.artifact.binding` static service
  row, controlled provisioning, AUTH-09E admission, and activation sequence;
- cancellation, commitment drift, idempotency, provider ambiguity, cleanup
  custody, and cross-project disclosure proof.

PR #129 supplies only inactive committed-source preparation. It does not
approve a contribution-evidence port, admission, provider execution,
verification, binding, read, or retention contract.

## Prohibited coupling

- No evidence row/event in CON-07.
- No CON-09A/09B prerequisite for CON-10A/B or CON-11.
- No ART prerequisite in the core chunk dependency order or joint live drill.
- No raw ArtifactStore, scratch manager, prepared/committed source, provider
  reference, path, credential, or ART repository crossing into CON.
- No optional evidence action counted as a core WS-CON action.
- No storage outcome mutating canonical contribution or award truth.

This handoff changes no runtime and starts no optional projection work.
