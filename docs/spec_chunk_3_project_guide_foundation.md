# Chunk 3 Project And Guide Foundation Spec

This retains the original foundation implementation and legacy response/migration
shapes; it is not the current remaining-work plan. For the replacement unified
path, use the [current dependency contract](../.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md#current-dependency-contract),
[checker architecture](architecture_checker_framework.md) and
[contribution specification](spec_contribution_compensation.md).
In particular, historical separate-inference requirements
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

Current v0.1 implementation note: project guide rows store human-facing guide
content only. Submission artifact requirements live in `SubmissionArtifactPolicy`
and compile into the project `PreSubmitCheckerPolicy`.

Migration note: the migration history now creates the current guide and task
contract directly. Guide activation binds an explicit published ContributionPolicyVersion;
task artifact requirements come from the locked project policy and checker bundle.

The guide version is the join key for the guide-specific policies.

The canonical CP07 guide activation operation, exposed by AUTH-18, requires:

- a draft guide in a draft or active Project, with an exact mutation generation
- an intact source manifest and finalized current unified compilation
- sufficient guide findings with required warning acknowledgements
- the exact pre-submit approval and compiled effective intake plan
- a separate exact post-submit policy approval and supported catalogue selections
- selected complete review/revision policy generations and hashes
- a complete supported ReviewPolicy; `human_review_required=false` additionally
  requires the approved requirement inventory to contain no `human_review`
  disposition
- an explicitly selected current published ContributionPolicyVersion validated
  by CON, including its complete rules and binding eligibility
- the exact expected prior active guide and generation, if replacing one
- a nominal prepared activation authority participant and immutable audit receipt

No Task, Submission, provider invocation or completed checker
run is required. Default composition denies activation; AUTH-12H supplies the
live manager authority for this same operation.

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

Activation requires a revision policy before the guide can become active. The active guide response returns revision policy beside submission artifact policy, checker policy, and review policy so future task records can lock the full policy context. The Non-Scope section keeps only revision workflow execution out of this chunk, not revision policy itself.

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
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/documents/{document_id}/content`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}/acknowledge-warnings`
- `POST /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies`
- `PATCH /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}`
- `GET /api/v1/projects/{project_id}/active-guide`

These routes require an actor role allowed to manage project setup.

Guide creation requires at least one task example and a complete nonempty
`documents` list of labels and supported media types. Its response includes each
`document_id` and the initial `awaiting_documents` setup. Upload each original as
a raw binary body with the declared `Content-Type` and a UUID `Idempotency-Key`.
Workstream computes the digest and size, checks format and bounds, and stores
the bytes through ArtifactStore. The document-set identity and source consent
are internal custody; clients do not create or select a source snapshot.
Exact create/upload replay rechecks current authority and returns the original
result. A changed document set requires a new guide.

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

POL-05B exposes POL-05A complete-proposal review, pre-submission approval and
setup-wide correction using AUTH-12F4 exact-project human manager authorization.
The manual artifact-policy approval route and operation are removed. Proposal
services require explicit authority; no unconfigured construction path remains.
The existing setup diagnostic returns `finalized_compilation_id` only after
finalization; that pointer never substitutes for authorized complete proposal read.
For a correction successor, the same authorized read returns
`correction_operation_id` and `predecessor_compilation_id` from its immutable
correction record, before dispatch and after finalization. A replacement manager
can discover both and dispatch through the existing predecessor-scoped route
without the creator's receipt. Current dispatch authority is still required;
initial setups return null for both pointers.

The review package contains all findings, requirements, distinct pre/post
bindings, capability suggestions and notes, plus exact source, result, component,
catalogue and finalization identities. Evidence locations use document ordinals
and page/section labels; runtime document handles are not disclosed.

Approval requires the exact displayed target, acknowledged warning hashes
and the current approval identity when replacing a policy. The existing CHECKERS
compiler produces the effective artifact policy and compiled pre-submit bundle;
the canonical planner supplies its ordered execution plan. An immutable approval
operation and the existing mutation reservation bind those outputs atomically.
Approval neither invokes a model nor changes the finalized setup receipt.

Correction binds a manager's reason to one successor generation over the same
original documents and task examples. The successor starts at
`correction_requested`; initial-upload automatic recovery cannot dispatch it.
The existing authorized human request operation binds feedback into its canonical
input and reserves one attempt. POL-05B dispatch atomically stores the pending
queue claim with request custody, then publishes through the existing queue.
The worker selects the exact saved human request and uses the same execution,
projection and finalization owners. Public dispatch never reveals provider keys.
See the [public manager flow](operations_project_operating_manual.md#review-approve-or-correct-a-guide-proposal). Blocked results
may be corrected but cannot be approved, and uncertain provider attempts are
not correction targets. Guide activation still requires a complete compiled
pre-submission policy and the separately governed post-submission policy.

CP07 provides the complete-guide activation command and immutable receipt.
Its command selects both approval receipts, review/revision generations, exact
ContributionPolicy/version, guide mutation generation and expected predecessor.
The receipt preserves those inputs, CON validation facts and activation time.
One caller-owned transaction commits audit custody, guide binding, predecessor
supersession and draft-Project activation. Exact replay requires current authority
but does not reselect CON after retirement or guide supersession.

The AUTH-11C2 administrative `GET /active-guide` projection returns the current
guide and its compiled/approved policy context, including the guide's bound
ContributionPolicy/version and activation operation identifiers. It requires
immutable activation custody; retained unbound rows are unavailable. The GET is
available only to a covered Project Manager or Audit Authority grant, or a
system-scoped Operator grant. AUTH-12H supplies activation authority only for a live exact-project Project
Manager. AUTH-18 exposes the canonical POST on `/api/v1/projects/{project_id}/guides/{guide_id}/activate`.
The draft post-policy review package supplies complete activation selectors without
Finance policy bodies or draft selectors. Missing inputs are explicit, not defaults.
One UUID Idempotency-Key and the original body recover the receipt with fresh
authority; response serialization and validation precede commit.

## Exact selected POST revision inputs

A checker specification declares `kind: evaluation_context` with an exact sorted
`evaluation_context_roles` list drawn from `predecessor_findings` and
`predecessor_submission_archive`. Only that input kind carries the role field;
other inputs omit it. The matching dependency is
`evaluation_context/current_runner` with `material_unavailable`, and requires POST
background execution. Model evaluation and isolated trial checks may both use it.

The binding must select the same roles using
`workstream_evaluation_context_version: v1` and
`workstream_evaluation_context_roles`; its immutable registered configuration
schema must declare both keys. Proposal validation and approval-time resolution
check exact agreement, including absent declaration versus absent selection.
These declarations grant no access. Existing verified runtime custody supplies
only selected evidence, while broad `task_context` and `guide_context` remain
unavailable runtime gaps. Registry publication and a descriptive specification
alone do not approve or activate a policy.

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
- guide activation is blocked when checker/review/revision/contribution policies are missing
- guide activation is blocked when revision policy is missing
- guide activation is blocked when revision policy is incomplete
- guide activation is blocked when the selected ContributionPolicy is unavailable or incomplete
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
POL-06A implements hidden post-policy derivation from the saved unified result,
complete canonical draft reads, separate approval and setup-wide correction.
Projection requires the current approved artifact/effective/pre-submit chain.
Each immutable operation binds finalization, source, result, upstream approval,
catalogue and canonical policy hash. Correction reuses the unified successor;
no operation reopens finalization or calls an evaluator. Affected active-guide
reads require this operation custody instead of role-string approval fields.
AUTH-12G and POL-06B supply live post-policy authority and public exposure.
AUTH-12H supplies live exact-project manager authority for the existing internal
complete-guide activation operation; AUTH-18 exposes its exact-authorized HTTP endpoint.

The superseded guide-keyed PaymentPolicy table and mutable repository path are
removed. Migration refuses retained payment terms or obsolete immutable TASK
response keys; it never rewrites them into ContributionPolicy facts. Current
compensation remains owned by [ContributionPolicy](spec_contribution_compensation.md).
