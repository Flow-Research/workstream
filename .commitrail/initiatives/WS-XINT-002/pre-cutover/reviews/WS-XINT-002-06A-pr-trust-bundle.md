# PR Trust Bundle: WS-XINT-002-06A

## Goal

Activate exactly `artifact.pre_submit.checker_input.materialize` for
`workstream.artifact.materializer`, fail closed before private contributor
bytes reach inspection/scratch/checkers, and unblock ART-04C1 without activating
contributor submission authority.

## Design

- Reuse the existing opaque, process-local, single-use, transaction-bound PREP
  service and fixed-service identity matrix.
- Prepare before ZIP inspection using exact task, immutable assignment UUID,
  project/guide/snapshot, locked-policy, plan/catalogue, prepared-generation,
  archive, and storage-scheme facts.
- Consume the same handle after inspection with the server-computed canonical
  semantic-manifest hash, before scratch reservation or checker execution.
- Persist bounded authorization evidence with the full resource-context digest
  and project/prepared-generation coordinates.

## Scope

The catalogue changes one planned action to active `WS-XINT-002-06A` custody.
No new ActionId, PermissionId, service identity, migration, alternate evaluator,
serializable handle, public route, generic artifact read, durable admission,
Submission, post-submit checker, checker output, or review capability is added.

## Proof

- Catalogue/service tests prove the sole availability transition and fixed
  materializer identity.
- Real PREP tests prove exact preflight/final binding, transaction ownership,
  replay denial, cross-resource mismatch denial, and audit digest/coordinates.
- Materialization tests prove preparation denial precedes inspection, canonical
  manifest drift precedes final consumption/workspace, and final consumption
  precedes scratch/checker execution.
- No test, CI gate, coverage threshold, lint rule, or workflow was weakened.
- Local focused tests passed; hosted Backend and Agent Gates remain mandatory on
  the exact PR head.

## Delivery order

After this PR merges, ART may run 04C1 then 04C2. AUTH can concurrently resume
at 12F3. ART-04C1 owns production composition and the locked-current-assignment
revalidation immediately before PREP.

## Reviewer result

Architecture, security, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test-delta, and docs reviewers pass after all valid findings were
repaired. See `WS-XINT-002-06A-internal-review.md`.

## Human review focus

Review the two-stage ordering, exact fixed identity, complete scalar/final fact
binding, audit digest, single action activation, and the explicit ART-04C1
composition boundary. Human approval owns merge.
