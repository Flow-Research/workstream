# Test Design: WS-REV-001 Runtime Foundation And Revision Cutover

## Status

Planning-only. No backend test/fixture/migration is implemented until the exact
child dependency and separate human-start gates are satisfied.

## Dependency gate fixture

Every runtime child records and asserts:

- trusted-main SHA and one Alembic head;
- exact owner chunk IDs, merged PR/SHAs, migrations, typed contracts, and tests;
- canonical `contributor_id` on TaskAssignment/Submission with no retired
  contributor storage names;
- database-backed canonical-human ActorProfile constraints;
- preserved task/submission/checker regressions, especially
  `test_checker_caused_revision_resubmits_fixed_version_through_api`.

Missing evidence stops before REV generates a migration.

## 02A chronology and Task locking

### Migration/data

- Number active/superseded guides independently per project by effective time,
  created time, then ID; drafts remain null.
- Fail on missing activation provenance, unknown/inconsistent status, duplicate
  ordering/sequence facts, or ambiguous Task guide context with row-specific
  remediation and no partial DDL/data effects.
- Backfill non-draft Task only from an exact same-project guide/version/sequence.
- Prove prior-head preflight, one head, upgrade, safe downgrade/re-upgrade,
  protected-row downgrade refusal, and failure rollback on real PostgreSQL.

### Direct SQL

- Reject nonpositive/duplicate/mutable sequence.
- Enforce exact draft/active/superseded provenance shapes and canonical-human
  approver.
- Reject partial, crossed, cross-project, or valid-to-valid changed Task guide
  triplet.

### Concurrency/service

- Project-first publication and task screening run against activation, setup
  mutation, and setup-job completion in both commit orders.
- First activations serialize and allocate distinct monotonic sequences.
- Draft activation succeeds; sole-active repeat is no-write idempotent;
  superseded candidate remains denied in 02A.
- Screening audit contains complete triplet; audit fault rolls back stamp.
- No external I/O occurs while locks are held; timestamp is post-lock DB time.

## 02A2 hidden reactivation

- AUTH action remains unavailable while hidden behavior is built.
- Missing If-Match -> 428; stale/mismatched current active -> 412; no feature
  mutation/audit.
- Valid reactivation preserves original approver/effective time/sequence, clears
  only restored superseded time, supersedes expected current at DB time, and
  appends exact shared audit.
- Exact retry, delayed retry, two reactivations, activation/reactivation,
  authority loss, audit failure, and both commit orders leave one active guide.

## 02B policy and dormant lifecycle

- Approved positive preference/lease defaults are explicit and independent of
  `sla_hours`.
- Enforce capacity one, no self-review, exact decisions, blocking/advisory
  finding vocabulary, no second review, and immutable activated policy.
- Remove legacy auto-reject policy without creating Review/task terminal/
  assignment terminal/CON/audit/outbox effects.
- Add dormant accepted/rejected/cancelled and completed/blocked storage shapes
  but no service transition or reject FK.
- Unknown/inconsistent historical policy/status fails preflight with no partial
  migration.

## 02C Submission lineage

- Backfill exact responsible assignment using one inclusive historical interval;
  zero or multiple candidates fail without choosing current/latest.
- Enforce exact assignment contributor, same task, canonical human actor,
  immediate N-1 predecessor, one successor, and exact immutable guide context.
- Finalized identity/attribution/context/evidence is immutable. The only future
  digest exception is the separately owned set-once server-derived
  `artifact_hash`; overwrite/caller promotion fails.
- Concurrent initial creates yield exactly one v1; loser exact replay/conflict.
  They never yield v2.
- Concurrent creates against one human preparation head yield exactly one N+1;
  loser exact replay/conflict. Concurrent checker-remediation creates likewise
  yield one N+1 from the exact current CheckerRun state. The winner persists the
  server-derived `remediation_source_checker_run_id`; direct SQL cannot cross the
  source run's task/immediate predecessor or reuse it for a second N+1. Neither
  path yields N+2; that requires a later committed human Review/preparation or
  final needs-revision CheckerRun.

## Human Review preparation and distinct checker remediation

### Human preparation constraints

- Bind one root to the exact Review(needs_revision), project/task/prior
  Submission/source assignment.
- Reject accept/reject Review, crossed/duplicate source, duplicate prior
  Submission episode, mutable source, and service-as-human actor.
- A CheckerRun cannot be used as a RevisionContextPreparation root.
- Version 1 has neither source relation. After human prepared cutover, every N+1
  has exactly one of `revision_context_preparation_id` or
  `remediation_source_checker_run_id`; null/null and both-set rows fail migration,
  service creation, and direct SQL.

### Atomic creation

- Existing checker transaction remains CheckerRun -> Task needs_revision ->
  audit/outbox -> one commit using unchanged task context. Fault rolls back its
  state; no Review/finding/CON/preparation record exists.
- Human transaction in 10: immutable Review + reviewer CON operation -> initial
  preparation -> Task needs_revision -> audit/outbox -> one commit.
  Fault rolls back all review/contribution/revision effects.
- No contributor-readable human-review needs_revision state lacks a head; unsafe
  context creates a blocked head. Exact CheckerRun lineage distinguishes the
  separate checker path from rootless legacy human state.

### Path-specific behavior

- Human Review revision requires responses for unresolved blocking ReviewFindings,
  response evidence where policy requires it, later resolutions, and preferred
  prior-reviewer return.
- Checker remediation exposes only contributor-safe checker message/fix, keeps
  existing guide/task context, consumes no human revision limit/deadline, requires
  no fake ReviewFinding/response/resolution, and returns to open routing.

### Limits and deadline

- No test is locked until the human approves exact human Review round count,
  deadline anchor, and inclusive/exclusive boundary.
- Approved semantics exclude checker retries and freeze/use database time.
- Limit/deadline blocked head cannot use repair; exact D6 close only.
- Context invalid/revoked head may append one authorized repair successor.

### Legacy

- Prove exact CheckerRun + Submission + matching durable audit lineage remains a
  valid checker-remediation path and is never classified as legacy human state.
- Classify valid human Review root, valid checker remediation, ambiguous claimed
  human source, and truly rootless human legacy separately. Never fabricate Review.

## Release phase

- Checker allow_review and checker needs_revision routing share the
  allowed checker-completion phases through `revision_cutover_fenced`; both deny
  from `admission_fenced`.
- Human preparation is inseparable from leased review.decision completion and
  remains allowed only where that completion class is allowed.
- Phase tests prove static routes/AUTH memberships do not change, denied commands
  fail at the database fence, scheduler suspension is operational, and crash
  resume is forward-only.

## Per-child proof

Every child runs focused tests/Ruff, real-PostgreSQL isolated full suite at 78
percent, 90 percent changed-subsystem coverage, stale contract scans, Markdown
links, agent gates including merge intent/internal review evidence, and
`git diff --check`. No test is skipped or weakened to accommodate new schema.
