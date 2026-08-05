# WS-CON-001-02C PR Trust Bundle

## Chunk

`WS-CON-001-02C` — Shared Lifecycle Audit Participant.

## Goal

Provide the flush-only, caller-transaction audit participant required by future
REV and CON lifecycle transactions without creating a second ledger or taking
commit ownership.

## Human-approved intent

Workstream must record bounded canonical lifecycle evidence in the same
transaction as the product facts it describes. This chunk supplies that shared
boundary only; it does not implement review, contribution, compensation, or
outbox lifecycle behavior.

## What changed

- Added closed canonical REV/CON lifecycle event, entity, reason, and reference
  types.
- Enforced exact event-to-entity and event-to-reference contracts, including
  FinalAcceptance, reviewer/submitter contribution, and award lineage.
- Added `LifecycleAuditParticipant` over the existing `audit_events` ledger and
  caller-owned `AsyncSession`.
- Added exact replay handling and changed-replay conflict behavior serialized by
  a transaction-scoped PostgreSQL advisory lock.
- Reserved fixed internal provenance and blocked generic-repository bypass.
- Added rollback, privacy, replay, concurrency, vocabulary-completeness, and
  lineage tests.
- Reconciled 02C status and evidence with current main, REV-03A2, and migration
  head `0056_review_lease_preference`.

## Why it changed

Future REV decision and CON contribution/award transactions need audit evidence
to succeed or roll back atomically with their domain rows. The previous generic
repository path accepted unbounded compatibility shapes and did not define deterministic
concurrent replay behavior.

## Design chosen

The participant reuses the existing lifecycle-compatible `audit_events`
representation. Its persisted discriminator remains `legacy_lifecycle`, but
that compatibility token is not exposed as the interface name or product
boundary. Callers can supply only typed canonical facts. It flushes through the
caller's session and never commits or creates a session. Exact event-ID replay
returns the existing immutable row; changed reuse raises a non-leaking
`LifecycleAuditConflict`. A transaction-scoped advisory lock serializes the
read/insert decision for that event ID.

Nested `project_id` is provenance evidence only. Authorization and filtering
must reload the canonical entity chain rather than trusting audit payload data.

## Alternatives rejected

- A second lifecycle audit table or event domain: duplicate ledger authority.
- Participant-owned sessions or commits: breaks atomic REV/CON transactions.
- Arbitrary event names or metadata: permits semantic and privacy drift.
- Unique-constraint failure as replay behavior: leaks a storage concern and is
  nondeterministic for callers.
- Authorization-link events in this participant: canonical authority decisions
  remain owned by the typed authority audit boundary.

## Scope control

Changed runtime scope is limited to:

- `backend/app/modules/audit/{schemas,repository,service}.py`
- `backend/tests/test_audit.py`
- the exact shared-audit architecture note and WS-CON-001 loop evidence

No model, migration, route, background executor, feature service, dependency,
workflow, CI threshold, outbox dispatcher, review command, contribution
persistence, compensation fulfillment, or reputation behavior changed.

## Product behavior

No user-facing lifecycle is activated. The shared contract distinguishes
`accept`, `needs_revision`, and `reject`; only acceptance evidence may reference
FinalAcceptance. Reviewer and submitter contribution evidence use distinct exact
source shapes. Generic or ambiguous contribution events are not admitted.

## Acceptance criteria proof

- Caller rollback removes staged lifecycle evidence.
- The participant flushes without commit and opens no independent session.
- Event vocabulary and primary-entity mappings are complete and closed.
- Event references are exact; unrelated lineage is rejected.
- Exact replay succeeds and changed replay fails closed.
- Concurrent replay waits on the exact event advisory lock.
- Generic repository bypass and forged secret-bearing input are rejected.
- The existing append-only ledger remains the only audit store.

## Tests and checks run

- 39 isolated PostgreSQL audit tests passed before final main reconciliation.
- 26 focused lifecycle tests passed again after reconciliation with current
  main and migration `0056`.
- 11 schema-only lifecycle input tests passed.
- Audit subsystem coverage: 94.64 percent; required minimum: 90 percent.
- Four focused replay/concurrency tests passed after lifecycle fixture cleanup.
- Ruff, Markdown links, stale Workstream wording, stale authorization docs, and
  diff integrity passed.

## Test delta

Lifecycle audit tests were added; no existing test was removed, skipped,
weakened, or rewritten to accept broken behavior. Test cleanup now removes all
audit rows created by the fixture, including lifecycle compatibility rows.

## CI integrity

No workflow, lane, runner, dependency, package script, coverage threshold, or
branch-protection behavior changed. Final hosted results pass:

- Agent Gates
- Backend `shared_foundations`
- Backend `schema_contracts_a`
- Backend `schema_contracts_b`
- Backend `project_lifecycle`
- Backend `task_lifecycle`
- merged Backend `test`

## Reviewer results

Senior engineering, QA, security, product/ops, architecture, docs,
reuse/dedup, and test-delta tracks passed after valid findings were fixed. See
`WS-CON-001-02C-internal-review-evidence.md`.

## External review

CodeRabbit passes. Actionable findings were addressed: concurrent replay is
atomic, committed lifecycle fixtures are cleaned up, the waiter assertion is
bound to the exact event lock, coverage evidence is precise, and initiative
status wording is current.

## Remaining risks

- The participant uses fixed internal values in compatibility provenance columns;
  future audit-schema cleanup may replace that compatibility representation.
- New lifecycle event tokens require an adopted feature contract, exact primary
  entity, exact source references, and contract tests.
- REV/CON readers must not use nested audit `project_id` as authorization truth.

## Follow-up work

After human merge, stop. REV-04B may consume this interface and merge after 02C.
CON-03C contribution/award persistence begins only under a separate explicit
instruction and after its REV-owned FK prerequisites exist.

## Human review focus

- Is caller transaction ownership preserved with no hidden commit path?
- Are accepted, revision, contribution, and award lineage shapes exact?
- Does concurrent event-ID replay deterministically return or conflict?
- Is the shared audit module free of REV/CON feature-service coupling?

## Human merge ownership

- [x] Required internal reviewers passed.
- [x] Hosted CI and CodeRabbit passed.
- [x] Valid external findings were addressed.
- [ ] The user explicitly approves PR #277 for merge.
