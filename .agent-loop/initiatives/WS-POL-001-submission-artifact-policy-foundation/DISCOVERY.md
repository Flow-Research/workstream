# Discovery: WS-POL-001 - Submission Artifact Policy Foundation

Discovery is read-only. No product implementation has started for this
initiative.

## Baseline Behavior Captured Before Implementation

The architecture docs already lock the target model:

```text
SubmissionArtifactPolicy
-> GuideSufficiencyReport
-> EffectiveProjectSubmissionArtifactPolicy
-> persisted project PreSubmitCheckerPolicy
-> tasks lock project policy/checker references
-> pre-submit checks before submission creation
-> post-submit/internal checks after submission lock
```

At initiative start, the backend was transitional:

- `ProjectGuide.evidence_policy` represented submission artifact requirements.
- `WorkstreamTask.required_files` and `required_evidence` drove checker behavior.
- `Submission.locked_checker_policy_version` was used broadly for post-submit
  checker context.
- Pre-submit feedback used `task.required_files` and `task.required_evidence`.
- Post-submit durable checks used registered checker names and locked checker
  policy.

The product ownership boundary is now locked. Project owners provide open-ended
project guide material and business terms. Workstream runs asynchronous internal
agents to evaluate guide sufficiency and derive machine-readable policy. The
project owner does not approve Workstream's internal policy controls.

## Relevant Files/Modules

| Path | Purpose | Notes |
|---|---|---|
| `docs/decision_0011_submission_artifact_policy_drives_pre_submit.md` | Accepted ADR for this initiative | Source of truth for policy-driven intake. |
| `docs/spec_chunk_5_submission_packet_foundation.md` | Submission packet target contract | Already says current code is transitional. |
| `docs/spec_chunk_8_submission_artifact_policy_checkers.md` | Pre-submit versus durable checker boundary | Names default pre-submit checks and routing. |
| `docs/spec_chunk_9_pre_review_gate.md` | Post-submit gate | Keeps internal checker routing separate from human review. |
| `backend/app/modules/projects/models.py` | Project guide and policies | `ProjectGuide.evidence_policy` was old construction state; `WS-POL-001-06` removes it from the current schema. |
| `backend/app/modules/projects/schemas.py` | Project guide API schemas | `WS-POL-001-06` removes `evidence_policy` and other legacy guide checklist fields from create/update/response contracts. |
| `backend/app/modules/projects/service.py` | Guide activation and policy validation | Chunk 1 moved activation authority to dedicated submission artifact policy records. |
| `backend/app/modules/tasks/models.py` | Task/submission models | Transitional task required files/evidence remain until the task locked-context chunk. |
| `backend/app/modules/tasks/service.py` | Task lifecycle and locked context | Later chunk migrates runtime authority to locked project policy/checker references. |
| `backend/app/modules/checkers/runner.py` | Checker implementations | Pre-submit and durable checks share helper logic until the runtime migration. |
| `backend/app/modules/checkers/service.py` | Pre-submit and durable checker orchestration | Later chunk consumes generated pre-submit policy at runtime. |

## Current Tests

| Test path | What it covers | Gaps |
|---|---|---|
| `backend/tests/test_projects.py` | Project guide activation and policy context | Does not test dedicated `SubmissionArtifactPolicy`. |
| `backend/tests/test_tasks.py` | Task lifecycle and assignment | Task required files/evidence remain transitional. |
| `backend/tests/test_submissions.py` | Submission packet creation/versioning | Does not yet prove effective policy provenance. |
| `backend/tests/test_checkers.py` | Pre-submit feedback, durable runs, routing | Uses task fields rather than generated pre-submit policy. |
| `backend/scripts/week2_api_e2e.py` | Real API checker/pre-review flow | Needs a future variant using dedicated policy records. |

## Dependencies/Integrations

- FastAPI async endpoints.
- SQLAlchemy 2.x async ORM.
- Alembic migrations.
- Pydantic schemas.
- Postgres as record database.
- Existing Flow token verification boundary.
- Existing checker runner registry.

## Risks Discovered

| Risk | Why it matters | Suggested handling |
|---|---|---|
| Policy/source drift | Guide prose, task fields, and checker policy can disagree. | Introduce policy objects first, then migrate runtime reads in later chunks. |
| Project owner-authored schema burden | Asking project owners to write Workstream policy schema creates setup errors and unfair worker failures. | Workstream derives policy from project material and requires approval by `admin` or `project_manager`. |
| Weakening defaults | Project policy could accidentally remove Workstream safety rules. | Implement non-bypassable default merge validation. |
| Big-bang rewrite | Changing project, task, submission, and checker runtime together is risky. | Split into reviewable chunks. |
| Version/hash ambiguity | Pre-submit policy is generated, so versioning needs careful naming. | Human review field names before migration. |
| Worker-facing confusion | Internal routes can leak if naming is sloppy. | Keep worker-facing state `needs_revision`; keep internal route fields internal. |

## Unknowns/Questions For Human

| Question | Why it matters | Needed before chunk? |
|---|---|---|
| Exact guide sufficiency report fields | Defines what the sufficiency agent proves before activation. | Yes, before implementation chunk 1 completes. |
| Exact policy provenance field names | Prevents future schema drift. | Yes, before schema migration. |
| Exact async agent execution shape | Affects background job orchestration. | No; chunk 1 can model records/contracts first. |

## Existing Conventions To Preserve

- Async-first FastAPI and SQLAlchemy.
- Router, service, repository, schema separation.
- No Workstream-owned login/session/auth.
- Postgres-backed integration tests for lifecycle behavior.
- Review decision stored values only `accept`, `needs_revision`, `reject`.
- Internal checker routes are not review decisions.
- CodeRabbit and CI supplement, but do not replace, internal reviewer tracks.

## Post-Actor-Registry Live API Drill Findings

The 2026-07-07 Terminal Benchmark live API drill completed through real HTTP
calls and proved the core setup and submission path:

```text
Flow-token auth
-> project create
-> guide/source snapshot create
-> Celery project setup
-> OpenAI Agents SDK sufficiency report
-> OpenAI Agents SDK submission artifact policy derivation
-> policy approval
-> effective project policy merge
-> deterministic project PreSubmitCheckerPolicy compilation
-> guide activation
-> task screen/release
-> worker profile activation
-> claim/start
-> pre-submit failure creates no submission
-> pre-submit pass creates submission
-> current submission lock route triggers pre-review gate
-> review_pending
```

The drill also exposed visibility gaps:

| Gap | Current state | Needed API behavior |
|---|---|---|
| Project setup run status | Celery returns task state, but Workstream does not persist a setup-run record. | Persist and expose latest setup run with status, current step, Celery task id, timestamps, and output ids. |
| Sufficiency report discovery | Creation and acknowledgement endpoints exist, but list/get read endpoints are missing. | Operators can list and inspect reports by API. |
| Submission artifact policy discovery | Create/update/approve endpoints exist, but list/get read endpoints are missing. | Operators can inspect the generated draft before approval without DB access. |
| Effective policy discovery | Approval response shows the effective policy, but there is no stable current-policy GET. | Operators can fetch current effective policy by project/guide. |
| Pre-submit checker policy discovery | Active guide response includes a summary, but no focused checker-policy GET exists. | Operators can fetch checker names, configs, compiler version, and compiled bundle hash. |
| Worker submission requirements | Workers can run pre-submit, but cannot fetch the exact required artifacts/evidence/attestation concepts first. | Worker-facing requirements endpoint shows the locked intake contract without internal-only compiler details. |
| Operator locked context | Some task responses redact or omit internal lock fields depending on actor. | Operator endpoint exposes full task locked provenance for support and drill verification. |
| Public submission lock wording | Public endpoint is `/submissions/{id}/lock`; the worker cannot call it and the name sounds like a storage action. | Replace with `/submissions/{id}/finalize` as the public handoff into pre-review gate. |
| Gate audit actor | Current lock/finalize requester appears as the actor on pre-review gate execution. | Use an internal Workstream system actor for checker gate execution while retaining requester provenance. |

Already-existing APIs from the desired drill surface:

- `POST /api/v1/tasks/{task_id}/submission-precheck`
- `GET /api/v1/submissions/{submission_id}/checker-runs`
- `GET /api/v1/checker-runs/{checker_run_id}`
- `GET /api/v1/tasks/{task_id}/audit-events`

These should stay covered by the new no-DB drill but do not need duplicate
routes.
