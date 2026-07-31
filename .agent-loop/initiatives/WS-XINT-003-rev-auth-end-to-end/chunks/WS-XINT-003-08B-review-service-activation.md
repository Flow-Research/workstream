# Chunk Contract: WS-XINT-003-08B — Review Service And Lifecycle Control Activation

## Status and risk

Non-implementable planning skeleton after 08A. Refresh exact files and commands
on current main before an explicit user request. Requires hidden REV
jobs/projection/control. L1 fixed-service and
release-control authority.

## Goal

Activate the single `review.reconcile.run` ActionId once for both separately
admitted authority-invalidation and general reconciliation identities, plus
`review.artifact_reference.reconcile`, `review.projection.rebuild`, and
reason-bound `review.lifecycle.activation.manage`.

## Allowed files

Enumerate exact REV jobs/controller, Celery command registration, AUTH identity/matrix
and Operator context, migrations, tests, docs, evidence at start.

## Not allowed

Catch-all service, human authority in payloads, prepared-handle serialization,
canonical truth in projections, provider-specific access in REV, or route
release before conformance.

## Acceptance criteria

- Each fixed service uses its admitted identity and closed action membership; general
  and invalidation reconciliation identities remain distinguishable.
- Jobs are batched, resumable, idempotent, and reauthorize each transaction.
- Projection/reconciliation never becomes canonical judgment and ART repair is
  delegated through exact typed ports.
- Lifecycle control requires an Operator, exact phase/preconditions/reason, and
  cannot bypass dependency readiness or drain/fence state.
- All-pairs denial, Celery payload/registration, crash/retry, and crossed
  controller/job tests pass.
- No lifecycle-control command exists until 08R registers its exact planned
  action with migration/catalogue parity.

## Verification and reviewers

Service-command/matrix/retry/control tests, coverage and hosted gates; architecture,
security, product/ops, QA, senior, CI, reuse, docs, test-delta.

## Stop

Merge and stop before end-to-end conformance/release.
