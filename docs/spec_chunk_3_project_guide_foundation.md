# Chunk 3 Project And Guide Foundation Spec

## Scope

Build the Workstream v0.1 project and guide foundation.

This chunk creates the first domain module for projects, versioned project guides, submission artifact policy, checker policies, review policies, revision policies, and payment policies. It implements the backend rules needed before tasks can lock a guide and policy context.

## Non-Scope

- frontend
- external source adapters
- checker execution
- task queue and assignment
- submission packet logic
- review workflow
- payment execution
- reputation records

Revision workflow execution is not in this chunk, but revision policy is in scope. The project-guides ADR requires every active guide to drive revision policy, so this chunk stores and validates the revision-policy contract before a guide can become active.

## Expected Files And Modules

- `backend/app/modules/projects/models.py`
- `backend/app/modules/projects/schemas.py`
- `backend/app/modules/projects/repository.py`
- `backend/app/modules/projects/service.py`
- `backend/app/modules/projects/router.py`
- `backend/alembic/versions/0002_project_guide_foundation.py`
- `backend/alembic/versions/0006_submission_artifact_policy_foundation.py` (revision `0006_submission_policy`)
- `backend/tests/test_projects.py`

## Architecture Requirements

- Routers handle HTTP only.
- Services own activation, validation, and permission rules.
- Repositories own SQLAlchemy database access.
- Models use SQLAlchemy 2.x async-compatible mappings.
- API contracts use Pydantic schemas.
- Routes use the current actor dependency from Chunk 2.
- Permission checks live in the service layer.

## Data Model Impact

Architecture target:

- `projects`
- `project_guides`
- `guide_sufficiency_reports`
- `submission_artifact_policies`
- `effective_project_submission_artifact_policies`
- `pre_submit_checker_policies`
- `checker_policies`
- `review_policies`
- `revision_policies`
- `payment_policies`

Current v0.1 implementation note: the first project-guide foundation stores submission artifact requirements in `ProjectGuide.evidence_policy`. That is old construction state. The target replacement is `SubmissionArtifactPolicy`; no compatibility alias is required.

There is no automatic backfill from `ProjectGuide.evidence_policy` into
`SubmissionArtifactPolicy`. Existing local draft guides must create a fresh
guide source snapshot, guide sufficiency report, approved submission artifact
policy, effective project submission artifact policy, and project
`PreSubmitCheckerPolicy` contract before activation. Already-active task policy
context is not silently rewritten.

The guide version is the join key for the guide-specific policies.

Project guide activation requires:

- guide is still draft
- immutable guide source snapshot exists for the exact source material being activated
- guide sufficiency report is passed or warnings are acknowledged by `admin` or `project_manager`
- Workstream-derived submission artifact policy is approved for the guide version with `admin` or `project_manager` approval provenance
- effective project submission artifact policy hash exists for the guide source snapshot
- project pre-submit checker policy is compiled for the effective project policy
  and has a persisted compiled bundle hash
- post-submit checker policy exists for the guide version
- review policy exists for the guide version
- revision policy exists for the guide version
- payment policy exists for the guide version
- revision policy has max revision rounds, revision deadline hours, and allowed resubmission states
- payment policy has base amount, currency, payout type, and accepted payment rule

Implementation sequencing: Chunk 1 models the project pre-submit checker
dependency and fails activation unless compiler-owned compiled bundle fields are
present. Chunk 2 adds the trusted compiler path that writes those fields.

Activating a new guide supersedes the prior active guide for that project without mutating its content.

## Revision Policy

Revision policy is a first-class guide-version policy, as required by the project-guides ADR. It defines how Workstream will later enforce the `needs_revision` loop after a reviewer requests changes.

The v0.1 contract records:

- maximum revision rounds
- revision deadline in hours
- whether the task automatically rejects after the revision limit
- states that allow resubmission
- reviewer reassignment rule

Activation requires a revision policy before the guide can become active. The active guide response returns revision policy beside submission artifact policy, checker policy, review policy, and payment policy so future task records can lock the full policy context. The Non-Scope section keeps only revision workflow execution out of this chunk, not revision policy itself.

## Submission Artifact Policy

Submission artifact policy is a first-class guide-version policy. It defines what a worker must submit before Workstream creates a submission packet.

The architecture contract is:

```text
EffectiveProjectSubmissionArtifactPolicy =
  WorkstreamDefaultSubmissionArtifactPolicy
  + SubmissionArtifactPolicy
```

Workstream generates, persists, and locks a project `PreSubmitCheckerPolicy`
contract bound to the effective project submission artifact policy hash. The
approval path compiles the deterministic checker bundle and stores lifecycle
status `compiled`. Tasks later lock the applicable guide snapshot, effective
project submission artifact policy hash, and compiled pre-submit checker bundle
hash. Blocking pre-submit failures prevent submission creation.

Implementation note: the first v0.1 schema stored this as `ProjectGuide.evidence_policy`. That field is old construction state and is replaced by the dedicated policy table/API path.

## API Impact

Adds protected v1 routes:

- `POST /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/guides`
- `PATCH /api/v1/projects/{project_id}/guides/{guide_id}`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots/{source_snapshot_id}/run-sufficiency-agent`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}/acknowledge-warnings`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots/{source_snapshot_id}/derive-submission-artifact-policy`
- `PATCH /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}/approve`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/activate`
- `GET /api/v1/projects/{project_id}/active-guide`

These routes require an actor role allowed to manage project setup.

`run-sufficiency-agent` returns `201` when it creates a new report and `200`
when it reuses the existing sufficiency row for the same source snapshot.
`derive-submission-artifact-policy` returns `201` when it creates a new policy
and `200` only when it reuses an existing agent-derived policy for the same
source snapshot.
Manual policy creation does not accept derivation provenance fields. Manual
policies persist `manual_admin_derivation`; agent-created policies persist
`agent_derivation` and use a server-owned `agent-<snapshot-hash>` policy
version. Manual policy creation requires sufficiency clearance first. Agent
policy derivation requires a Workstream-agent sufficiency report for the same
snapshot, and persisted agent identity is server-owned rather than copied from
provider output. A source snapshot has one sufficiency report. If a manual
report exists for that snapshot, `run-sufficiency-agent` reuses that row, while
`derive-submission-artifact-policy` rejects it; operators continue through
manual policy creation after clearance or create a fresh guide-source snapshot
before running the agent path.

`POST /submission-artifact-policies/{policy_id}/approve` returns the merged
`EffectiveProjectSubmissionArtifactPolicy`. The approval path also creates the
project-scoped `PreSubmitCheckerPolicy` contract with lifecycle status
`compiled`. The compiled bundle and compiled bundle hash are written during the
same approval path. Guide activation fails unless the compiled project
pre-submit checker policy exists.

`POST /activate` and `GET /active-guide` return the active guide with the full
setup bundle:

- `guide_source_snapshot`
- `guide_sufficiency_report`
- `submission_artifact_policy`
- `effective_submission_artifact_policy`
- `pre_submit_checker_policy`
- `post_submit_checker_policy`
- `review_policy`
- `revision_policy`
- `payment_policy`

## Lifecycle Impact

No task lifecycle transitions are implemented.

The active guide response becomes the future source for task-owned locked guide and policy context.

## Security/Auth Impact

- Routes require bearer auth.
- Missing/invalid token is rejected by the existing auth dependency.
- Project setup actions require admin or project manager role.
- Workers cannot create or activate guides.

## Tests Required

- migration upgrade/downgrade works
- project can be created
- draft guide can be created
- guide activation is blocked when submission artifact policy is missing
- guide activation is blocked when checker/review/revision/payment policies are missing
- guide activation is blocked when revision policy is missing
- guide activation is blocked when revision policy is incomplete
- guide activation is blocked when payment policy is incomplete
- guide activation or policy approval is blocked when project submission artifact policy removes Workstream hash requirements
- guide activation or policy approval is blocked when project submission artifact policy permits unsafe storage references
- guide activation or policy approval is blocked when project submission artifact policy requires default-forbidden artifacts
- guide activation or policy approval is blocked when project submission artifact policy downgrades Workstream blocking defaults
- generated effective project submission artifact policy always contains Workstream defaults
- guide activation succeeds with complete guide and policies
- active guide can be retrieved for task creation
- editing a draft guide works
- editing an active guide is blocked
- activating a new guide supersedes the prior active guide without mutating prior content
- worker role cannot create project setup records
- API validation errors are structured

## Conditions Of Satisfaction

- project can be created
- guide version can be created as draft
- guide version can be activated only when required policy fields exist
- active guide can be retrieved for task creation
- editing a draft guide does not mutate historical task context
- migrations pass upgrade/downgrade tests
- model/service/API tests pass
- stale wording scan passes
- Markdown link check passes
- required engineering-loop reviewer tracks pass according to the active chunk contract

## Reviewer Agents Required

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture/docs/reuse/test-delta/CI reviewers when the chunk touches those surfaces
