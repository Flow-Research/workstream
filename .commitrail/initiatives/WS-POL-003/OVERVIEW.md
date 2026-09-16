# WS-POL-003 — Unified project-guide compilation

Latest completed POL behavior: [POL-07B checker phase service](WS-POL-003-07B.md),
building on [POL-07A pre-submit attempt recovery](WS-POL-003-07A.md),
building on [POL-06B public post-policy review](WS-POL-003-06B.md),
building on [POL-06A post-policy custody](WS-POL-003-06A.md),
building on [POL-05B public manager operations](WS-POL-003-05B.md),
building on [POL-05A proposal custody](WS-POL-003-05A.md),
building on [POL-04B2 guide document intake](WS-POL-003-04B2.md),
building on [POL-04B live unified setup](WS-POL-003-04B.md).
Current remaining design: [POL plan](planning/PLAN.md) and the
[cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: automatic unified execution, deterministic projections,
  immutable setup finalization, current-authority replay and one public guide
  creation/document-upload flow; hidden complete-proposal review, pre-submission
  approval custody and correction successors; public exact manager review,
  pre-submission approval and manual dispatch through the same runtime; automatic
  post-policy derivation, public complete policy read, separate approval and correction;
  ART-owned pre-submit reservation and completed evidence recovery without rerunning checks;
  one internal command per phase and removal of the standalone JSON precheck.
  Production post-submit phase execution remains unavailable.
- Intent: compile one locked guide and its policies into authoritative,
  versioned project behavior without circular subsystem authority.
- Next usable boundary: remaining ARCH-03B queues and actor-specific projections
  after completed ARCH-03B1 detached metadata and CP08 lineage
  and minimal writers and ARCH-03A internal guide context, following completed CP07 activation/binding and
  [AUTH-12H live authority](../WS-AUTH-001/WS-AUTH-001-12H.md). POL-07B consumes the completed POL-07A
  ART attempt prerequisite and ARCH-04A value contracts. POL-06B public
  policy review and automatic derivation use completed
  [AUTH-12G authority](../WS-AUTH-001/WS-AUTH-001-12G.md). POL-05B connects manager review, pre-submit
  approval and manual correction dispatch to AUTH-12F4 and POL-05A.
  Live setup consumes the [consolidated catalogue](../WS-ARCH-001/WS-ARCH-001-04A.md)
  and completed AUTH-12B2.
  Earlier development schemas require no backward-compatibility paths.
  The existing ReviewPolicy boolean is delivered; automated acceptance remains unavailable.
- Governing sources: project-guide specifications, authorization and
  contribution-policy specifications, code, migrations, and tests.
- Preserve: trusted policy compilation, explicit ownership, atomic persistence,
  no public activation route or default live-authority composition, and no concrete
  adapter leakage.

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

POL-05/06 and AUTH-12F4/12G deliver public proposal and post-policy visibility,
separate approvals and shared corrections. Automatic derivation and recovery
consume committed upstream approvals while finalized setup remains immutable.

1. CP06 validation and CP07 hidden complete-guide activation/binding are delivered. AUTH-12H now authorizes CP07's hidden command without a
   Task/CheckerRun dependency. POL-07B supplies the internal phase service;
   ARCH-04C alone owns later durable post-submit persistence.
   Remove obsolete owner code in each replacement chunk; no compatibility or
   deferred duplicate implementation is permitted.
