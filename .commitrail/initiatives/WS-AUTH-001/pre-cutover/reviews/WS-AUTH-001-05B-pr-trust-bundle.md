# WS-AUTH-001-05B PR Trust Bundle

## Chunk

`WS-AUTH-001-05B` - Authority Idempotency And Invalidation Foundation

## Goal

Make the ten sensitive authority mutations concurrency-safe and retry-safe,
with typed replay results and exactly linked success/invalidation evidence.

## Human-Approved Intent

The human approved the repaired L1 contract and its semantic chunk boundary.
The work remains backend foundation only; AUTH-06 must not start automatically.

## What Changed

- Migration `0019` adds immutable actor-scoped idempotency reservations, a
  pending-to-committed transition, typed replay references, database timestamps,
  a deferred pending guard, and guarded downgrade custody.
- Strict frozen request variants cover exactly ten mutation operations and hash
  only canonical, bounded, server-derived facts.
- The authorization service reserves, replays, records privacy-neutral
  mismatches, validates concrete success evidence, constructs invalidations,
  and completes the claim in one caller-owned transaction.
- PostgreSQL links actor, claim, operation, entity, resource, target, concrete
  cause, request, correlation, and project context and closes committed records
  to later evidence.
- Behavior tests cover all ten operations plus project-grant replacement,
  exact and mismatched concurrency, rollback, privacy, direct bypasses,
  immutable state, and upgrade/downgrade races.

## Why It Changed

Later actor, grant, and permission chunks need a trustworthy retry boundary.
Without it, a lost response or concurrent retry could duplicate authority
state, disclose another request's result, or leave misleading audit evidence.

## Design Chosen

The unique namespace is actor kind, actor reference, operation, and client key.
Only the canonical request digest and typed response reference persist. The
existing shared audit service remains the sole application writer, while
PostgreSQL independently enforces linkage and immutability. Repositories never
commit, roll back, retry, or create sessions.

## Alternatives Rejected

- Storing raw requests or response bodies was rejected for privacy and schema
  stability.
- Application-only idempotency and evidence validation was rejected because
  direct SQL must fail closed.
- A parallel invalidation table was rejected because AUTH-05A already owns the
  shared authority evidence envelope.
- Route, grant, actor, cache, queue, and consumer implementation remains in
  later owning chunks.

## Scope Control

No API route, permission evaluator, actor/grant table, token verifier, cache,
queue, invalidation consumer, product authorization decision, dependency,
workflow, or CI threshold changed.

## Product Behavior

There is no new externally reachable product behavior. Internal callers can
claim a mutation, receive an exact committed replay, or receive a private
mismatch signal. Completion requires one concrete success plus one linked
invalidation event.

## Acceptance Criteria Proof

- Independent concurrent retries serialize through PostgreSQL and produce one
  committed result and one evidence pair.
- All ten operations and the project replacement branch have positive typed and
  database-linked proof.
- Request target/project facts are bound to the success, response, and replay;
  cross-actor, wrong-entity, wrong-target, and mismatched-cause paths fail.
- Committed rows reject new success or invalidation evidence and reject update,
  delete, and truncate.
- Rejected secrets and malformed Unicode are absent from strings, args,
  diagnostics, public state, cause, and context.
- Downgrade is observed waiting for an actual PostgreSQL writer lock, refuses
  non-empty custody, preserves compatible pre-0019 rows, and restores head.

## Tests And Checks Run

- Focused behavior/migration suite: 26 passed.
- Authorization subsystem coverage: 96.88 percent.
- Isolated-runner suite: 16 passed.
- Ruff, 95.3 percent docstring coverage, stale contract scans, changed Markdown
  links, internal review evidence structure, and diff integrity passed or are
  rerun after this bundle is finalized.
- A local repository-wide isolated suite reached approximately 94 percent with
  no failure before intentional interruption after two hours on an overloaded
  four-core host. GitHub Backend owns the authoritative full-suite and global
  coverage result.

## Test Delta

Tests are additive or strengthened. Existing audit assertions were adapted for
mandatory idempotency linkage, and positive operation coverage replaced weaker
assertions. No raises guard, skip, xfail, coverage threshold, or test selection
was removed or weakened.

## CI Integrity

No workflow, dependency, package script, exclusion, or coverage setting
changed. GitHub Backend must still enforce the repository-wide 78 percent floor
and the existing artifact-foundation 90 percent floor.

## Reviewer Results

Exact runtime SHA `e0838908dfa19227fab2f73e32c9b0c94dd39bb4` passed senior
engineering, architecture, product/ops, docs, reuse/dedup, QA/test, test delta,
CI integrity, and security/auth/privacy review with no remaining findings.

## External Review

Pending GitHub checks, CodeRabbit, and human review.

## Remaining Risks

- Database-owner or DDL credentials can bypass normal-DML triggers; production
  must use the documented non-owner runtime role.
- This chunk emits invalidation evidence but intentionally has no consumer.
- Replay references are internal; future routes must reload and reauthorize the
  current resource before disclosure.

## Follow-Up Work

After merge, post-merge memory, stop, and a separate human start, AUTH-06 may
implement canonical actor profiles and identity links. Later chunks own the
authorization kernel, grants, resource cutovers, and invalidation consumers.

## Human Review Focus

Review the migration triggers and downgrade lock ordering, canonical digest
boundary, request-to-evidence binding, mismatch privacy, and proof that no
route or product authorization behavior entered scope.

## Human Merge Ownership

Only the human may approve and merge this PR. Internal or external checks do
not authorize merge.
