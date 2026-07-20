# PR Trust Bundle: WS-CON-001-02A

## Chunk

`WS-CON-001-02A` - Shared Transactional Outbox Persistence.

## Goal

Land feature-neutral shared PostgreSQL outbox truth and a caller-transaction
append participant, with enough persistence shape for 02B to add dispatcher
mechanics without another migration.

Risk: L1 infrastructure/data boundary; SLA P1.

## Human-Approved Intent

The human explicitly started 02A after CON-01 merged. This chunk must remain
generic and authorization-neutral: AUTH owns every action, permission,
evaluator, service admission, and activation decision, while 02B and later
feature chunks own execution behavior.

## Why It Changed

REV-owned lifecycle transactions need one generic durable event participant
that can flush into the caller's transaction without publishing, committing,
or inheriting feature authority. No such shared persistence boundary existed on
trusted main.

## What Changed

- Added one linear `0029_shared_transactional_outbox` migration after the
  ART-owned `0028_artifact_admission` revision.
- Added the generic outbox model, strict append schemas, reservation repository,
  and flush-only service.
- Registered the model in shared SQLAlchemy metadata.
- Added PostgreSQL migration, concurrency, replay, privacy, custody, rollback,
  and state-shape tests.
- Updated the WS-CON chunk ledger and added exactly one schema-v2 merge intent
  naming 02B with a separate explicit start.

## Design Chosen

- Immutable event truth and mutable operational delivery state are separate.
- PostgreSQL, not the caller, owns producer, occurrence time, initial state,
  counters, and initial eligibility time.
- Event ID and global idempotency key are independent identities; exact replay
  requires every immutable fact to match.
- The repository inserts with conflict suppression, locks matching identities
  deterministically, and uses only the supplied `AsyncSession`.
- The service reuses the existing repository-wide `app.core.hashing` canonical
  JSON helper, takes one defensive deep payload snapshot before its first await,
  and emits only stable input, conflict, or persistence errors with detached
  payload-bearing validation/database exception contexts.
- Retention is one-way terminal archival; event truth cannot be deleted or
  truncated.
- No route, dispatcher, delivery executor, broker, Celery task, handler,
  authorization identifier, or product-domain mutation is present.

## Scope Control

The committed diff is limited to the reviewed 02A migration, outbox module,
metadata registration, focused tests, initiative evidence, and one merge
intent. The user-owned local PDF deletion is excluded. No 02B dispatcher work
or protected product behavior is included.

## Product Behavior

There is no new public or protected product surface. Existing review,
contribution, compensation, authorization, artifact, task, and project behavior
is unchanged; the new participant is infrastructure for later callers.

## Alternatives Rejected

- A new canonicalizer or generic idempotency framework.
- An outbox-owned session, commit, enqueue, publish, or post-commit repair.
- Event identity inferred only from the idempotency key.
- Mutable payload/envelope facts or physical retention deletion.
- A schema too small for 02B that would force a second delivery-state migration.
- Dispatcher authority inherited by protected feature handlers.

## Acceptance Criteria Proof

- Current PR #153 reconciliation: 43 passed, 32 deselected in 177.40 seconds
  on the exact bounded isolated outbox/migration row; outbox coverage is 95.73
  percent against the 90 percent subsystem floor.
- Current helper regression suite: 8 passed in 0.21 seconds. A Pydantic opaque
  mapping compatibility repair preserves fail-closed secret graph inspection.
- Current AUTH revision-specific lifecycle proof: 1 passed in 63.77 seconds,
  preserving AUTH's exact `0026` downgrade/reupgrade behavior independently of
  repository head.
- Alembic reports exactly one head at `0029_shared_transactional_outbox`, with
  parent `0028_artifact_admission`.
- The exact ART `0028` / CON `0029` bounded row passes 73 tests with 32
  deselected after the Proxy repair and 95.90 percent focused outbox coverage.
- REV-02A PR #156 is reconciled at trusted main `3b1d6379`; it changes planning
  contracts only and adds no migration, runtime outbox seam, or CON authority.
- The following `0027` rows are retained as historical pre-PR #153 evidence;
  they do not replace the current `0028` proof above or GitHub CI.
- Post-review exact bounded row: 43 passed, 30 deselected in 60.22 seconds,
  with 95.73% outbox coverage against the 90% subsystem floor.
- Reconciled exact contract selector: 8 passed, 56 deselected.
- Current-main outbox plus migration/lifecycle-guard suite: 36 passed in
  156.17 seconds; the reconciled outbox implementation retains 95.43% focused
  coverage.
- After ART-02B1 merged, the combined outbox/migration plus real-MinIO S3
  focused suite passed 76 tests in 243.28 seconds on the current tree.
- After AUTH-09D-B merged, the combined outbox/migration, real-MinIO S3, and
  identity-link lifecycle/concurrency suite passed 78 tests in 378.36 seconds.
- Affected AUTH lifecycle downgrade tests: 2 passed, including atomic rollback
  to the full `0027` head when AUTH refuses `0026 -> 0025`.
- Alembic historically reported exactly one head: `0027_shared_transactional_outbox`.
- Isolated database runner self-tests: 16 passed in 102.10 seconds with the
  required admin URL.
- Real API contract end-to-end on the `0027` chain: passed.
- Pre-reconciliation exact isolated PostgreSQL full suite: 1347 passed in 17741.96 seconds
  (4:55:41), with 85.35% repository coverage against the 78% floor.
- The pre-reconciliation isolated evidence records tree `f72bb6e`, database
  `workstream_test_d513fb2f03b1`, and the superseded Alembic head
  `0026_shared_transactional_outbox`; the superseded `0027` focused proof is
  retained above and GitHub CI must supply repository-wide proof after publication.
- Agent-loop gates: 88 passed after AUTH-09D-B.
- Ruff, 90.4% docstring coverage, Markdown links, stale Workstream/AUTH/ART/REV
  scans, and diff hygiene pass.
- AUTH-09D-A reconciliation historically moved the migration to `0027`; PR #153
  supersedes that revision with the current `0028` proof above, and GitHub CI
  must pass after publication.
- REV PLAN2 PR #150 then advanced trusted main to `983b9e53`. It changes only
  planning/specification files, preserves the 02A runtime boundary, and updates
  future CON/REV child gates. A two-hour suite on the prior head was stopped,
  discarded, and is not counted.
- ART-02B1 PR #151 then advanced trusted main to `1b5422fc`. It adds the real
  S3-compatible adapter, MinIO service, SDK pins, CI gates, and a substantial
  backend test delta without changing 02A code or migration. The 3-hour
  7-minute run on the prior tree was stopped and discarded.
- AUTH-09D-B PR #152 then advanced trusted main to `93dd3924`. It activates
  only identity-link revoke/reactivate and adds AUTH route/test coverage, with
  no migration or 02A boundary change. The one-hour run on the prior tree was
  stopped and discarded.
- Contributor-foundation PR #153 then advanced trusted main to `8d5eb15b`. It
  clean-cuts TaskAssignment/Submission attribution to canonical human
  `contributor_id`, adds writer revalidation, and owns `0027`. It changes no
  CON authority or outbox behavior; CON's migration is now the linear `0028`
  child. Fresh bounded proof and exact-SHA internal review supersede the older
  publication evidence, while the full suite remains GitHub CI-owned.
- A fourth local run on the frozen current head was stopped after approximately
  4 hours 15 minutes by human direction that repository-wide suites must run in
  GitHub CI. Its metadata was removed and it is not counted. The existing
  Backend full-suite job is the required exact-head repository proof.

## Tests And Checks Run

The exact isolated PostgreSQL selector covers migration custody, rollback,
replay, collision races, payload privacy, and delivery-state constraints. The
separate helper suite covers deep secret-retention assertions. Ruff, Alembic
head, Markdown links, stale-contract scans, agent-loop tests, docstrings, and
`git diff --check` also pass.

## Test Delta

No existing test was deleted, skipped, weakened, or rewritten to accept broken
behavior.

Internal-review repairs add regression proof for one detached Pydantic
core-schema boundary across model methods and `TypeAdapter`, valid Python/JSON/
string-mode parity, hostile top-level and nested dict/list/string subclasses,
payload-free outbox traceback locals including idempotency conflicts, nested
payload mutation while reservation is blocked, payload-free database failures,
and caller rollback after an injected post-reservation failure. The shared deep-
retention assertion now inspects dict/list/string subclasses and slotted
dataclass state without invoking the tested hostile overrides. The exact
documented focused command generates fresh coverage before enforcing the
subsystem floor.

## CI Integrity

No workflow, dependency, package script, test runner, lint/typecheck command,
coverage threshold, or CI configuration changed.

Repository-wide tests and the 78 percent repository coverage floor run only in
the existing GitHub Backend full-suite job. Local proof is bounded to focused
real-service tests, the 90 percent outbox coverage floor, Ruff, migrations, and
static gates. This changes execution location only: no test, assertion,
isolation control, or coverage threshold is waived.

## Reviewer Results

- Exact repair candidate `9be9c88a19c4301f2b7ac606b6782604a48472bb`
  passed senior engineering, QA/test, security/auth, product/ops,
  architecture, docs, reuse/dedup, test-delta, and CI-integrity review against
  trusted main `3b1d63796c086f53fc2b0aeefe096387b82485ec` with no open findings and no
  open reviewer sessions.
- The pre-PR #153 implementation passed all nine tracks at historical code SHA
  `460573287270965d730c83f5f1e52f3acf1c0671`.
- That historical review is superseded by the current exact-SHA result above.

## External Review

CodeRabbit review `8be695bd-33ce-4847-8bf1-905a130804ec` posted five actionable
documentation-consistency threads. The repair adds explicit reviewer tracks,
aligns AUTH counts, defines REV parent/child aliases, fixes REV-13C release
ownership, and fixes the REV-04B prerequisite. Its physical-purge suggestion is
deferred to separately started 02B because 02A forbids retention behavior and
its custody contract prohibits physical delete/truncate. GitHub Backend remains
in progress; external review does not replace internal review.

## Remaining Risks

- GitHub still must prove the full backend suite and repository-wide 78 percent
  coverage floor on the published exact head.
- The Pydantic string-mode wrapper supports the model's fixed strict/default
  contract; arbitrary per-call runtime option overrides are not a 02A API.
- Dispatcher mechanics, service authority, and recovery remain excluded and
  require a separately started 02B chunk.
- Sustained-volume archival/retention behavior remains a reviewed 02B concern;
  no trigger-disable purge path is introduced into immutable 02A event truth.

## Human Review Focus

1. Is the immutable/operational schema complete for migration-free 02B without
   implementing dispatcher behavior early?
2. Do global idempotency and event-ID collisions fail closed under concurrent
   commit and rollback orders?
3. Are payload bounds and secret-key rejection sufficient for a generic event
   envelope?
4. Do database custody, archival, and guarded downgrade preserve durable event
   truth?
5. Does append remain entirely inside the caller-owned transaction with no AUTH
   or product-domain boundary expansion?

## Follow-Up Work

The same-initiative successor is `WS-CON-001-02B`, Shared Outbox Dispatcher And
Recovery. It requires a separate explicit start after this PR merges and after
its AUTH/service prerequisites refresh from trusted main.

## Human Merge Ownership

Only the human owner may approve and merge the specific 02A PR. Passing
reviewers, CI, or CodeRabbit do not authorize merge or the next chunk.
