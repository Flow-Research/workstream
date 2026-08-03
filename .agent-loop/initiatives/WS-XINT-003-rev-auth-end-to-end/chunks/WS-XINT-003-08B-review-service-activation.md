# Chunk Contract: WS-XINT-003-08B — Review Service And Lifecycle Control Activation

## Status and risk

Non-implementable parent skeleton after 08A. Split into current-main children
aligned to exact REV-11C, REV-12P2, and REV-12A4 behavior; never implement this
combined parent. L1 fixed-service and release-control authority.

## Goal

Activate the single `review.reconcile.run` ActionId once for both separately
admitted authority-invalidation and general reconciliation identities, plus
`review.artifact_reference.reconcile`, `review.projection.rebuild`, and
reason-bound `review.lifecycle.activation.manage`.

## Allowed files

Each child enumerates only exact AUTH evaluator/availability parity and
integrated tests/docs/evidence. REV jobs/controller and Celery implementation
are read-only dependencies.

## Not allowed

New contexts/protocols/principals, REV job/controller behavior, catch-all
service, human authority in payloads, prepared-handle serialization,
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
- 02C/02D registration, principal, contract, and denial proof is already merged.
  Each child adds no ActionId, PermissionId, principal, context class, protocol,
  REV lifecycle behavior, or product route.

## Verification and reviewers

Service-command/matrix/retry/control tests, coverage and hosted gates; architecture,
security, product/ops, QA, senior, CI, reuse, docs, test-delta.

## Stop

Merge and stop before end-to-end conformance/release.
