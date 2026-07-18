# Chunk Contract: WS-REV-001-02 - Locked Review Policy And Task Lifecycle Alignment

## Goal

Align locked review policy, task terminal states, assignment blocking fields,
and the existing versioned Submission with WS-REV without adding review queues.

## Risk class

L1 schema, policy, and lifecycle.

## Preconditions

- Current trusted main contains the merged WS-AUTH definition of done.
- Current trusted main contains AUTH-08's regression proof for rollback-only
  authorization-dependency teardown, typed decision-evidence SQL failure mapped
  to the stable retryable 503, and documented route-owned canonical
  verification-timestamp semantics.
- Before this chunk starts, AUTH must amend its current circular AUTH-13/14 graph
  and merge an AUTH-owned schema-only contributor-field foundation. That bounded
  foundation performs only the canonical `TaskAssignment.contributor_id` and
  `Submission.contributor_id` clean cuts while preserving current task,
  submission, checker, and legacy-revision behavior. It must not claim the later
  replacement/replay behavior that depends on REV-09A. AUTH assigns the exact
  chunk ID and migration numbers from then-current main through a separately
  reviewed contract; REV does not invent them or edit the retired fields.
- Full AUTH-13/14 product cutovers are not REV-02 prerequisites. After REV-09A
  merges hidden prepared revision/replacement behavior, AUTH must amend and
  complete those cutovers before REV-13. Parallel edits to contributor fields or
  revision behavior outside this order are prohibited.
- This chunk consumes those contracts but changes no AUTH implementation.

## Allowed files

```text
backend/app/modules/projects/{models,schemas,repository,service}.py
backend/app/modules/tasks/{models,schemas,lifecycle,repository,service}.py
backend/app/db/models.py
backend/alembic/versions/<activation-next>_review_policy_task_alignment.py
backend/tests/test_{alembic,projects,tasks}.py
docs/architecture_lifecycle_state_machine.md
docs/operations_revision_replay.md
docs/operations_operator_workflow.md only for migration/deployment/remediation notes
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-02.json
```

## Not allowed

```text
new SubmissionVersion table
review queue, lease, Review, or finding tables
public review routes
authorization or artifact implementation
contribution or compensation implementation
synthetic reject from checker, deadline, or revision limit
```

## Acceptance criteria

- Dependency refresh records the exact merged AUTH repair SHA and proves every
  precondition above before migration or runtime edits begin.
- Review policy stores task-lockable preference, lease, capacity=1,
  self-review=false, close-task reject, and finding-evidence settings.
- Once a ReviewPolicy is part of an activated Project Guide context, it is
  immutable; policy changes require a new guide version. Its canonical UUID is
  the typed `policy_context_ref` later stored by FinalAcceptance, while Task and
  Submission continue to stamp the matching locked review-policy version.
- Existing policy rows receive an explicit safe migration rule; unsafe data
  fails with a remediation message.
- Task supports canonical `accepted`, `rejected`, and `cancelled` transitions
  without weakening existing transitions. Only human reject enters `rejected`;
  reason-bound administrative revision closure enters `cancelled`. No
  undocumented `closed` status or synthetic reject is added.
- TaskAssignment supports `completed` and `blocked` state compatibility, but no
  reject Review FK is added and no code can block before the Review table lands.
- Existing Submission remains the only version chain and its predecessor and
  actor semantics are enforced: immutable rows, same-task predecessor, exact
  version N-1 linkage, and canonical submitter ActorProfile identity. Database
  constraints or deferred constraint triggers guard direct SQL as well as the
  service path; unsafe historical lineage fails with a remediation message.
- Submission gains an immutable `task_assignment_id` bound by composite
  integrity to the same task. Its AUTH-14-owned `Submission.contributor_id` must
  equal the AUTH-13-owned `TaskAssignment.contributor_id` on that exact
  assignment. Existing rows are
  backfilled only when exactly one assignment is provably responsible; ambiguous
  lineage fails migration with explicit remediation instead of selecting a
  current or recent assignment. Assignment release/reassignment never changes
  a prior Submission's attribution.
- TaskAssignment stores only `task_id` for context resolution and does not
  duplicate or reference a guide/context lock. The task-context resolver uses
  the task lock for initial work, a later immutable preparation for revision
  work, and each Submission's own stamped context for history.
- ProjectGuide receives a per-project monotonic immutable activation sequence;
  activation allocates it exactly once under a project row lock. Existing
  active/superseded guides are deterministically backfilled by effective time,
  creation time, and ID with collision/ambiguity validation; draft guides remain
  null until first activation. Database checks require null for drafts and
  non-null for active/superseded guides, and uniqueness covers project plus
  activation sequence. Task and Submission contexts stamp guide ID, version,
  and activation sequence; no semantic or lexical version comparison determines
  rebase order.
- Direct-SQL tests reject sequence mutation, duplicate project/sequence,
  draft-with-sequence, active/superseded-without-sequence, and allocation of a
  second sequence when a previously activated guide is reactivated. Migration
  fixtures prove deterministic historical backfill, sequence preservation on
  reactivation, concurrent allocation under the project lock, and downgrade
  refusal once task/Submission contexts stamp activation sequence.
- Project-guide activation locks Project, candidate/current guide,
  source-snapshot, and artifact/effective/pre-check/post-check/review/revision/
  policy rows in the canonical PLAN order before publication. If retired
  compensation-context state still exists before WS-CON cutover, it is locked only as a
  transitional consistency input; WS-CON owns its later consumer and schema
  removal. The final Project Guide/revision context contains no retired compensation or
  ContributionPolicyVersion. Publication never assembles mixed generations.
- Every persisted human identity added or validated here is the canonical
  active human `ActorProfile.id`. External subjects, email, legacy typed-profile
  IDs, token roles, and current-assignment inference are rejected as identity
  substitutes.
- Human-only persistence is database-enforced with an immutable composite
  actor-kind candidate key plus local `actor_kind='human'` check, or an
  equivalently reviewed deferred constraint trigger. A plain FK to
  `ActorProfile.id` is insufficient; mutable active status is revalidated by
  AUTH in the transaction rather than treated as an immutable FK fact.
- The approved limit/deadline decision is encoded without fabricating Review.
- Legacy `auto_reject_after_limit` is removed or migrated to the approved
  fail-closed D6 behavior; reaching the boundary blocks revision preparation
  and submission with no automatic task/assignment/Review/CON mutation.

## Verification

```text
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_alembic.py tests/test_projects.py tests/test_tasks.py
cd backend && ruff check app/modules/projects app/modules/tasks tests/test_alembic.py tests/test_projects.py tests/test_tasks.py
cd backend && docstr-coverage --config .docstr.yaml
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in app/modules/projects/models.py app/modules/projects/schemas.py app/modules/projects/repository.py app/modules/projects/service.py app/modules/tasks/models.py app/modules/tasks/schemas.py app/modules/tasks/lifecycle.py app/modules/tasks/repository.py app/modules/tasks/service.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, and test-delta.

## Human review focus

Migration safety, policy defaults, no duplicate submission identity, and no
synthetic human decision. Guide-sequence allocation/backfill and the rule that
the current active guide remains authoritative in both sequence directions
receive explicit human attention.

## Stop condition

Merge, record automated memory, and stop. Do not start 03.
