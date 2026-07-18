# Chunk Contract: WS-REV-001-02B - Locked Review Policy And Dormant Task Lifecycle Compatibility

## Parent initiative

`WS-REV-001` - Review And Revision Lifecycle

## Goal

Make guide-bound review/revision policy immutable and add the exact dormant Task
and TaskAssignment state shape required by later human Review decisions.

## Why this chunk exists

The current ReviewPolicy lacks routing, lease, no-self-review, reject, and
evidence rules; RevisionPolicy still advertises automatic reject. Tasks and
assignments also lack the terminal values later decision transactions require.
This child adds safe schema compatibility without making a human decision or
enabling a review effect before Review persistence exists.

## Risk class

L1 schema, policy, and lifecycle.

## SLA

P2.

## Preconditions

- 02A is merged and automated memory is current.
- The exact merged AUTH contributor-foundation PR/SHA and its canonical-human
  database constraint names are recorded.
- The human has approved concrete positive values for
  `review_preference_window_seconds` and `review_lease_duration_seconds`.
  Neither value may be inferred from `sla_hours`.
- This contract receives a separate human start.

## Proposed exact policy schema

`ReviewPolicy` retains `id`, `project_id`, `guide_version`,
`allowed_decisions`, `minimum_finding_fields`, `sla_hours`, and `created_at`,
and adds:

```text
review_preference_window_seconds integer not null, > 0
review_lease_duration_seconds integer not null, > 0
max_active_review_leases_per_reviewer integer not null, = 1 in v0.1
self_review_allowed boolean not null, = false in v0.1
reject_policy varchar(30) not null, = 'close_task' in v0.1
finding_evidence_requirement varchar(30) not null,
  in ('optional', 'required_for_blocking', 'required_for_all')
```

`finding_evidence_requirement` backfills to `optional`. Capacity, self-review,
and reject policy backfill to their single v0.1 values. Existing duration values
use only the two separately approved migration defaults. Existing
`allowed_decisions` must equal the canonical three decision values and
`minimum_finding_fields` must contain `description` and `severity`; unsafe rows
fail with remediation rather than being silently broadened.

`requires_second_review` is retained but database-constrained to false in v0.1.
Migration fails if any existing row is true.
`RevisionPolicy.auto_reject_after_limit` is removed because D6 permits no
automatic reject; the migration records that the retired field never had an
implemented Review-producing runtime path.

## Allowed files

```text
backend/app/modules/projects/{models,schemas,repository,service}.py
backend/app/modules/tasks/{models,schemas,lifecycle,repository,service}.py only for Task/TaskAssignment lifecycle compatibility
backend/app/db/models.py
backend/alembic/versions/<then-current-next>_review_policy_task_lifecycle.py
backend/tests/test_{alembic,projects,tasks}.py
docs/architecture_data_model.md
docs/architecture_lifecycle_state_machine.md
docs/operations_revision_replay.md
docs/operations_operator_workflow.md only for migration/deployment/remediation
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-02B.json
```

## Not allowed changes

```text
Submission schema, attribution, predecessor, or finalization behavior
ProjectGuide activation-sequence behavior except consuming merged 02A fields
Review, ReviewLease, ReviewFinding, FinalAcceptance, or reject Review foreign key
service transition into accepted, rejected, completed, or blocked
public review or revision-obligation-close route
AUTH, ART, CON, compensation, contribution, reputation, or adjudication behavior
synthetic reject from checker, revision limit, deadline, or administrative close
```

## Acceptance criteria

- Once its guide has an activation sequence, ReviewPolicy and RevisionPolicy are
  update/delete protected by database guards. Policy changes require a new draft
  guide version; both draft policies remain replaceable before first activation.
- `ReviewPolicy.id` is the canonical future `policy_context_ref`. Task and
  Submission continue to stamp the matching locked policy version; no duplicate
  review policy snapshot table is added.
- `allowed_decisions` remains exactly `accept`, `needs_revision`, and
  `reject`. Capacity is one, self-review is false, and reject policy is
  `close_task`.
- Review-policy service/schema validation matches the database constraints;
  an upsert cannot mutate a policy whose guide was ever activated.
- Removing `auto_reject_after_limit` creates no Task, Assignment, Review, CON,
  award, outbox, or audit mutation. Executable limit/deadline blocking belongs
  to 09A revision preparation/submission and is not implemented in 02B.
- Task storage accepts canonical terminal statuses `accepted`, `rejected`, and
  `cancelled` plus a bounded terminal reason/time shape. The only reserved
  reason mapping is `accepted -> review_accepted`,
  `rejected -> review_rejected`, and
  `cancelled -> revision_limit_reached | revision_deadline_expired |
  legacy_revision_context_unrecoverable`. All cancellation reasons remain
  dormant until their separately authorized administrative commands land.
- The lifecycle module defines the status constants but exposes no transition
  edge into those terminal states in this child. Review-driven edges land with
  the decision/task participant; the administrative cancellation edge lands
  with its reason-bound command.
- TaskAssignment storage accepts `active`, `released`, `completed`, and
  `blocked`, with compatible `completed_at` and `blocked_at` timestamp shape.
  No service path enters completed/blocked, and no reject Review FK or
  `blocked_reason_review_id` is added before Review persistence.
- Existing task/assignment rows preserve their status. Unknown statuses or
  inconsistent existing terminal timestamps fail with explicit remediation.
- No checker, limit, deadline, or migration creates a synthetic Review or human
  reject outcome.

## Verification commands

```text
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_alembic.py tests/test_projects.py tests/test_tasks.py
cd backend && ruff check app/modules/projects app/modules/tasks tests/test_alembic.py tests/test_projects.py tests/test_tasks.py
cd backend && docstr-coverage --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
```

The full isolated PostgreSQL suite must preserve the repository-wide 78 percent
floor. Every materially changed projects/tasks module must remain at or above
90 percent coverage.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, and test-delta.

## Human review focus

Duration defaults, activated-policy immutability, removal of automatic reject,
dormant versus executable status behavior, and no premature Review FK.

## Stop conditions

- Stop if duration defaults are unapproved or historical policy values are
  unsafe.
- Stop if the change needs Review persistence or an AUTH schema edit.
- Merge, record automated memory, and stop. Do not start 02C automatically.
