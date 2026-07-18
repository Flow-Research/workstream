# Chunk Contract: WS-REV-001-09A

## Goal

Implement controlled revision-context preparation, immutable responses and
response evidence, and guarded version N+1 resubmission without replay
resolution or return routing.

## Risk class

L1 policy, immutable history, and contributor fairness.

## Allowed files

```text
backend/app/modules/reviews/{repository,schemas,service,router}.py
backend/app/modules/reviews/task_revision_participant.py
backend/app/modules/tasks/{models,repository,service,lifecycle,submission_participant}.py
backend/app/modules/projects/{models,repository,service}.py only for approved current guide/task-execution-policy resolution
backend/app/modules/checkers/models.py only for checker-to-submission context integrity
backend/app/composition/review_lifecycle.py only to install the revision participant
backend/app/db/models.py
backend/alembic/versions/<activation-next>_revision_context.py
backend/tests/test_{alembic,reviews,tasks,projects,checkers,artifacts,authorization,app}.py
docs/decision_0010_revision_context_rebase.md
docs/operations_revision_replay.md
docs/template_revision_replay.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-09A.json
```

## Not allowed

```text
mutation of prior submission/review/finding
new submission.revise permission
parallel review-owned resubmission endpoint
contributor/reviewer-callable revision-preparation or repair route
out-of-band guidance as acceptance authority
automatic reject at limit/deadline
public decision route activation
finding resolution or preferred-return routing
production `/api/v1` review-router registration
```

## Acceptance criteria

- Revision preparation compares the prior Submission's stamped guide identity
  and activation sequence with the project's currently active Project Guide.
  Exact identity/activation-sequence match records `kept`; any different active
  identity or sequence records `rebased` plus `forward` or `backward` direction,
  including a lower activation sequence. Missing, incomplete, or unsafe active
  context records manager-repair block. No prior
  task-attempt or Submission row is mutated.
- Immutable `RevisionContextPreparation` persists task, immutable
  `reviewed_task_assignment_id`, current `target_task_assignment_id`, and prior-
  Submission identity; `revision_episode_id` as an FK to the originating
  `needs_revision` Review (not a separate episode entity);
  target Submission version; preparation sequence/supersession identity;
  kept/rebased/blocked
  outcome; complete guide/source-snapshot and task-execution policy IDs,
  versions, hashes, and locked bodies required by submission/checker execution;
  context digest;
  bounded change summary/reason; preparing actor/process; audit link; and
  database timestamp. A partial unique root constraint permits exactly one root
  per revision episode; `(task_id, revision_episode_id, preparation_sequence)`
  is unique; `supersedes_preparation_id` is unique so one parent has at most one
  child; and a deferred constraint trigger requires every edge to keep the same
  task, reviewed assignment, prior Submission, target version, and episode while
  incrementing the sequence by exactly one. Target assignment also remains the
  same except for the exact authority-loss replacement transition below.
  Manager repair appends a successor;
  the row with no child is the sole head.
- A deferred database constraint validates the episode Review and root together:
  `revision_episode_id` must reference a Review whose decision is
  `needs_revision`, whose reviewed Submission is exactly `prior_submission_id`,
  and whose project, task, and reviewed TaskAssignment match
  `reviewed_task_assignment_id`; the target assignment must be for the same task
  and exact active contributor authorized to fulfill the next attempt;
  `target_submission_version` must be the prior Submission version plus one.
  Successors retain that exact root lineage.
- Normal roots set target assignment equal to reviewed assignment. If AUTH-13
  closes that assignment for authority loss, the task retains an unassigned
  revision obligation. A covered manager's later replacement-assignment command
  invokes a typed review-owned transfer participant in the same caller session;
  it appends exactly one successor whose reviewed assignment remains fixed and
  whose target is the replacement, re-evaluates the authoritative current guide,
  and commits or rolls back with assignment creation. Reactivation never restores
  the old assignment. Concurrent replacement/repair/submission produces one
  head or a stable stale-head conflict.
- Finding-response evidence intake declares
  `review.finding_response_evidence.ingest` mapped to `submission.create`; it
  uses request-scoped preflight before ART candidate intake. Finalization uses
  AUTH prepare/authority lock and an opaque, non-Pydantic, single-use handle
  bound to exact session, ActionId, actor-reference kind and ID, idempotency key,
  and canonical request digest -> REV exact assignment, preparation head, prior
  Submission, finding and evidence-slot locks -> ART candidate/admission/binding
  locks -> final fact recomposition -> AUTH validation of exact bindings/current
  authority, single consumption, evaluation, and evidence staging before the
  first binding or REV mutation -> binding plus ReviewEvidenceArtifact flush.
  Wrong-binding, serialized, forged, or caller-constructed attempts against an
  unconsumed handle fail before canonical mutation, stage no
  AuthorizationDecision/evidence, preserve the legitimate handle, and permit its
  later exact first use. Stale/already-consumed and concurrent duplicate attempts
  remain invalid and stage no new state. Current-authority
  or policy denial after valid consumption follows AUTH's clean denial-evidence
  protocol. Pre-intake denial creates no ART candidate, binding, or receipt.
- Contributor and later reviewer see old/new guide/task-execution-policy context
  and change summary. ContributionPolicyVersion is not part of this context.
- While the task is `needs_revision`, the assigned submitter's Task Context API
  returns the prepared next-attempt guide/policy context. Submission N+1 stamps
  that same context; the reviewer later consumes it from Submission N+1 and
  performs no separate guide rebase.
- Project Guide is the only guide identity. No ReviewGuide, reviewer guide lock,
  or duplicate TaskAssignment guide-version field is introduced.
- Preparation freezes exact guide/source-snapshot and task-execution policy IDs,
  versions, and hashes. It never copies, substitutes, or rebases
  `ContributionPolicyVersion`; submitter policy remains frozen on the
  immutable TaskAssignment and reviewer policy remains frozen on each
  ReviewLease. Task Context returns the preparation and Submission N+1 must
  match it exactly. A later guide activation causes no silent drift; a revoked,
  corrupt, or invalid prepared context fails with an explicit re-preparation
  requirement.
- The hidden `needs_revision` transaction synchronously appends the initial
  preparation before the task becomes contributor-readable. Task Context is a
  read-only deterministic resolver that selects the unsuperseded head and then
  validates it; a blocked/revoked/corrupt/invalid head never falls back and the
  read performs no lazy write. Revision submission supplies the head ID/digest as an
  acknowledgment; Submission N+1, finding responses, audit, and enqueue intent
  commit atomically against it.
- The migration removes Submission composite FKs that require every locked
  context field to equal `WorkstreamTask.locked_*`. It replaces them with
  direct same-project ProjectGuide/policy/source-snapshot integrity constraints,
  requires version N+1 to reference the exact preparation/context digest, and
  preserves the original task locks and every prior Submission unchanged.
- The same migration removes CheckerRun composite FKs that require guide/review/
  revision context to equal `WorkstreamTask.locked_*`. Any legacy checker or
  Submission payment-context fields have already been removed by the exact
  merged CON-owned retirement capability and are not replaced here. A CheckerRun for
  Submission N is instead constrained to the exact immutable context stamped on
  Submission N, including its post-submit policy and rebased guide/policy/source
  facts. This permits checker execution for a valid rebased N+1 without allowing
  mixed task, project, Submission, or context lineage.
- The existing `submission.create` operation creates version N+1 with immediate
  predecessor and one immutable response per unresolved blocking finding.
- Revision preparation is a task-owned internal participant invoked by
  `needs_revision`; submission only validates/acknowledges its frozen result.
  Initial preparation has no separately callable route or ActionId. The
  privileged manager repair command is deliberately deferred to chunk 11 and
  may append a successor only; it cannot create the root.
- `POST /api/v1/tasks/{task_id}/submissions` remains the only submission route.
  It declares the canonical AUTH-14 `submission.create` action for both initial
  and revision submissions.
  This chunk extracts its task-owned participant with caller AsyncSession and
  reuses existing version allocation, locked policy, lifecycle, audit, and
  post-commit enqueue rules without changing the registered route/schema or
  legacy production behavior. The hidden review revision participant validates
  preparation/responses and flushes response rows in the same test unit of
  work; neither domain imports the other's repository.
- Required response evidence references verified same-project/task bindings.
- Checker gate does not admit a revision missing required responses/evidence.
- At the exact revision-round limit or revision deadline, preparation and N+1
  submission fail with stable policy errors. Task remains `needs_revision`,
  TaskAssignment remains active, and no Review, finding, terminal Task or
  Assignment status, CON record, award, feature audit, or outbox record is
  created. Tests cover below/at/after each boundary, retry, and transaction
  rollback. The explicit reason-bound cancellation command remains owned only by
  REV-11; 09A never closes the obligation or fabricates reject.
- Response-evidence authorization uses
  `review.finding_response_evidence.ingest` mapped to `submission.create`, plus
  the owned active assignment, prepared revision context, and exact
  server-derived project/task/submission/finding operation scope. A race lost to
  revocation, assignment loss, or preparation supersession creates no canonical
  binding/relation, Submission response, or lifecycle effect; any uploaded
  unbound candidate is ART-owned and expires through ART retention.
- Response finalization depends on the same merged
  `WS-ART-001-REV-EVIDENCE` port and AUTH-active
  `artifact.review_evidence.binding.create` service action as REV-07; human
  `submission.create` authority cannot execute that ART action.
- Revision preparation, evidence-intake, and structured response behavior remain
  hidden and unavailable from production OpenAPI/composition in this chunk.
  Existing first-submission and legacy revision behavior is unchanged until the
  later amended AUTH-14 cutover installs the prepared branch and strict guard
  behind unavailable `submission.create`; internal composition/tests prove the
  new path before that owner cutover.
- This chunk changes no AUTH availability. It supplies hidden behavior and a
  feature-manifest delta for later `WS-AUTH-001-REV-09A` activation; route
  exposure waits for REV-13.
- Preparation-reference columns and conditional lineage constraints land here,
  but the global rule requiring every newly written version greater than one to
  reference a preparation does not. After REV-09A merges, amended AUTH-14 owns
  the `NOT VALID` check and replaces the legacy submission branch in one reviewed
  cutover while `submission.create` remains unavailable. REV-13 later verifies
  and exposes that already merged cutover, so no deployment exposes an
  `IntegrityError` or an accidental early public block.
- Import-boundary and rollback tests prohibit a parallel resubmission route,
  commit-owning participant, repository cycle, or duplicate post-commit enqueue.
- Real-Postgres tests cover same-guide keep, forward changed-guide rebase,
  backward changed-guide rebase, inconsistent/unsafe block,
  repair/successor preparation, Task
  Context before submission, preparation
  acknowledgment mismatch, invalid preparation, constraint-safe N+1 stamping,
  and immutable N/prior task locks.
- Forward and backward rebase tests prove the TaskAssignment submitter
  ContributionPolicyVersion is unchanged. A later reviewer lease may
  independently freeze the then-current reviewer ContributionPolicyVersion; no
  Submission, CheckerRun, Task Context, or preparation field duplicates either
  contribution-policy freeze.
- Independent-session barrier tests race guide activation against
  `needs_revision` and prove one complete old/new context, canonical lock order,
  and no mixed policy generation or deadlock. Head-selection tests prove no
  fallback from blocked/invalid successors.
- Independent-session barriers exercise the repository/schema successor
  primitive by racing two successor appends and a
  successor append against N+1 submission on the formerly current head. Exactly
  one unsuperseded head remains; submission either commits against its still-
  current acknowledged head or fails `repreparation_required`, with no fallback,
  partial response rows, or feature audit/enqueue intent. AUTH may retain only
  its bounded clean denial evidence under the AUTH-owned rollback/restaging
  protocol.
- A post-read activation test prepares and reads context, activates a newer
  guide, then proves the still-valid frozen head stamps one complete old context
  without drift. Separate revocation/corruption tests require re-preparation and
  produce no Submission/response or feature audit/enqueue side effects. AUTH may
  persist only its bounded clean denial evidence; evidence, participant,
  cancellation, or commit failure leaves no partial authority evidence.
- Independent-session tests race grant revocation, assignment loss, and
  preparation-head supersession against response-evidence candidate intake and
  finalization in both orders. Submission creation revalidates the finalized
  canonical binding and cannot consume an orphan candidate.
- Replacement-assignment tests prove authority-loss close, durable unassigned
  obligation, atomic successor transfer, replacement Task Context/read and N+1
  submission, old-contributor denial, replay requirements, guide re-evaluation,
  target-assignment contribution-policy source, and rollback/concurrent replacement.
- Fault injection during initial preparation rolls back the Review,
  `needs_revision` task/assignment effect, lease consumption, audit, and outbox
  so contributor access can never observe `needs_revision` without one head.
- Migration fixtures cover existing initial/revision rows, the non-forgeable
  preparation-reference schema, preserved historical task-equal contexts, and
  a prepared rebased N+1 whose context differs from the original task lock.
  They prove unprepared legacy rows remain possible only until amended AUTH-14's
  atomic route/schema cutover. Direct SQL rejects cross-project
  guide/policy/source/preparation references, prior-Submission mismatch, and
  preparation digest mismatch. Upgrade proof documents that rollback is blocked
  once rebased rows depend on the new constraints.
- Migration/constraint tests also create a rebased N+1 CheckerRun and prove it
  matches Submission N+1 rather than the original task lock. Direct SQL rejects
  checker rows with crossed Submission, project, guide, source, or policy facts.
  Existing `needs_revision` tasks that lack an originating Review and preparation
  root are reported as incompatible and remain fail-closed for operator
  remediation; migration and activation never fabricate a Review or root.
- Direct SQL root tests reject an accept/reject Review, a Review of another
  Submission, crossed task/project/assignment lineage, a target version other
  than prior version plus one, a second root, and a branched/skipped successor;
  each failed transaction leaves no root or head. Migration proof also shows
  historical unprepared revisions remain immutable/readable, names the
  conditions for amended AUTH-14 enforcement/validation and later REV-13
  verification/exposure, and blocks migration downgrade once prepared rows exist.

## Verification

```text
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_reviews.py tests/test_tasks.py tests/test_projects.py tests/test_checkers.py tests/test_artifacts.py tests/test_authorization.py tests/test_alembic.py tests/test_app.py
cd backend && ruff check app/modules/reviews app/modules/tasks app/modules/projects app/modules/checkers/models.py tests/test_reviews.py tests/test_tasks.py tests/test_checkers.py tests/test_app.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/modules/tasks/models.py app/modules/tasks/repository.py app/modules/tasks/service.py app/modules/tasks/lifecycle.py app/modules/tasks/submission_participant.py app/modules/projects/models.py app/modules/projects/repository.py app/modules/projects/service.py app/modules/checkers/models.py app/composition/review_lifecycle.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta.

## Human review focus

Fairness of rebase, complete response input, evidence authorization, and no
synthetic decision.

## Stop condition

Merge, record automated memory, and stop. Do not start 09B.
