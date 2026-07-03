# Chunk Contract: WS-POL-001-04 - Post-Submit Checker Policy Provenance

## Parent Initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Separate post-submit checker policy naming and provenance from project
pre-submit checker policy and from the transitional
`locked_checker_policy_version` field.

This chunk keeps pre-submit intake stable from `WS-POL-001-03`: pre-submit
checks run before submission creation and do not create durable checker runs.
It makes post-submit/internal checker runs explicitly bind to locked
post-submit checker policy context after a valid submission exists.

## Why This Chunk Exists

Chunks 1 through 3 established the project guide/source/policy foundation,
async agent and compiler runtime, task locked context, and pre-submit execution
before submission creation.

The remaining checker provenance gap is that durable checker runs still use
broad checker-policy naming that can be confused with pre-submit checker
policy. Workstream needs deterministic audit records that say exactly which
post-submit checker policy governed each internal checker run, while keeping
worker-facing pre-submit feedback separate from review decisions and durable
post-submit checks.

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
backend/app/db/models.py
backend/app/modules/projects/**
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/scripts/week1_dry_run.py
backend/scripts/week1_api_e2e.py
backend/scripts/week2_api_e2e.py
backend/tests/**
docs/spec_chunk_3_project_guide_foundation.md
docs/spec_chunk_5_submission_packet_foundation.md
docs/spec_chunk_8_submission_artifact_policy_checkers.md
docs/spec_chunk_9_pre_review_gate.md
docs/architecture_checker_framework.md
docs/architecture_data_model.md
docs/operations_queue_policy.md
docs/product_first_user_flows.md
docs/roadmap_status.md
docs/template_checker_policy.md
docs/template_submission_packet.md
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

The chunk map lists the product docs required for the post-submit checker split.
This contract also allows architecture/checker template docs and loop files
because this chunk is a naming and provenance correction. Those files may only
be changed to align authoritative `PostSubmitCheckerPolicy` wording, loop
status, evidence, and PR trust artifacts for this chunk.

## Implementation Not Allowed

```text
human review decision implementation
revision resubmission workflow implementation
payment/reputation/blockchain code
frontend or demo UI changes
object-storage implementation
auth provider changes
agent runtime redesign
pre-submit checker derivation redesign
per-task checker compilation
new worker-facing task outcome values
Workstream-owned login, signup, password, auth session, or API key auth
```

## Implementation Boundaries

- Pre-submit checker policy remains project scoped and compiled from the
  effective project submission artifact policy.
- Pre-submit feedback remains draft-packet intake feedback. It must not create
  durable `CheckerRun` records and must not store product review decision
  values.
- `PostSubmitCheckerPolicy` is the authoritative model/schema/service/API
  naming for the durable checker policy used after a submission exists. The
  current generic `CheckerPolicy`/`checker_policies` runtime authority must be
  renamed or explicitly demoted to legacy non-authoritative compatibility.
- The canonical lock path is task -> submission -> checker run: task screening
  locks the active post-submit policy id, version, and immutable policy hash;
  submission creation stamps that locked context from the task; a durable
  `CheckerRun` records the submission-stamped post-submit policy context it
  executed.
- Durable checker runs must bind to locked post-submit checker policy context,
  not to pre-submit checker bundle provenance and not to broad
  `locked_checker_policy_version` authority.
- Workers must not see internal-only checker routing fields or post-submit
  route names through worker-facing APIs. Worker-facing task/submission status
  may still be the canonical product status `needs_revision` when post-submit
  checks find worker-fixable failures.
- Stored product review decisions remain exactly `accept`, `needs_revision`,
  and `reject`; this chunk must not add review decision states.
- `WS-POL-001-05` owns revision resubmission and real API drill proof.

## Acceptance Criteria

- [ ] Pre-submit policy provenance and post-submit policy provenance are
      distinct in schema, service code, tests, and docs.
- [ ] Task screening locks explicit
      `locked_post_submit_checker_policy_id`,
      `locked_post_submit_checker_policy_version`, and
      `locked_post_submit_checker_policy_hash` values plus the immutable
      `locked_post_submit_checker_policy_body` from the active project
      post-submit policy.
- [ ] The locked post-submit checker policy body includes the complete durable
      checker execution list, including Workstream default durable checkers,
      project required checkers, warning checkers, and blocking severities.
      Durable checker execution uses that locked body, not a live service
      constant or mutable project setup row.
- [ ] Submission creation stamps the post-submit policy context from the task,
      and durable `CheckerRun` rows stamp the same post-submit policy context
      from the submission.
- [ ] Durable checker runs record the locked post-submit checker policy context
      they used.
- [ ] Later mutable project policy changes do not affect task, submission, or
      checker-run provenance that was already locked.
- [ ] Task readiness, submission creation, submission locking, checker-run
      creation, and gate routing fail closed when locked post-submit policy
      context is missing, mismatched, ambiguous, deleted, or unauthorized.
- [ ] Missing or invalid locked post-submit policy context creates no fake
      durable `CheckerRun`, no `CheckerResult`, no review-pending transition,
      and no worker-revision transition; it returns a structured setup/policy
      error.
- [ ] Pre-submit feedback still creates no durable `CheckerRun` records.
- [ ] Pre-submit feedback persistence cannot store review decision fields. If a
      shared shape is unavoidable, review decision fields are enforced empty.
- [ ] Worker-facing checker-run detail, checker-run list, task response,
      submission response, and audit-event response surfaces do not expose
      internal-only checker routes, post-submit routing internals, human review
      decision records, review decision ids, `allow_review`, `checker_retry`,
      `task_setup_blocked`, or locked post-submit policy provenance fields.
- [ ] Worker-facing APIs may expose the canonical product task/submission
      status `needs_revision`; that status is not treated as an internal route
      field.
- [ ] Existing `submission-precheck` and failed submission-create behavior from
      `WS-POL-001-03` remains unchanged.
- [ ] Migration names and ORM fields use `post_submit_checker_policy` wording,
      not vague `checker_policy` wording for new provenance.
- [ ] Transitional broad `locked_checker_policy_version` authority is removed
      from durable checker-run provenance or retained only as admin-visible
      legacy context with tests proving new code uses the
      `locked_post_submit_checker_policy_*` fields.
- [ ] Migration tests prove existing v0.1 rows are backfilled, renamed, or
      rejected safely before explicit post-submit policy provenance is enforced.
      Because there is no production data yet, a documented migration preflight
      that blocks legacy non-draft task, submission, or checker-run rows is
      acceptable when tested. Legacy checker policy definitions without hashes
      may remain unauthoritative.

## Required Proof Scenarios

- Task screening stamps post-submit policy id, version, and hash.
- Submission creation and checker-run creation preserve the same post-submit
  policy id, version, and hash.
- Project post-submit policy mutation after lock does not alter existing task,
  submission, or checker-run provenance.
- Client-supplied post-submit policy fields are rejected.
- Missing or mismatched post-submit policy context fails closed without durable
  checker-run/result rows or task routing.
- Worker checker-run list/detail, task, submission, and audit responses omit
  internal route fields and forbidden internal route tokens.

## Verification Commands

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py tests/test_tasks.py tests/test_projects.py
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests
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

## Human Review Focus

- New post-submit checker policy field names and migration safety.
- Proof that durable checker runs use post-submit policy provenance.
- Proof that pre-submit feedback still creates no durable checker runs.
- Proof that worker-facing APIs do not expose internal checker routing or
  review-decision-like values.
- Assurance that revision resubmission and human review decisions remain out of
  scope for this chunk.

## Stop Conditions

Stop and escalate if:

- post-submit checker policy cannot be split without redesigning task or
  project activation architecture
- human review decision behavior must change
- revision resubmission behavior must be implemented to satisfy this chunk
- auth, payment, reputation, settlement, or frontend scope becomes necessary
- CI/test weakening is required to pass
- same blocker remains after 2 repair attempts
- secrets or production data are needed
