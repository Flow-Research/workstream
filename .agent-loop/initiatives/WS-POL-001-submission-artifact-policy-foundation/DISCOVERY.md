# Discovery: WS-POL-001 - Submission Artifact Policy Foundation

Discovery is read-only. No product implementation has started for this
initiative.

## Current Behavior

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

The backend is still transitional:

- `ProjectGuide.evidence_policy` represents submission artifact requirements.
- `WorkstreamTask.required_files` and `required_evidence` drive checker behavior.
- `Submission.locked_checker_policy_version` is used broadly for post-submit
  checker context.
- Pre-submit feedback uses `task.required_files` and `task.required_evidence`.
- Post-submit durable checks use registered checker names and locked checker
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
| `backend/app/modules/projects/models.py` | Project guide and policies | `ProjectGuide.evidence_policy` is transitional. |
| `backend/app/modules/projects/schemas.py` | Project guide API schemas | Exposes `evidence_policy` today. |
| `backend/app/modules/projects/service.py` | Guide activation and policy validation | Activation currently checks `evidence_policy` and checker policy. |
| `backend/app/modules/tasks/models.py` | Task/submission models | Task stores required files/evidence; submission stores broad checker policy version. |
| `backend/app/modules/tasks/service.py` | Task lifecycle and locked context | Stamps locked guide/policy context onto tasks/submissions. |
| `backend/app/modules/checkers/runner.py` | Checker implementations | Pre-submit and durable checks share helper logic today. |
| `backend/app/modules/checkers/service.py` | Pre-submit and durable checker orchestration | Needs to consume generated pre-submit policy later. |

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
