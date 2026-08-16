# Chunk Contract: WS-ARCH-001-CP04B — Hidden ContributionPolicy Publication

## Goal

Implement hidden publish and retire behavior using CP04A's public API,
operation/recovery custody, and opaque authorization port. Keep all policy
actions unavailable and add no route or downstream product behavior.

## Preconditions, risk and outcome

- CP04A is merged and current-main discovery is replayed.
- Risk: L1.
- Outcome: `complete` when the implementation PR merges; CP05 becomes next.

## Allowed files

```text
backend/app/modules/contributions/api/**
backend/app/modules/contributions/{models.py,repository.py,service.py}
backend/app/adapters/contributions/**
backend/alembic/versions/<next-current-head-policy-lifecycle-migration>.py (only if schema proof requires correction)
backend/alembic/env.py (head parity only if migration exists)
backend/tests/contributions/**
backend/tests/architecture/** (exact boundary proof only)
backend/tests/test_alembic.py (only with migration)
backend/scripts/{behavior_ownership.py,run_test_lanes.py} (exact parity only)
.ci/behavior-ownership/** (exact CP04B targets only)
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json (generated parity; no new debt)
docs/{architecture_data_model.md,roadmap_status.md,spec_contribution_compensation.md}
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/{CHUNK_MAP.md,STATUS.md,DISCOVERY.md}
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/{CHUNK_MAP.md,STATUS.md,AUTHORIZATION_HANDOFF.md}
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP04B-con-policy-publication-behavior.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP04B-*.md
```

## Not allowed

```text
AUTH activation/evaluator/grant/catalogue changes
public routes, ProjectGuide/TASK/Submission/REV mutations
ContributionRecord, CompensationAward creation, fulfillment, callback, delivery or reputation behavior
caller-supplied publication truth, compatibility paths, service commits or serialized PREP handles
```

## Publish contract

- Fence operation recovery before product locks or AUTH.
- Lock exact aggregate, draft version, both rules, definitions, referenced
  project units, and adapter bindings through the CP04A public owner ports;
  retain all owner fences through publication.
- Require a complete graph and active same-project units/bindings with exact
  instrument alignment.
- Recompute canonical rules/definitions digest and sorted unique binding ids
  from locked rows; require exact equality with typed AUTH facts.
- Consume and close PREP before changing version/policy state.
- Publish the version and make it current atomically. If another version is
  currently published, retire that prior version in the same transaction with
  exact actor/time attribution before installing the new current version.
  Prior content and every downstream frozen reference remain immutable.
- Serialize same-project publication so the one-active-policy race has a
  deterministic winner before AUTH consumption.

## Retire contract

- Target only the aggregate's exact current published version.
- Lock and verify expected state before AUTH; consume/close PREP, then retire
  policy and version with exact actor/time attribution and one immutable event.
- Block future guide selection without rewriting any guide, task, assignment,
  Submission, ReviewLease, ContributionRecord, or award history.
- A retired aggregate is terminal. A later policy requires a new aggregate and
  normal draft/publish flow; no compatibility resurrection path exists.

## Acceptance criteria

- [ ] Publish/retire remain hidden and production deny-default.
- [ ] Publish facts equal digest/binding facts recomputed from locked rows.
- [ ] Concurrent child mutation, binding suspension, unit retirement,
  competing publication, revocation, replay, cross-project use, wrong session/
  transaction, close failure, and rollback fail closed without mutation.
- [ ] Replacement publication retires exactly the prior current version while
  preserving its content and frozen downstream references; aggregate retirement
  is terminal.
- [ ] Exact duplicate recovery requires current read authorization and creates
  no new evidence/effect.
- [ ] PostgreSQL rejects immutable graph mutation, lifecycle skips, forged
  attribution/events, event mutation/deletion/truncation, and incomplete publish.
- [ ] No new file reaches 500 lines; one primary behavior per test; no frozen
  debt growth; focused coverage remains at least 90%.
- [ ] CP05 alone becomes the next activation boundary.

## Verification and reviewers

Use CP04A's boundary/state commands plus focused publication, retirement,
concurrency, PostgreSQL guard, and recovery tests. Hosted CI owns complete lanes
and aggregate coverage. Required reviewers: architecture, security/auth,
product/operations, QA, test-delta, CI integrity, senior engineering,
reuse/dedup, and documentation.

## Human review focus and stop conditions

Confirm server-owned publication truth, complete lock order, PREP-before-effect,
immutable history, and no activation/downstream behavior. Stop and amend if a
new action, permission, lifecycle state, foreign write, or compatibility path
is required.
