# WS-AUTH-001-05A PR Trust Bundle

## Chunk

`WS-AUTH-001-05A` - Shared Audit Ownership And Append-Only Authority Evidence

## Goal

Add one typed, privacy-bounded, append-only authority evidence envelope to the
existing shared `audit_events` path without changing legacy task/checker
behavior or activating authorization decisions.

## Human-Approved Intent

The human approved AUTH-05A as one semantic chunk bounded by its allowed files,
non-goals, acceptance criteria, behavior evidence, and required reviews rather
than an arbitrary production-line ceiling. AUTH-05B remains separate.

## What Changed

- Migration `0018` extends the shared audit table with versioned authority
  fields, closed registries, cross-field constraints, database-owned time,
  authority-cause integrity, and append-only normal-DML triggers.
- A typed authority input and shared audit service enforce the same event,
  reason, fact, reference, permission, denial, role, and project matrices.
- Task repository compatibility methods delegate to `AuditRepository` while
  preserving caller session and transaction ownership.
- Behavior tests cover all 20 authority events through typed and direct-SQL
  positive and negative paths, legacy compatibility, rollback, mutation
  custody, non-retention, and migration downgrade guards.

## Why It Changed

Later authorization chunks require trustworthy evidence custody before actor,
grant, permission evaluation, route cutover, idempotency, or invalidation
consumers can be implemented.

## Design Chosen

The existing audit table remains the sole store. Application writes use one
typed service and shared repository. PostgreSQL independently enforces the
closed envelope so direct SQL cannot bypass privacy or integrity rules.
Rejected mappings and JSON are inspected from one stable snapshot, and service
re-admission never serializes untrusted mutated values before validation.

## Alternatives Rejected

- A parallel authority event table was rejected because it would split audit
  custody and duplicate writer behavior.
- Application-only validation was rejected because direct SQL must enforce the
  same boundary.
- Splitting typed and SQL matrices into mergeable partial states was rejected
  because either half alone is an incomplete security boundary.
- AUTH-05B idempotency/replay work remains deferred to its own chunk.

## Scope Control

No route, dependency, middleware, permission evaluator, actor/grant lifecycle,
authorization cutover, idempotency record/replay path, invalidation consumer,
token verifier, workflow, dependency, or CI threshold was added or changed.

## Product Behavior

Legacy audit behavior and task/checker projections remain unchanged. New
authority evidence is internal foundation behavior only; it does not grant,
revoke, authorize, route, or invalidate product actions.

## Acceptance Criteria Proof

- All 20 registered events share typed and PostgreSQL positive/negative cases.
- System and project grant scopes, project/resource equality, UUID references,
  registered tokens, denial codes, cause domain, self-cause, and append-only
  custody have direct behavior proof.
- Malformed, scalar, duplicate-key, hostile mapping, mutable-buffer, secret
  representation, and post-validation mutation cases retain no rejected value
  and emit no serializer warning.
- Legacy rows survive upgrade/downgrade proof and existing repository behavior.

## Tests And Checks Run

- Exact migration proof: 1 passed.
- Audit suite: 10 passed.
- Audit plus delegation coverage: 11 passed at 94.55 percent.
- Two affected task lifecycle regressions passed.
- Ruff, 95.1 percent docstring coverage, test-delta, migration line length,
  stale wording/auth/artifact, Markdown links, and diff integrity passed.
- Full local repository tests were intentionally not repeated; GitHub Backend
  CI owns the full suite and repository-wide 78 percent coverage floor.

## Test Delta

Tests were added or strengthened only. No assertion, raises guard, skip, xfail,
coverage threshold, or exclusion was removed or weakened.

## CI Integrity

No workflow, package, dependency, coverage configuration, or test selection
file changed. GitHub checks must pass before merge.

## Reviewer Results

Exact SHA `ea16fd8bd2d9bc38b37c12003e51416c08a56678` passed senior engineering,
architecture, reuse/dedup, docs, product/ops, QA/test, CI integrity, test delta,
and security/auth review with no remaining findings.

## External Review

CodeRabbit run `30676bdc-7525-4deb-8f9e-a87d42c64f92` produced four
actionable comments. The response replaces positional reason mapping with
explicit event keys, types the task audit cleanup session, makes the inactive
AUTH-05B verification block executable, and records AUTH-05A-specific reviewer
references. Internal QA additionally aligned the full-suite example with
Backend CI by running isolation-runner self-tests outside the isolated suite.
The generic CodeRabbit docstring warning is not applicable because the
repository's configured docstring gate passes at 95.1 percent. GitHub Backend
CI remains the final full-suite gate.

## Remaining Risks

- PostgreSQL append-only triggers protect normal DML, not database-owner or DDL
  credentials; production must use the documented non-owner runtime role.
- The full repository suite and global coverage floor remain GitHub CI gates.
- AUTH-05A records evidence but intentionally does not consume invalidations or
  perform authorization.

## Follow-Up Work

After merge, post-merge memory, and a separate human start, AUTH-05B may add the
idempotency and invalidation foundation. Later chunks own actor profiles,
grants, permission evaluation, and route cutover.

## Human Review Focus

Review the migration constraints and downgrade ordering, typed/SQL matrix
parity, single-snapshot privacy boundary, shared writer transaction ownership,
and proof that no authorization behavior was activated.

## Human Merge Ownership

Only the human may approve and merge this PR. Completion of internal or
external review does not authorize merge.
