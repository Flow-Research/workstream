# Chunk Contract: WS-POL-002-02 - Post-Submit Derivation Agent And Resumable Setup Integration

## Parent Initiative

`WS-POL-002` - Post-Submit Checker Foundation

## Approved Plan Reference

- INTENT: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Problem Being Solved

Post-submit policy must be derived from project guide/source context instead of
being invented manually in guide request bodies. The derivation must run
asynchronously inside the project setup pipeline and stop cleanly when the
guide implies unsupported checker requirements.

## Goal

Add `PostSubmitCheckerPolicyDerivationAgent` and integrate it into the
resumable setup continuation that runs after v0.1 setup-authorized
admin/project_manager approval creates the effective submission artifact policy
and compiled project pre-submit checker bundle.

## Target Behavior

- Initial source-capture setup still stops at `policy_draft_ready`.
- Setup-authorized admin/project_manager approval of the submission artifact
  policy creates the effective policy and compiled pre-submit bundle, then
  enqueues or resumes post-submit derivation.
- Post-submit derivation runs only after effective submission artifact policy
  and pre-submit checker bundle are available.
- Agent input includes guide source snapshot, sufficiency summary, effective
  policy summary, pre-submit checker summary, and registered post-submit
  checker catalog.
- Agent output is a constrained spec, not executable runtime code.
- Unsupported required checks are recorded as setup blockers.
- Successful derivation passes through the trusted compiler and creates a
  compiled project post-submit policy pending setup approval.
- Setup run status makes post-submit derivation/compile state visible.
- Hostile guide/source instructions that attempt to weaken Workstream defaults,
  roles, routing, authorization, or review decisions are ignored or rejected.
- Persisted derivation summaries are bounded and redacted; raw source text,
  local paths, secrets, signed refs, and exact source hashes are not returned in
  setup APIs by default.

## Contract Amendment

During implementation review, the chunk was explicitly kept as one L1
implementation slice rather than split because post-submit derivation cannot be
made durable without the project-agent interface contract and the database
provenance migration. The allowed files therefore include
`backend/app/interfaces/project_agents.py` and `backend/alembic/versions/**`.
Those files may only be changed for this chunk's derivation contract,
setup-run output state, and generated post-submit policy provenance; they must
not introduce runtime submission judgment or per-task checker generation.
Internal docs review also required README and glossary alignment after the
post-submit continuation became part of automatic project setup. Those docs may
only be changed to describe the new setup continuation at a high level.

Post-review CI repair exposed stale task/checker fixtures and real API drill
setup bridges that still assumed manual guide-body post-submit policy fields.
The allowed scope therefore also includes the test and e2e files listed below,
but only to remove that legacy request-body shape, keep activation fixtures
aligned with generated post-submit setup output, and make the temporary CI
activation bridge explicit until `WS-POL-002-03` adds the server-owned approval
API. These files must not introduce product runtime shortcuts or skip the
project setup continuation tests in `backend/tests/test_projects.py`.

During the post-submit API drill review, the user rejected a manual
manager-owned submission handoff. The normal product flow is now: assigned
contributor submits a packet, Workstream reruns pre-submit authoritatively
against that exact payload, Workstream stamps the immutable submission
boundary, and the server-owned pre-review gate runs through Celery. The allowed
scope therefore also includes the narrow task/checker runtime files needed to
keep manager action out of the happy path. This amendment must not add runtime
agent judgment, reviewer lifecycle behavior, or payment/reputation behavior.
Internal architecture review also required the automatic pre-review gate's
compare-and-set persistence primitives to sit behind the checker repository
boundary instead of inside the checker service. The allowed scope therefore
includes `backend/app/modules/checkers/repository.py`, but only for atomic
automatic pre-review gate persistence methods. Lifecycle decisions remain in
`CheckerService`.
Product/ops review found stale architecture wording that still described
artifact locking and `/finalize` as the normal submission handoff. The allowed
scope therefore also includes `docs/architecture_system_architecture.md`, but
only to align lifecycle wording with the implemented contributor-owned
submission lock and repair-only automatic gate finalization boundary.
Reuse/dedup review required that requester-provenance and Celery task-setting
helpers be shared so the task enqueue path, checker worker validation path,
and setup queue path do not drift. The allowed scope therefore also includes
`backend/app/modules/checkers/pre_review_gate.py` and
`backend/app/workers/task_settings.py`, limited to shared automatic-gate
provenance and worker task-setting contracts.

## Allowed Files

```text
backend/app/adapters/project_agents/**
backend/app/interfaces/project_agents.py
backend/app/modules/checkers/gate_queue.py
backend/app/modules/checkers/pre_review_gate.py
backend/app/workers/project_setup.py
backend/app/workers/async_runner.py
backend/app/workers/checkers.py
backend/app/workers/celery_app.py
backend/app/workers/task_settings.py
backend/app/modules/projects/setup_queue.py
backend/app/modules/projects/router.py (docstring-only stale OpenAPI wording cleanup)
backend/app/modules/projects/service.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/tasks/service.py
backend/app/modules/tasks/router.py (docstring-only stale OpenAPI wording cleanup)
backend/app/modules/checkers/service.py
backend/app/modules/checkers/compiler.py
backend/app/modules/checkers/repository.py
backend/alembic/versions/**
backend/tests/test_projects.py
backend/tests/test_agent_runtime.py
backend/tests/test_alembic.py
backend/tests/test_tasks.py
backend/tests/test_checkers.py
backend/scripts/api_contract_e2e.py
backend/scripts/week2_api_e2e.py
examples/terminal_benchmark/terminal_benchmark_api_e2e.py
README.md
docs/architecture_checker_framework.md
docs/architecture_data_model.md
docs/architecture_system_architecture.md
docs/glossary.md
docs/operations_project_operating_manual.md
docs/operations_roles_permissions.md
docs/spec_chunk_5_submission_packet_foundation.md
docs/spec_chunk_9_pre_review_gate.md
docs/spec_week2_checker_framework.md
docs/roadmap_day_by_day_execution_plan.md
docs/roadmap_status.md
docs/diagrams/task_lifecycle_sequence.md
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not Allowed

```text
backend/app/modules/tasks/** except backend/app/modules/tasks/service.py
backend/app/modules/checkers/** except backend/app/modules/checkers/service.py, backend/app/modules/checkers/gate_queue.py, backend/app/modules/checkers/pre_review_gate.py, backend/app/modules/checkers/compiler.py, and backend/app/modules/checkers/repository.py
frontend or demo UI work
payment/reputation/blockchain settlement
per-task checker generation
runtime agent-based submission judgment
```

## Acceptance Criteria

- The setup continuation invokes post-submit derivation only after v0.1
  setup-authorized admin/project_manager approval creates the effective
  submission artifact policy and compiled project pre-submit checker bundle.
- Blocked guide sufficiency prevents post-submit derivation.
- Unsupported required checker gaps block setup and are visible to operators.
- Successful derivation creates a compiled project `PostSubmitCheckerPolicy`
  without treating compilation as setup approval.
- Guide activation rejects compiled-only post-submit checker policies until a
  server-owned setup approval path records approval provenance.
- The compiled `PostSubmitCheckerPolicy` is bound to guide id, source snapshot
  id/hash, effective project policy id/hash, and pre-submit checker policy
  id/hash; setup-run and activation validation reject project/version-only
  matches.
- Agent prompt/instructions explicitly forbid arbitrary checker code and
  per-task checker generation.
- Tests include malicious guide/source excerpts and prove source text is treated
  as data, not authority.
- Returned spec reasons must be tied to bounded source evidence references.
- API-visible setup summaries redact secrets, local paths, replayable refs, and
  exact source hashes.
- Tests cover success, unsupported checker gap, and setup ordering.
- Tests prove the setup trigger boundary: no post-submit derivation before
  submission artifact policy approval/pre-submit compile, and exactly one
  post-submit setup continuation after that point.
- Implementation extends the existing project setup queue/worker boundary in
  `setup_queue.py` and `project_setup.py`; it must not create a disconnected
  post-submit-only queue or parallel pipeline.
- Assigned contributor submission creation locks the submitted packet after
  authoritative server-side pre-submit validation and enqueues the Celery
  pre-review checker gate with requester provenance.
- The existing finalize route remains idempotent/manual-repair only; repeated
  calls must not create duplicate checker runs or audit events.

## Verification Commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
(cd backend && .venv/bin/pytest tests/test_projects.py tests/test_agent_runtime.py -q)
(cd backend && .venv/bin/pytest tests/test_alembic.py -q)
git diff --check
```

## Required Reviewers

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

- Confirm the agent derives setup policy only.
- Confirm unsupported checker requirements fail closed.
- Confirm no runtime submission judgment is delegated to an agent.

## Stop conditions

Stop and escalate if:

- scope must expand beyond allowed files
- architecture direction changes
- auth/payment/policy/data boundary changes beyond this contract
- CI/test weakening is required to pass
- the same blocker remains after 2 repair attempts
- secrets or production data are needed
