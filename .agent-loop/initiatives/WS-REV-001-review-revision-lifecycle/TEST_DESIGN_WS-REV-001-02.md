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

## 02A1 Project/setup publication fence

- Exhaustive writer inventory proves every Project Guide/setup mutation locks
  Project first, then the declared row types and same-type IDs in stable order.
- Locked reads refresh ORM identity-map state and revalidate draft ownership
  before mutation.
- Agent/provider work happens outside locks; persistence rolls back the read
  phase and reacquires the full fence.
- Post-commit enqueue bookkeeping uses the fenced setup-run participant rather
  than direct mutation; the setup job remains a service-only caller.
- The exact 18-row writer inventory in the 02A1 contract is the race matrix;
  every row races with activation in both Project-lock acquisition orders and
  observes a PostgreSQL wait. A separate structural test fails if any current or
  newly discovered writer bypasses the shared fence.
- Setup-run ID-only commands use an authority-free project projection, lock
  Project first, refresh the graph, and revalidate project/guide ownership.
- Activation-first, writer-first, insert-only create-guide, competing activation,
  readiness-denial, post-commit delegation, and remote-output assertions match
  the exact matrix contract; no partial or stale graph commits.

## 02A3 guide activation chronology

### Migration/data

- Number active/superseded guides independently per project by effective time,
  created time, then ID; drafts remain null.
- Fail on malformed/missing/non-human approver, invalid status/provenance/time
  order, more than one active guide, or identical effective/created ordering
  facts within a Project, with bounded redacted diagnostics and no partial DDL.
- Prove prior-head preflight, one head, upgrade, safe downgrade/re-upgrade,
  dependency/protected-row downgrade refusal, and failure rollback on real
  PostgreSQL without dropping AUTH's shared human-reference function.

### Direct SQL and service

- Reject nonpositive/duplicate/mutable sequence and invalid
  draft/active/superseded provenance shapes.
- Activation changes only lifecycle allocation/update-time fields. Afterward,
  reject every activated-row change including ID, project/version, content,
  summary, creator/creation time, sequence, approver, and effective facts.
  Permit only status/superseded/update-time changes during the
  database-timestamped active-to-superseded transition, then reject every change
  or clear.
- Reject service approver and prove active-human profile/link revalidation in
  both lifecycle race orders. Suspension, terminal deactivation, and link
  revocation each prove both orders plus exact Projects-owned 403/503 envelopes.
- Public pre-service service-token, already suspended/deactivated, already
  revoked, identity-verifier unavailable, and actor-registry unavailable paths
  retain their exact AUTH-owned envelopes and never enter ProjectService.
- Transaction-race tests first resolve a valid ActorContext, then force the
  lifecycle transition before or after the ProjectService actor lock. Only the
  post-resolution revalidation failure uses the Projects envelope. Direct
  non-human service misuse is tested separately from the public route.
- First activations serialize and allocate distinct monotonic sequences using
  one post-lock database timestamp.
- Draft activation succeeds; sole-active repeat is explicit additive no-write
  idempotency; superseded candidate remains denied.

## 02A4 Task guide triplet and screening

- Backfill non-draft Task only from an exact same-Project guide/version with
  valid chronology; reject polluted drafts and zero/multiple legacy matches.
- Direct SQL rejects partial, crossed, cross-Project, nonpositive, changed, or
  cleared Task triplets through the exact composite FK/check/trigger.
- Screening uses unlocked ID/project projection, then Project -> refreshed Task
  -> refreshed active Guide locks before graph validation and stamping.
- Screening audit contains the complete triplet; audit fault rolls back status,
  guide, policy, and payment stamps.
- Activation/screening races observe PostgreSQL lock waits in both commit orders
  and never commit a mixed triplet.

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
