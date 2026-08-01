# Chunk Contract: WS-XINT-003-08R — Privileged Lifecycle Action Registration

## Status and risk

Non-implementable planning skeleton after 07. Refresh exact files and commands
on current main before an explicit user request. L1 privileged action catalogue.

## Goal

Register exactly four approved actions as planned and unavailable:
`review.revision_context.repair -> project.task.manage`,
`review.revision_obligation.close -> project.task.manage`,
`review.revision_context.legacy_close -> operations.reconcile.run`, and
`review.lifecycle.activation.manage -> operations.reconcile.run`.

## Allowed files

At current-main refresh, enumerate only AUTH catalogue/runtime resource types,
one then-current migration, authorization/migration tests, canonical AUTH/REV
docs, and initiative evidence.

## Not allowed

Action activation, routes, service commands, REV recovery/control behavior, new
PermissionIds, broad permission remapping, identities, or compatibility aliases.

## Acceptance criteria

- Exact ActionId enum, ActionDefinition owner/permission/planned availability,
  typed closed resource context, SQL evidence parity, and docs are added for
  only the four actions.
- Migration proves prior-head/fresh upgrade, single head, downgrade/re-upgrade,
  protected-evidence refusal, and no existing mapping/availability drift.
- Candidates match reviewed manifests: covered Project Manager for repair and
  obligation close; Operator for legacy close and lifecycle control.
- Static tests prove no route/command declares the actions and evaluation
  remains unavailable.

## Verification and reviewers

Catalogue/runtime/migration/direct-SQL parity and denial tests, Ruff, focused
90-percent coverage, hosted full suite; full L1 reviewer set.

## Stop

Merge and stop before 08A activation.
