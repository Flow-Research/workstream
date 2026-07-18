# Chunk Contract: WS-POL-001-08 - Celery Project Setup Pipeline

## Parent Initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Replace manual pre-submit setup trigger calls with a Celery-backed project setup
pipeline.

When a draft project guide receives an immutable guide-source snapshot,
Workstream enqueues the pre-submit setup pipeline automatically:

```text
GuideSourceSnapshot
-> ProjectGuideSufficiencyAgent
-> stop if blocked
-> SubmissionArtifactPolicyDerivationAgent
-> draft SubmissionArtifactPolicy ready for admin/project_manager review
```

Policy approval still remains a human Workstream action. Approval compiles the
deterministic project `PreSubmitCheckerPolicy` through the existing compiler.

## Why This Chunk Exists

The current backend can run the sufficiency agent and derivation agent, but only
through explicit API trigger routes. That does not match the locked product
intent. Project setup should run automatically after guide material is captured,
and project owners should not need to know internal Workstream trigger endpoints.

This chunk switches project setup background execution to Celery. FastAPI
background tasks are not used for this path.

## Risk Class

L1

## SLA

P1

## Implementation Allowed Files

```text
backend/pyproject.toml
backend/app/core/config.py
backend/app/db/session.py
backend/app/schemas/auth.py
backend/app/modules/projects/**
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/app/workers/**
backend/scripts/week1_api_e2e.py
backend/scripts/week2_api_e2e.py
backend/alembic/versions/**
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/tests/test_tasks.py
backend/tests/test_checkers.py
demos/week1_api_demo_ui/src/api.ts
docker-compose.yml
README.md
docs/architecture_system_architecture.md
docs/decision_0007_async_first_execution.md
docs/decision_0011_submission_artifact_policy_drives_pre_submit.md
docs/product_first_user_flows.md
docs/internal_reviews/**
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

## Implementation Not Allowed

```text
backend/app/modules/submissions/**
backend/app/adapters/auth/**
.github/workflows/**
frontend/**
payment/reputation/blockchain code
post-submit lifecycle redesign
review/revision lifecycle redesign
```

## Implementation Boundaries

- The setup pipeline starts after source material is snapshotted, not from
  mutable guide prose alone.
- `ProjectService.create_guide` may create the initial server-owned guide
  source snapshot for the guide body and enqueue setup.
- `ProjectService.create_guide_source_snapshot` must enqueue setup for the new
  latest snapshot.
- Celery is the background execution boundary for this pipeline.
- The HTTP request must not run the project setup agents inline.
- The pipeline uses a Workstream-owned internal actor for server-owned setup
  provenance. It does not impersonate the project owner or worker.
- Blocking guide sufficiency stops the pipeline before submission artifact
  policy derivation.
- Passing or warning sufficiency allows derivation, but warnings still require
  human acknowledgement before policy approval or guide activation.
- Derived submission artifact policy remains draft until a human
  `admin`/`project_manager` approves it.
- Approval and checker compilation continue through the existing
  `approve_submission_artifact_policy` path.
- Existing explicit trigger routes may remain for development and repair, but
  the normal project setup path must not depend on manually calling them.
- Because Workstream is still in construction, discarded request fields,
  migration aliases, wrapper names, and proposal source files are removed rather
  than supported for compatibility. The only accepted references to removed
  column names are negative schema assertions proving they are absent.

## Acceptance Criteria

- [ ] Celery is declared as the durable worker dependency for project setup.
- [ ] Local Docker Compose includes a broker suitable for Celery local dev.
- [ ] Project setup Celery configuration is explicit and documented.
- [ ] Creating a guide creates or binds an immutable source snapshot for the
      guide body and enqueues the setup pipeline.
- [ ] Creating a later source snapshot enqueues the setup pipeline for that
      latest snapshot.
- [ ] The enqueue step is idempotent and does not create duplicate reports or
      policies for the same source snapshot.
- [ ] The Celery task runs `ProjectGuideSufficiencyAgent`.
- [ ] If sufficiency is `blocked`, no `SubmissionArtifactPolicy` is created.
- [ ] If sufficiency is `passed` or `passed_with_warnings`, the derivation agent
      creates a draft `SubmissionArtifactPolicy`.
- [ ] The pipeline does not approve the policy or activate the guide.
- [ ] Tests prove the HTTP request path does not call the agent runtime inline.
- [ ] Tests prove eager Celery execution can exercise the full automatic
      pipeline deterministically.
- [ ] Tests prove blocked guide material stops before derivation.
- [ ] Tests prove a normal guide reaches draft derived policy without manual
      sufficiency or derivation route calls.
- [ ] Current schema and API request bodies keep no compatibility aliases for
      removed project payment fields, guide checklist fields, task-owned
      artifact fields, generic checker-policy locks, or discarded lifecycle
      states.

## Verification Commands

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py
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

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- test delta
- CI integrity

CI integrity is required because this chunk changes backend dependencies and
local worker infrastructure.

## Human Review Focus

- Whether project setup now runs automatically from guide/source capture.
- Whether Celery, not FastAPI background tasks, owns the setup worker boundary.
- Whether blocked guide sufficiency stops derivation.
- Whether policy approval remains human-owned.
- Whether post-submit/review/revision/payment lifecycle is intentionally not
  redesigned in this chunk.
