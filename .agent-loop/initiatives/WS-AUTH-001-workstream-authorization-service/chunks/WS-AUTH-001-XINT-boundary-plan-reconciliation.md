# Chunk Contract: WS-AUTH-001-XINT — Lifecycle Boundary Plan Reconciliation

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Reconcile the remaining AUTH plan with merged PR #139 and the canonical
`WS-XINT-001` AUTH/ART/REV/CON handoffs before any affected runtime work
continues.

## Why this chunk exists

The cross-initiative reconciliation changed the meaning of `ActionOwner`,
replaced the combined project-role model, required a prepared mutation
protocol, and made fixed-service admission a prerequisite rather than feature
authority. The existing AUTH plan reflects parts of those decisions but does
not yet provide complete, executable chunk custody.

## Risk class

L1 planning and security-contract correction.

## SLA

P1. Stop all affected AUTH runtime work until this boundary reconciliation is
reviewed and merged.

## Allowed files

```text
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-XINT.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
docs/spec_authorization_service.md
docs/operations_authorization_service.md
```

## Not allowed

```text
backend runtime, migration, schema, route, background-service, or test implementation
ActionId or PermissionId registration
ActionOwner or ActionAvailability runtime changes
service provisioning or feature action activation
editing immutable historical migrations or archived reference specifications
starting AUTH-09B, ART, REV, CON, or POL runtime work
resolving PR #132 by restoring pre-XINT planning text
```

## Acceptance criteria

- The plan records PR #139 and treats all four merged XINT handoffs as
  authoritative inputs.
- PR #132's seven fixed identities, eleven static matrix actions, and migration
  `0023` remain valid. Convergence must preserve its packaged frozen migration
  contract, zero mutable `app.modules` imports from the migration, explicit
  Alembic-script-owned repository root, location-independent built-wheel
  custody/replay proof, same-event-loop CLI execution and engine disposal, and
  original `BaseException` precedence with cancellation/cleanup tests. Its
  planning conflicts are assigned to a separate exact-main convergence and
  re-review step.
- `ActionOwner` means only an exact AUTH activation custodian. All 25 current
  ART and 19 current REV mappings have explicit availability-neutral transfer
  chunks and exact future AUTH activation chunks.
- The four proposed REV actions and the ART review-evidence binding action stay
  unregistered until their owning features publish complete typed contracts;
  their registration and activation are separate gates.
- AUTH gains a bounded prepared-mutation foundation before project and review
  mutations consume it.
- AUTH-10 cleanly removes current `both` and replacement evidence from typed
  and PostgreSQL validation without rewriting historical migrations or silently
  converting rows.
- AUTH-10 through AUTH-16 state role-specific invalidation, wrong-grant denial,
  idempotency, migration, conformance, and fixed-service proof exactly.
- Every future implementation chunk names one merge-intent file, required
  reviewers, deterministic proof, and a stop condition.
- The amendment changes no runtime and declares no automatic successor start.

## Verification commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup

## Human review focus

Review whether authority custody, transaction ownership, service identity,
project-role independence, migration order, and downstream activation gates are
complete without moving ART, REV, or CON behavior into AUTH.

## Stop conditions

Stop if reconciliation requires inventing a foreign-domain resource contract,
activating a feature action, changing runtime, or overwriting the merged XINT
contract to preserve older AUTH wording.
