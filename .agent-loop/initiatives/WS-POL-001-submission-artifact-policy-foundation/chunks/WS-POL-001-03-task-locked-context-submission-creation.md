# Chunk Contract: WS-POL-001-03 - Task Locked Context And Submission Creation

## Parent Initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Move task readiness and submission creation onto the locked project guide-source
snapshot, effective project submission artifact policy, and compiled project
`PreSubmitCheckerPolicy` bundle.

This chunk preserves the project-scoped checker architecture. Tasks lock
references to the active project context. Tasks do not run policy derivation and
do not compile their own checker bundle.

## Why This Chunk Exists

Chunk 1 created the records and activation guards for the guide-policy bundle.
Chunk 2 added async guide sufficiency / derivation agents and the trusted
project pre-submit checker compiler.

The remaining runtime gap is task/submission authority. The system still has
transitional task-level `required_files` and `required_evidence` fields from the
earlier submission-packet foundation. Chunk 3 makes task readiness and
submission creation use the locked project context instead of those transitional
fields.

## Risk Class

L1

## SLA

P1

## Implementation Allowed Files

```text
backend/alembic/versions/**
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/test_tasks.py
backend/tests/test_checkers.py
backend/tests/test_projects.py
backend/scripts/week1_api_e2e.py
backend/scripts/week2_api_e2e.py
docs/architecture_data_model.md
docs/spec_chunk_5_submission_packet_foundation.md
docs/spec_chunk_7_checker_runner_registry.md
docs/template_checker_policy.md
docs/template_submission_packet.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

## Implementation Not Allowed

```text
human review implementation
payment/reputation/blockchain code
frontend
object-storage implementation
project-agent runtime redesign
new checker derivation or compilation per task
free-form task runtime parameter map
Workstream-owned login, signup, password, auth session, or API key auth
```

`backend/app/modules/projects/models.py` and `backend/tests/test_projects.py`
are included only to bind `PreSubmitCheckerPolicy.id` to
`compiled_bundle_hash` as a composite FK target for locked task/submission
provenance. `backend/app/modules/projects/repository.py` is included only for
read-only locked effective-policy and pre-submit checker policy loaders so the
checker service does not query project persistence tables directly. These
project-module changes must not change guide activation behavior or project
setup flow in this chunk.

The architecture/template docs are included only to align locked task and
submission provenance wording with the implemented v0.1 fields and public
`pre_submission_checker_failed` contract. `docs/spec_chunk_7_checker_runner_registry.md`
is included only for stale pre-submit/post-submit wording discovered during
internal product/ops review; it must not change checker behavior in this chunk.

`backend/scripts/week1_api_e2e.py` is included only to keep the real HTTP CI
drill aligned with the locked project pre-submit checker policy. The script
must submit evidence and attestation data that satisfy the current effective
policy instead of relying on transitional task fields.

## Implementation Boundaries

- Project setup remains project-scoped:
  `GuideSourceSnapshot -> GuideSufficiencyReport -> SubmissionArtifactPolicy ->
  EffectiveProjectSubmissionArtifactPolicy -> project PreSubmitCheckerPolicy`.
- Task readiness must lock references to the active project context before a
  task enters `READY`.
- Every task under the same active project guide version shares that guide
  version's project `PreSubmitCheckerPolicy`.
- Task-specific values are constrained server-owned task-contract fields
  consumed by the locked checker bundle. They are not a second policy channel.
- Submission creation must run pre-submit checks before inserting a submission
  row or creating a submission version.
- Blocking pre-submit failure is not a product review decision. It returns
  `pre_submission_checker_failed` and creates no submission.
- Pre-submit checks are draft-packet intake checks and must not create durable
  post-submit `CheckerRun` records.
- Post-submit/internal checker policy split stays deferred to `WS-POL-001-04`.
- Revision resubmission drill stays deferred to `WS-POL-001-05`.

## Acceptance Criteria

- [ ] Tasks lock `locked_guide_source_snapshot_id`,
      `locked_guide_source_snapshot_hash`,
      `locked_effective_project_submission_artifact_policy_hash`, and
      `locked_pre_submit_checker_bundle_hash` during screening before `READY`.
- [ ] Every task under the same active project guide version shares that guide
      version's project `PreSubmitCheckerPolicy`.
- [ ] Tasks do not run submission artifact policy derivation.
- [ ] Tasks do not compile checker bundles.
- [ ] If a guide version does not cover the task set, activation remains blocked
      and the guide must be improved or the work split into another
      project/guide.
- [ ] Task-specific values are constrained parameters from trusted task-contract
      fields only.
- [ ] No free-form task runtime parameter map is introduced.
- [ ] Transitional `required_files` and `required_evidence` are replaced for
      submission runtime and are not compatibility aliases.
- [ ] Blocking pre-submit failure creates no submission row, no submission
      version, no submitted transition, and no durable checker run.
- [ ] `POST /tasks/{id}/submission-precheck` returns `200
      PreSubmitCheckResponse` with `status`, `eligible_to_submit`, and
      `results`.
- [ ] `POST /tasks/{id}/submissions` returns `422
      DomainError(code="pre_submission_checker_failed")` with structured
      pass/fail/warning details when blocking pre-submit fails.
- [ ] Passing pre-submit creates a submission stamped with locked policy
      context.

## Verification Commands

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_tasks.py tests/test_checkers.py tests/test_projects.py
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
- CI integrity

## Human Review Focus

- Task locked context fields and when they are stamped.
- Shared project checker reuse across tasks.
- No-row/no-version/no-transition guarantee on blocking pre-submit failure.
- Separation between `submission-precheck` response and failed submission-create
  domain error.
- Assurance that transitional task `required_files` and `required_evidence` no
  longer drive submission runtime.
