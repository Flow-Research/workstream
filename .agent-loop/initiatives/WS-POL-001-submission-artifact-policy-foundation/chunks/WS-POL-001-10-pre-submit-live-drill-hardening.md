# Chunk Contract: WS-POL-001-10 - Pre-Submit Live Drill Hardening

## Parent initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Fix the concrete pre-submit setup and intake gaps found during the real
Terminal Benchmark API drill, without expanding into post-submit review,
revision, payment, or agent-runtime redesign.

## Why this chunk exists

The live drill proved the project guide -> agent setup -> policy approval ->
task lock -> pre-submit path, but it also exposed several places where the API
still behaved like an internal test harness instead of a real operator/worker
workflow. This chunk hardens those seams before we continue post-submit work.

## Approved plan reference

- INTENT:
  `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- PLAN:
  `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- CHUNK_MAP:
  `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/tasks/router.py
backend/app/modules/tasks/schemas.py
backend/app/modules/tasks/service.py
backend/tests/test_projects.py
backend/tests/test_tasks.py
docs/architecture_data_model.md
docs/architecture_lockdown.md
docs/decision_0011_submission_artifact_policy_drives_pre_submit.md
docs/spec_chunk_4_task_queue_assignment.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-10-pre-submit-live-drill-hardening.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-10-*
```

## Not allowed

```text
backend/alembic/**
backend/app/adapters/project_agents/**
backend/app/interfaces/project_agents.py
backend/app/modules/checkers/**
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/tasks/models.py
backend/app/modules/tasks/repository.py
docs/** except the explicitly allowed files above
.github/workflows/**
demos/**
frontend/**
review lifecycle implementation
revision lifecycle implementation
payment/reputation/blockchain code
post-submit checker policy redesign
agent runtime provider replacement
new scripts or fake local fixtures
```

## Acceptance criteria

- [ ] Duplicate guide versions return a mapped conflict response instead of an
      unhandled database error.
- [ ] Project guide creation can include source-snapshot items, including
      representative task examples, so the automatic sufficiency and derivation
      agents receive the same material captured at guide setup time.
- [ ] The active-guide response exposes project pre-submit checker names and
      checker configs, while still excluding the compiled checker bundle body.
- [ ] Workers can create or refresh their own active worker profile through a
      public authenticated worker API before claiming a task; workers without a
      profile remain blocked from claiming.
- [ ] A failed pre-submit submission attempt creates no submission version but
      writes a durable task audit event containing the structured checker
      result for project operators.
- [ ] Request bodies remain fail-closed through Pydantic `extra="forbid"`; no
      legacy project guide artifact fields are reintroduced.

## Verification commands

```bash
cd backend && .venv/bin/python -m ruff check app/modules/projects/schemas.py app/modules/projects/service.py app/modules/tasks/router.py app/modules/tasks/schemas.py app/modules/tasks/service.py tests/test_projects.py tests/test_tasks.py
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'duplicate_guide_version_returns_conflict or guide_creation_accepts_source_snapshot_items_for_agent_material or guide_activation_and_active_guide_retrieval' -q
cd backend && .venv/bin/python -m pytest tests/test_tasks.py -k 'worker_can_create_profile_before_claiming_task or worker_without_profile_cannot_claim_ready_task or pre_submit_failure_writes_audit_event_without_submission' -q
cd backend && .venv/bin/docstr-coverage app/modules/projects app/modules/tasks --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Every listed reviewer must end with one exact result value:

- `PASS`
- `PASS AFTER FIXES`
- `PASS WITH LOW RISKS`
- `N/A - with approved reason`

Required:

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

- The worker profile endpoint is authenticated and worker-owned, not a hidden
  seed path.
- Guide creation source items are captured as immutable snapshot material and
  do not revive legacy guide-owned artifact fields.
- Failed pre-submit attempts remain user-facing as
  `pre_submission_checker_failed`, create no submission row, and leave operator
  audit evidence.
- Active-guide output gives enough checker visibility for operators without
  leaking the compiled bundle body.

## Stop conditions

Stop and escalate if:

- fixing any item requires database migrations
- the project-agent runtime contract needs to change
- post-submit/review/revision/payment scope is required
- tests or CI must be weakened to pass
- same blocker remains after 2 repair attempts
- secrets or production data are needed
