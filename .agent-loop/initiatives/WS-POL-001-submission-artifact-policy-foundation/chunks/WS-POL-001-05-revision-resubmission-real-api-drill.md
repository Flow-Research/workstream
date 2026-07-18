# Chunk Contract: WS-POL-001-05 - Revision Resubmission And Real API Drill

## Parent Initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Prove the current policy-driven submission path end to end after
post-submit/internal checkers route a submitted task to `needs_revision`.

This chunk also renames the persisted post-submission evaluation status from
`auto_checking` to `evaluation_pending`. The human-facing display label may be
`EVALUATION_PENDING`, but stored workflow values and API payloads use the
canonical lower-snake token `evaluation_pending`.

This rename is persisted data, not only wording. The implementation may add a
narrow Alembic data migration that rewrites existing `workstream_tasks.status`
and audit-event `from_status`/`to_status` values from `auto_checking` to
`evaluation_pending`, or it must prove no migration is required because the
current schema stores unconstrained string values and tests start from clean
Postgres databases. The final proof must show no current runtime code, tests,
scripts, active docs, or real API drill output still depend on `auto_checking`.
The preferred implementation is the narrow Alembic data migration/backfill; use
the no-migration path only if it is proven that no supported persisted database
can contain `auto_checking`.

## Why This Chunk Exists

Chunks 1 through 4 established guide-source snapshots, sufficiency and
derivation agents, effective project submission artifact policy, project
`PreSubmitCheckerPolicy`, task locked context, submission creation, and locked
post-submit checker policy provenance.

The remaining proof gap is the worker revision loop. A worker must be able to
receive checker-caused `needs_revision`, run pre-submit feedback again, submit a
new immutable submission version, and have the fixed version move through the
same locked policy and post-submit checker path.

The status rename is part of this proof. `auto_checking` is vague and makes the
post-submission phase sound like an implementation detail. The lifecycle state
is the period after a valid submission exists and before Workstream's
post-submit evaluation has completed, so `evaluation_pending` is the clearer
persisted status.

## Approved Plan Reference

- INTENT: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- DISCOVERY: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/DISCOVERY.md`
- PLAN: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md`

## Risk Class

L1

## SLA

P1

## Implementation Allowed Files

```text
backend/alembic/versions/**
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/**
backend/scripts/week1_api_e2e.py
backend/scripts/week2_api_e2e.py
examples/terminal_benchmark/**
scripts/check_stale_workstream_wording.py
scripts/test_agent_gates.py
docs/spec_chunk_9_pre_review_gate.md
docs/spec_chunk_10_checker_trial.md
docs/spec_chunk_8_submission_artifact_policy_checkers.md
docs/spec_chunk_6_checker_contract_records.md
docs/spec_week2_checker_framework.md
docs/architecture_lifecycle_state_machine.md
docs/architecture_data_model.md
docs/architecture_checker_framework.md
docs/checker_trial_failure_catalog.md
docs/diagrams/task_lifecycle_sequence.md
docs/operations_queue_policy.md
docs/principles.md
docs/review_process_pattern_baseline_review.md
docs/roadmap_30_day_master_plan.md
docs/roadmap_status.md
docs/template_checker_policy.md
docs/template_task_status.md
docs/current_system_data_flow.html
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

The chunk map originally listed only the pre-review gate spec for docs. This
contract allows the additional lifecycle and roadmap docs because the user has
locked a lifecycle naming correction for the post-submission evaluation state.
The contract also allows `scripts/test_agent_gates.py` because the stale-token
gate is part of this chunk's deterministic proof and the scanner hardening must
carry regression coverage. Those docs may only be changed to replace
`auto_checking` with the canonical `evaluation_pending` lifecycle wording and to
record this chunk's evidence. Historical review notes under
`docs/internal_reviews/**` and prior chunk evidence under
`.agent-loop/**/reviews/**` should not be rewritten merely to rename historical
wording. The stale-token check must either exempt those historical evidence
paths or classify them as historical context.

## Implementation Not Allowed

```text
human review decision implementation
payment/reputation/blockchain code
frontend or demo UI changes
object-storage implementation
auth provider changes
agent runtime redesign
pre-submit checker derivation redesign
per-task checker compilation
new review decision values
new worker-facing checker route names
Workstream-owned login, signup, password, auth session, or API key auth
```

## Implementation Boundaries

- `evaluation_pending` is a task lifecycle status, not a review decision.
- The display label may be `EVALUATION_PENDING`; the persisted/API token is
  `evaluation_pending`.
- Stored product review decisions remain exactly `accept`, `needs_revision`,
  and `reject`.
- Checker routing recommendation tokens remain separate:
  `not_evaluated`, `allow_review`, `needs_revision`, `checker_retry`, and
  `task_setup_blocked`.
- `pre_review_gate` remains the checker/audit phase name. It is not the
  persisted task status.
- A valid locked submission moves `submitted -> evaluation_pending` before
  durable post-submit checkers execute.
- A clean post-submit checker result moves `evaluation_pending -> review_pending`.
- Worker-fixable blocking post-submit checker failures move
  `evaluation_pending -> needs_revision` with `outcome_source = auto_checker`.
- Internal checker retry or task setup defects keep the task internal in
  `evaluation_pending` until trusted repair or retry completes.
- A worker may run pre-submit feedback and create a replacement submission only
  for an owned task in `in_progress` or `needs_revision`.
- In v0.1 there is no separate public "resume revision" endpoint. A worker-owned
  task in `needs_revision` may submit the replacement version directly, which
  produces the lifecycle transition `needs_revision -> submitted`.
- A replacement submission creates a new immutable submission version. Older
  submission versions, manifests, locked policy context, and checker runs remain
  immutable.
- Fixed resubmission reuses the same locked project guide/source snapshot,
  effective project submission artifact policy, project `PreSubmitCheckerPolicy`,
  and locked post-submit checker policy context unless a later explicit audited
  rebase exists.
- Checker-caused `needs_revision` remains distinguishable from future
  human-review-caused `needs_revision` through `outcome_source`, null
  `review_decision_id`, and linked checker run id.
- Worker-visible `evaluation_pending` means Workstream is evaluating a locked
  submission and no worker action is required yet. Internal `task_setup_blocked`
  and `checker_retry` routes must remain operator/admin visible with owner
  action, retry or repair status, checker run id where one exists, submission
  id/version, and audit event ids.
- Worker-visible checker-caused revision feedback must include stable result or
  finding ids, submission version, severity, `worker_message`, and suggested fix
  when available, without exposing internal route/source/provenance fields.

## Acceptance Criteria

- [ ] `auto_checking` is replaced in current runtime code, tests, scripts, and
      active docs with `evaluation_pending` for the persisted post-submission
      evaluation status.
- [ ] A narrow migration/backfill proof exists for persisted rows that may
      already contain `auto_checking`. If the PR does not add a migration, it
      must explicitly prove no supported persisted database can contain
      `auto_checking`.
- [ ] Postgres-backed tests or the real API drill query the database and prove
      no persisted `workstream_tasks.status`, `audit_events.from_status`, or
      `audit_events.to_status` contains `auto_checking` after upgrade/drill.
- [ ] Deterministic stale-token verification fails if active code, tests,
      scripts, docs, or real API drill output still depend on `auto_checking`.
      Historical evidence paths may be explicitly exempt.
- [ ] The lifecycle allows `submitted -> evaluation_pending`,
      `review_pending -> evaluation_pending`,
      `evaluation_pending -> review_pending`, and
      `evaluation_pending -> needs_revision`.
- [ ] `review_pending -> evaluation_pending` is allowed only for trusted
      checker retry or re-evaluation of the latest locked submission.
- [ ] Worker pre-submit feedback is allowed for owned tasks in `in_progress`
      and `needs_revision`.
- [ ] Non-owning workers cannot precheck, resubmit, list or read submissions,
      read checker runs, or read audit events for another worker's
      `needs_revision` task, and those attempts create no rows or audit events.
- [ ] A worker can create a replacement submission after checker-caused
      `needs_revision`.
- [ ] Replacement submission increments the submission version.
- [ ] Older submission versions remain immutable and cannot receive new checker
      runs after a newer version exists.
- [ ] New submission versions stamp the same locked guide snapshot, effective
      project submission artifact policy hash, project pre-submit checker
      bundle hash, and post-submit checker policy context from the task.
- [ ] Fixed resubmission does not derive a new project submission artifact
      policy, compile a new project `PreSubmitCheckerPolicy`, create a
      task-specific checker bundle, or mutate the locked post-submit checker
      policy context.
- [ ] A clean initial submission moves through
      `submitted -> evaluation_pending -> review_pending`.
- [ ] A worker-fixable post-submit checker failure moves through
      `submitted -> evaluation_pending -> needs_revision` with
      `outcome_source = auto_checker` and no human review decision record.
- [ ] A fixed resubmission moves through
      `needs_revision -> submitted -> evaluation_pending -> review_pending`.
- [ ] Internal `task_setup_blocked` and `checker_retry` routes are not exposed
      as worker-facing task outcomes and keep the task in `evaluation_pending`
      until trusted repair or retry.
- [ ] Invalid setup before a durable checker run is created leaves no
      `CheckerRun`, no `CheckerResult`, no human review decision, no worker
      revision, and no fake success. Valid internal retry after a run starts
      remains internally auditable and never appears as a worker-facing outcome.
- [ ] Worker-facing checker-run detail, checker-run list, task response,
      submission response, and audit-event response surfaces do not expose
      internal-only checker route fields, `outcome_source`, review decision ids,
      internal locked policy/source/checker ids, hashes, bodies, trigger
      metadata, package hashes or URIs, artifact manifests, internal checker
      metadata, `routing_recommendation`, `allow_review`, `checker_retry`, or
      `task_setup_blocked`. The denylist includes all internal `locked_*`
      policy/source/checker ids, versions, hashes, bodies, and bundle hashes
      unless ADR 0010 explicitly makes a non-sensitive guide or policy version
      visible as revision context.
      This redaction does not remove the worker-visible revision context
      required by ADR 0010, including prior/next guide and policy versions,
      rebase reason, and change summary. It only redacts internal hashes,
      bodies, ids, routing/source fields, and private checker details.
- [ ] Worker-visible checker-caused `needs_revision` responses include stable
      result or finding ids, submission version, severity, `worker_message`, and
      suggested fix when available.
- [ ] Precheck and submission-create request bodies reject client-supplied
      `locked_*`, `outcome_source`, `routing_recommendation`,
      `trigger_source`, `review_decision_id`, `checker_retry`,
      `task_setup_blocked`, `allow_review`, and review-decision fields with no
      submission, checker-run, or audit side effects.
- [ ] Admin/project-manager surfaces retain enough audit detail to distinguish
      checker-caused `needs_revision` from future human-review-caused
      `needs_revision`, including `outcome_source = auto_checker`,
      `review_decision_id = null`, checker run id, submission id/version, audit
      event id, and superseded submission linkage for fixed resubmission.
- [ ] Real API drill covers clean pass, blocking pre-submit failure,
      post-submit checker-caused `needs_revision`, fixed resubmission, immutable
      older submissions, locked policy context, and `evaluation_pending`.

## Required Proof Scenarios

- Clean task: claim -> submit -> lock latest submission -> automatic
  post-submit evaluation starts in `evaluation_pending` -> checker pass ->
  `review_pending`.
- Blocking pre-submit: preflight and submission-create failure return
  `pre_submission_checker_failed`; no submission row, submission version,
  submitted transition, or durable checker run is created.
- Checker-caused revision: valid submission locks, enters `evaluation_pending`,
  post-submit checker finds worker-fixable failure, task becomes
  `needs_revision`, checker run records `outcome_source = auto_checker`, and no
  human review decision is created. The audit events prove
  `submitted -> evaluation_pending` and
  `evaluation_pending -> needs_revision`.
- Fixed resubmission: worker sees `needs_revision`, runs pre-submit feedback,
  submits version 2, version 1 remains immutable, version 2 stamps locked policy
  context, post-submit evaluation starts in `evaluation_pending`, and the fixed
  version reaches `review_pending`. The audit events prove
  `needs_revision -> submitted`, `submitted -> evaluation_pending`, and
  `evaluation_pending -> review_pending`.
- Trusted retry: a trusted actor re-runs post-submit evaluation for the latest
  locked submission already in `review_pending`; the audit events prove
  `review_pending -> evaluation_pending -> review_pending`, attempt
  supersession, and no worker-visible internal route leakage.
- Internal setup/retry route: project-manager-owned checker setup defect or
  retry condition remains internal in `evaluation_pending` and does not create
  fake worker revision, fake checker success, or fake human review decision.
- Ownership denial: a different worker cannot precheck, resubmit, read
  submission/checker/audit detail, or create side effects for an owned task that
  is in `needs_revision`.
- Real API drill scenario names must include `checker_caused_revision` and
  `fixed_resubmission` and must print or persist their invariant summaries.

## Verification Commands

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py tests/test_tasks.py
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week2_api_e2e.py
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
```

## Required Reviewers

Every listed reviewer must end with one exact result value:

- `PASS`
- `PASS AFTER FIXES`
- `PASS WITH LOW RISKS`
- `N/A - with approved reason`

Required:

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- test delta
- CI integrity

## Human Review Focus

- The `evaluation_pending` lifecycle status name and whether it correctly
  replaces `auto_checking`.
- Worker fairness during checker-caused revision and resubmission.
- Proof that fixed resubmission creates a new immutable version while preserving
  old version audit context.
- Proof that checker-caused `needs_revision` is audit-distinct from future
  human-review-caused `needs_revision`.
- Real API drill coverage using real Postgres-backed API calls.

## Stop Conditions

Stop and escalate if:

- revision resubmission requires implementing human review decisions
- post-submit checker routing cannot be made audit-distinct from human review
- `evaluation_pending` requires a broad lifecycle redesign outside this chunk
- auth, payment, reputation, settlement, frontend, or agent runtime scope
  becomes necessary
- tests or CI must be weakened to pass
- same blocker remains after 2 repair attempts
- secrets or production data are needed
