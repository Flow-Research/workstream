# WS-POL-003 — Unified project-guide compilation

Latest completed POL behavior: [POL-04B2 guide document intake](WS-POL-003-04B2.md),
building on [POL-04B live unified setup](WS-POL-003-04B.md).
Current remaining design: [POL plan](planning/PLAN.md) and the
[cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: automatic unified execution, deterministic projections,
  immutable setup finalization, current-authority replay and one public guide
  creation/document-upload flow.
- Intent: compile one locked guide and its policies into authoritative,
  versioned project behavior without circular subsystem authority.
- Next usable boundary: POL-05A builds hidden complete-proposal review, correction and pre-policy approval custody, followed by AUTH-12F4 and POL-05B approval/manual rerun.
  Live setup consumes the [consolidated catalogue](../WS-ARCH-001/WS-ARCH-001-04A.md)
  and completed AUTH-12B2.
  Earlier development schemas require no backward-compatibility paths.
  The existing ReviewPolicy boolean is delivered; automated acceptance remains unavailable.
- Governing sources: project-guide specifications, authorization and
  contribution-policy specifications, code, migrations, and tests.
- Preserve: trusted policy compilation, explicit ownership, atomic persistence,
  no hidden activation, and no concrete adapter leakage.

## Delivered

- Strict unified catalogue, one guide-agent adapter, authorized immutable
  compilation persistence and bounded recovery classifications, hidden execution, and deterministic
  sufficiency/artifact-policy projections are complete through 04A3.
- POL-04A2 atomically binds those exact projections to an immutable finalization
  receipt and closes the current setup generation. AUTH-12B2 supplies the exact
  concrete adapter; POL-04B explicitly composes it in the automatic worker.
  Default composition and public finalization routes remain unavailable.

- POL-04B1 binds automatic source-ready requests to committed source consent
  and current setup-service authority. Human and service replay hold current
  authority through receipt classification.
- POL-04B runs one automatic compilation when ART commits all assigned originals, using an
  immutable runtime/model/instructions snapshot and scoped on-demand document
  access. Original bytes stay in ArtifactStore; extracted bodies are not stored
  in PostgreSQL. It replaces all three earlier
  inference methods and stops at findings and draft pre/post proposals. Unknown
  provider outcomes are visible and cannot trigger a second invocation.

## Remaining v0.1 sequence

The existing guide-bound ReviewPolicy now persists and exposes strict
`human_review_required`, default `true`, in its immutable semantics/hash.
See the [delivered implementation](../../changes/pre-review-plan-reconciliation.md#delivered-policy-setting-implementation)
and preserved [bounded handoff](../../changes/pre-review-plan-reconciliation.md#product-builder-handoff-implement-the-setting-next).
Configured `false` remains available in draft but cannot activate a guide until
the authorized automated FinalAcceptance/CON path is proven and available.
Existing tasks retain their locked rules; adjudication is not included.

1. POL-05/06 complete proposal visibility, setup-wide correction, approval and
   post-submit manifests with AUTH-12F4/12G. Immutable
   finalized setup rows require separately reviewed downstream custody before
   live post-submit integration.
2. POL-07 facade consumes independent ARCH-04A registered-capability proof;
   ARCH-04C alone owns durable post-submit persistence. AUTH-12H activates
   CP07's hidden complete guide command without a Task/CheckerRun dependency.
   Remove obsolete owner code in each replacement chunk; no compatibility or
   deferred duplicate implementation is permitted.
