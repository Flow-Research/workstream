# Chunk Contract: WS-REV-001-11

## Goal

Implement reason-bound administrative routing/lease operations, grant-revocation
recovery, and queue/lease/review reconciliation without rewriting history.

## Risk class

L1 privileged operations and recovery.

## Allowed files

```text
backend/app/modules/reviews/{models,repository,schemas,service,router}.py
backend/app/modules/tasks/review_participant.py only for caller-transaction administrative closure effects
backend/app/composition/review_lifecycle.py only to install existing task/revision participants
backend/app/db/models.py
backend/alembic/versions/<activation-next>_review_reconciliation_admin_commands.py
backend/app/workers/{celery_app,reviews}.py
backend/tests/test_{alembic,reviews,authorization,artifacts,audit}.py
docs/operations_reviewer_workflow.md
docs/operations_operator_workflow.md
docs/operations_queue_policy.md
docs/operations_revision_replay.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-11.json
```

## Not allowed

```text
admin decision authority without reviewer grant and lease
hard deletion or mutation of immutable review history
operator execution as artifact recovery lease owner
silent reconciliation repair
new adjudication or reject reopen flow
production `/api/v1` review-router registration
```

## Acceptance criteria

- Force release, routing override, compensating routing correction,
  administrative closure, and reconciliation declare, respectively,
  `review.lease.force_release`, `review.queue.routing.override`,
  `review.queue.routing.correct`, `review.queue.close`, and
  `review.reconcile.run`. Human mutations use AUTH prepare/authority lock and an
  opaque, non-Pydantic, single-use handle bound to exact session, ActionId,
  actor-reference kind and ID, idempotency key, and canonical request digest;
  REV canonical row locks and final fact recomposition; then AUTH validates every
  binding/current authority, consumes once, evaluates once, and stages evidence
  before first feature mutation; participant flush and one request-route/service-
  command commit follow. They require exact covered scope and mandatory
  reasons; queue closure,
  correction, and force release remain Operator-only.
- `POST /api/v1/tasks/{task_id}/revision-obligation/close` declares the additive
  AUTH-owned `review.revision_obligation.close` ActionId mapped to existing
  `project.task.manage`. Only a covered Project Manager grant is a candidate.
  The server-derived typed resource contains the exact project, task, current
  assignment, originating `needs_revision` Review, current preparation head,
  revision limit/deadline policy, and proof that the selected terminal cause is
  currently reached. The request supplies only idempotency key, current head
  ID/digest, bounded reason, and one of `revision_limit_reached` or
  `revision_deadline_expired`; missing/not-yet-reached, stale/crossed,
  cross-project, Operator-only, or arbitrary cause attempts fail closed.
- D6 closure locks/revalidates current authority and those exact rows, records
  `ReviewAdministrativeCommandRequest`, AuthorizationDecision, audit, and outbox
  evidence, and applies the terminal effects below in one caller transaction.
  Exact replay returns the same closure; changed cause/head/reason/actor
  conflicts. It creates no reconciliation finding and cannot reuse Operator
  `review.queue.close` or legacy-close authority.
- `POST /api/v1/tasks/{task_id}/revision-context/repair` declares the additive
  AUTH-owned `review.revision_context.repair` ActionId mapped to existing
  `project.task.manage`. Its candidate authority is only a Project Manager grant
  covering the canonical project. Its typed resource contains exact project,
  task, assignment, prior Submission, revision episode, and current head facts,
  and requires transaction revalidation. AUTH locks authority before REV locks
  these feature rows. The command requires idempotency, a
  bounded reason, and the
  current preparation head ID/digest. Through the existing task-owned revision
  participant it locks and revalidates authority, project/guide/policies,
  task/assignment, prior Submission, revision episode, and head, then appends
  exactly one validated successor. It cannot create a root, edit a preparation,
  or act on a healthy submitted/terminal episode.
- Repair follows the canonical order through Submission then
  RevisionContextPreparation. The originating episode Review is immutable and
  is read/revalidated through its constrained FK lineage without taking an
  earlier Review row lock; the command never reorders Review ahead of the
  preparation head.
- Repair-versus-repair and repair-versus-submission barriers run both commit
  orders. Exact replay returns the same successor; changed replay conflicts;
  stale head returns a stable conflict/re-preparation response; one head remains
  and no partial feature audit/outbox/lifecycle effect commits. AUTH denial
  evidence follows the separate clean rollback/restaging protocol.
- Reconciliation classifies legacy `needs_revision` rows without an originating
  Review/root as `legacy_revision_context_unrecoverable`. The exact
  `POST /api/v1/admin/review-reconciliation/{finding_id}/legacy-revision-close`
  endpoint declares additive AUTH-owned
  `review.revision_context.legacy_close` mapped to existing
  `operations.reconcile.run`; only an Operator AdminRoleGrant is a candidate.
  Its typed resource contains the canonical unresolved finding, project, task,
  assignment, queue, and no-Review/no-root facts and requires transaction
  revalidation. The command is idempotent, requires the reconciliation finding
  ID and reason, and closes the task with that
  stable terminal reason by moving the task to canonical `cancelled`, releases/clears its assignment, closes any queue as
  `admin_cancelled`, preserves immutable history/project grant, and creates no
  Review, preparation root, CON/award/reputation record, or synthetic reject.
- Chunk 11 owns `ReviewReconciliationFinding` with immutable defect/evidence
  facts and a set-once resolution pointer, plus one-to-one immutable
  `ReviewReconciliationResolution` records for domain inconsistency evidence;
  they are not audit or queue replacements. It also owns a bounded
  `ReviewAdministrativeCommandRequest` idempotency aggregate keyed by actor,
  ActionId, canonical resource, and client key, with canonical payload digest
  and stable response snapshot. These reuse shared canonical hashing/request/
  correlation conventions and do not reuse AUTH decision persistence or the
  lease/submission-specific `ReviewDecisionRequest`.
- Each reconciliation finding stores a canonical `identity_fingerprint` over
  finding type plus canonical project/resource/lineage IDs, an immutable
  `evidence_fingerprint` over the detected bounded facts, and a monotonically
  allocated `generation` under the canonical resource lock. PostgreSQL enforces
  unique `(identity_fingerprint, generation)` and a partial unique index allowing
  at most one row with a null resolution pointer per identity. Duplicate or
  concurrent scans use insert-on-conflict/reload and emit no duplicate alert or
  outbox effect.
- Resolution atomically inserts the unique resolution row and sets the finding's
  null pointer exactly once; a deferred trigger requires mutual one-to-one IDs,
  the same administrative request/finding, and consistent actor/reason/auth/audit
  facts. After resolution, a genuinely recurring defect may allocate generation
  N+1 only after re-reading current resource facts under lock. It never reopens,
  edits, or reuses generation N.
- Legacy closure loads the finding identity, then in canonical order locks the
  administrative request, Project, task, assignment, queue if present,
  reconciliation finding, and relevant Review/preparation absence facts. The
  finding must remain unresolved/current, belong to that exact project/task,
  and still prove the no-Review/no-root condition. Exact replay returns the
  original closure; changed actor/resource/finding/reason payload conflicts.
  Crossed/stale evidence, closure-versus-reconciliation, assignment/queue races,
  duplicate delivery, and denial/fault rollback are covered in both orders.
- The successful legacy-close transaction atomically appends the one-to-one
  `ReviewReconciliationResolution` linked to the exact finding and
  `ReviewAdministrativeCommandRequest`, recording actor, bounded reason,
  AuthorizationDecision, audit/outbox evidence, and terminal effects. Any fault
  rolls back the resolution, command completion, task/assignment/queue effects,
  audit, and outbox together, so the finding remains unresolved when closure did
  not commit.
- Migration/direct-SQL tests reject duplicate unresolved identities, duplicate
  identity/generation, a second or crossed resolution, and pointer/resolution
  mismatch. Independent-session tests cover duplicate reconciliation scans,
  reconciliation versus closure, post-resolution recurrence, job retry/
  restart, and fault rollback, proving one unresolved finding, at most one
  resolution, stable alert/outbox effects, and no partial administrative request.
- D6 limit/deadline closure is explicit and idempotent: task moves from
  `needs_revision` to `cancelled` with `revision_limit_reached` or
  `revision_deadline_expired`, assignment atomically
  becomes `released` with `released_at=database_now`, the task's active-assignee
  projection clears, reclaim is denied because the task is terminal, queue closes
  `admin_cancelled`, project grant is unchanged, and no
  Review/CON/award/reputation record is created.
- D6 tests cover PM allow, non-PM and Operator denial, cross-project concealment,
  not-yet-reached denial, both terminal causes, stale/crossed head, exact and
  changed replay, closure versus submission/repair/reassignment, and fault
  rollback after every state/audit/outbox participant.
- Exact reviewer-grant revocation, actor suspension/deactivation, corrected attribution that
  creates self-review, and policy ineligibility immediately invalidate
  preference/decision authority and revoke/requeue an active lease while
  preserving queue age; missed recovery is detected idempotently.
- Reviewer-grant reconciliation changes only review preference, lease, and queue
  state. It never revokes, replaces, or mutates submitter, adjudicator, or
  AdminRoleGrant rows. Submitter revocation remains task-assignment owned;
  adjudicator invalidation remains dormant until a separate lifecycle exists.
- Reconciliation detects every specified queue/lease/review inconsistency and
  emits alerts/compensating events rather than silent edits.
- Reviewer-authority invalidation reconciliation runs only as fixed service
  `workstream.review.authority_invalidation_reconciliation`; general queue,
  lease, and history reconciliation runs only as
  `workstream.review.reconciliation`. Both have their own exact static
  `review.reconcile.run` row, an AUTH-09A-compatible identity/matrix extension,
  AUTH-09B-provisioned ActorProfile/link, AUTH-09E admission, cross-service
  denial, and later AUTH action activation. Neither borrows
  Operator or reviewer identity; human Operator closure/force-release remains a
  separate prepared path. Neither identity belongs to AUTH-09A's seven-identity
  ART set. Generic AUTH-09E admission does not provision either identity; AUTH
  adds each exact identity, constraint, static membership, and admission proof
  only from this chunk's reviewed service manifest.
- Artifact verification recovery calls the existing ART-owned
  `ArtifactOperatorRecoveryPort` with the registered
  `artifact.verification_job.retry` action. The provisioned Artifact Storage
  execution service runs under ART fencing; WS-REV owns neither another recovery
  permission nor execution lease.
- Admin without reviewer grant still cannot claim or decide.
- Revocation/decision and override/claim races are deterministic.
- Release, decline, override, force-release, admin closure, recovery, and any
  actor-attributed deferred commit use AUTH's prepared mutation protocol,
  persist the AuthorizationDecision link, follow the command-specific lock order, and
  reject wrong-binding, serialized, forged, or caller-constructed attempts
  against an unconsumed handle before feature mutation. That rejection stages no
  AuthorizationDecision/evidence, preserves the legitimate handle, and permits
  its later exact first use. Stale/already-consumed and concurrent duplicate
  attempts remain invalid and stage no new state. AUTH alone validates bindings,
  consumes once, evaluates once, and stages evidence after REV recomposes final
  facts. Current-authority
  or policy denial after valid consumption leaves no REV/task/ART/CON mutation or
  feature audit/outbox event. The request route or service command rolls back the
  dirty transaction; AUTH restages the unchanged bounded denial in a clean
  transaction; and that route or command commits the evidence once. Evidence,
  participant, cancellation, commit, or restaging failure commits nothing.
- This chunk supplies hidden behavior/resource facts for its actions and changes
  no ActionOwner or availability. `WS-AUTH-001-REV-11` activates the existing
  action group after merge. `WS-AUTH-001-REV-LIFECYCLE` activates the three
  additive chunk-11 actions only after all four additive manifests, including
  REV-12A, merge. Product route release waits for REV-13.
- Production OpenAPI remains free of lifecycle routes.
- Recovery/reconciliation jobs reuse `run_async_task`, fresh execution
  engine/session disposal, stable task IDs, and `sync_task_settings`; they do
  not introduce another async bridge, session factory, or queue helper.

## Verification

```text
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_alembic.py tests/test_reviews.py tests/test_authorization.py tests/test_artifacts.py tests/test_audit.py
cd backend && ruff check app/modules/reviews app/workers/reviews.py tests/test_reviews.py tests/test_alembic.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/modules/tasks/review_participant.py app/composition/review_lifecycle.py app/workers/reviews.py app/workers/celery_app.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, and test-delta.

## Human review focus

Privilege separation, mandatory reasons, revocation race, recovery fencing, and
immutable history.

## Stop condition

Merge, record automated memory, and stop. Do not start 12.
