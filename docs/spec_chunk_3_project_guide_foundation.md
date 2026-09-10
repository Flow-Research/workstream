# Chunk 3 Project And Guide Foundation Spec

This retains the original foundation implementation and legacy response/migration
shapes; it is not the current remaining-work plan. For the replacement unified
path, use the [current dependency contract](../.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md#current-dependency-contract),
[checker architecture](architecture_checker_framework.md) and
[contribution specification](spec_contribution_compensation.md).
In particular, historical PaymentPolicy and separate-inference requirements
do not govern the new activation command. Historical migration names below
must not be allocated again against the current baseline.

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

Current v0.1 implementation note: project guide rows store human-facing guide
content only. Submission artifact requirements live in `SubmissionArtifactPolicy`
and compile into the project `PreSubmitCheckerPolicy`.

Migration note: the migration history now creates the current guide and task
contract directly. Project payment terms belong to `PaymentPolicy`; task
artifact requirements come from the locked project policy and checker bundle.

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
- states that allow resubmission
- reviewer reassignment rule

Limit or deadline exhaustion blocks later preparation and submission. It never
creates a reject Review; the current active contract defines reason-bound
manager/Operator cancellation paths.

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

## API Impact

Adds protected v1 routes:

- `POST /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/guides`
- `PATCH /api/v1/projects/{project_id}/guides/{guide_id}`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}/acknowledge-warnings`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies`
- `PATCH /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}/approve`
- `GET /api/v1/projects/{project_id}/active-guide`

These routes require an actor role allowed to manage project setup.

Committed original-document readiness dispatches the sole unified project-guide compilation
through Celery. Source metadata without committed original uploads remains pending;
ART readiness resumes the same generation. Guide creation alone does not invoke
the provider. One authorized attempt proposes sufficiency findings and separate
pre-submission and post-submission checker policies. A blocked guide records
findings without a policy projection; a ready guide records draft proposals.

The old sufficiency-run route and three inference methods are removed. The fixed
`workstream.project.setup` service requests, executes, projects and finalizes the
same attempt under fresh authority at each boundary. Runtime configuration is
immutable attempt evidence. Recovery never repeats an uncertain provider call.
Manual reports remain human-authored diagnostics and cannot occupy the
compilation report slot. Each compilation report binds exact original-document
accesses from its fenced attempt.
New projected artifact policies use `unified_compilation` provenance.

The superseded post-submit setup read, approval and correction APIs are removed.
Current outcomes remain visible through the latest setup run.

Project Manager proposal reads, correction, fresh-generation reruns and approval
remain POL-05. Existing generic approval rejects unified compilation drafts before
writing effective policy or checker contracts. No correction or approval enqueues
another inference operation.

`POST /submission-artifact-policies/{policy_id}/approve` returns the merged
`EffectiveProjectSubmissionArtifactPolicy`. The approval path also creates the
project-scoped `PreSubmitCheckerPolicy` contract with lifecycle status
`compiled`. The compiled bundle and compiled bundle hash are written during the
same approval path. Guide activation fails unless the compiled project
pre-submit checker policy exists.

Guide activation is unavailable until AUTH-12H installs its prepared mutation
boundary. The following retained legacy response shape is not the replacement
activation contract. CP07 owns the complete hidden unified command/response,
including guide-bound ContributionPolicy and no required PaymentPolicy row;
AUTH-12H activates that command. The legacy shape contains:

- `guide_source_snapshot`
- `guide_sufficiency_report`
- `submission_artifact_policy`
- `effective_submission_artifact_policy`
- `pre_submit_checker_policy`
- `post_submit_checker_policy`
- `review_policy`
- `revision_policy`
- `payment_policy`

The AUTH-11C2 administrative `GET /active-guide` projection returns the same
current guide context except `payment_policy`. Compensation configuration is
not part of this read authority. The GET is available only to a covered Project
Manager or Audit Authority grant, or a system-scoped Operator grant; other
principals receive concealed denial.

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


Unified setup records expose current sufficiency and submission-policy draft
outputs. The retired post-submit setup-step response fields and dormant activation
command are removed. Pre-submit capability references do not duplicate intake
settings: `submission_artifact_policy` is the sole configuration proposal.
Post-submit capability references retain their evaluator-owned configuration.
POL-05/POL-06 and AUTH-12H own the remaining approval, projection and activation
boundaries; current active-guide reads continue validating locked policy lineage.
