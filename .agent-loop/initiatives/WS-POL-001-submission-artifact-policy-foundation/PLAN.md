# Plan: WS-POL-001 - Submission Artifact Policy Foundation

## Proposed Approach

Implement policy-driven submission intake in narrow slices.

First, add the guide-sufficiency and policy-bundle foundation without changing
the full submission runtime. Then add async guide analysis and derivation
execution. Then move submission creation to the locked pre-submit policy. Then
split post-submit checker policy naming and provenance. Finally, verify
revision resubmission and real API flows.

## Design Chosen

The product model is:

```text
ProjectGuide
  open-ended human-facing project material

GuideSourceSnapshot
  immutable bundle manifest for the exact guide/source material Workstream evaluated

GuideSufficiencyReport
  Workstream-owned assessment of whether the guide is sufficient

WorkstreamDefaultSubmissionArtifactPolicy
  platform-owned, non-bypassable safety rules

SubmissionArtifactPolicy
  Workstream-derived, admin-or-project-manager-approved machine-readable intake rules

EffectiveProjectSubmissionArtifactPolicy
  deterministic merge of default + project policy

PreSubmitCheckerPolicy
  persisted project checker rules for draft packet intake

PostSubmitCheckerPolicy
  durable checker rules for finalized submission review readiness
```

Project owners provide open-ended project material. Workstream does not enforce
a universal checklist. `ProjectGuideSufficiencyAgent` reviews the guide and task
shape asynchronously. Blocking gaps stop activation and create clarification
requests for the project owner. Warnings can be acknowledged only by a Workstream
actor with the `admin` or `project_manager` role.

Project owner material is always treated as untrusted data. Internal agents must
not execute embedded instructions from guide text, URLs, repository docs, or
examples. Fetching source material must use approved adapters or allowlisted
retrieval paths. Temporary fetch locators can include ordinary URL query
parameters when an approved adapter needs them, but signed URLs,
credential-bearing refs, token-bearing refs, and local filesystem paths are
rejected. Workstream persists only immutable `GuideSourceSnapshot` records with
canonical manifests, bundle hashes, opaque sanitized source refs, per-item
content hashes, optional future content ids, adapter names, and capture
timestamps. It never persists signed URLs, credentials, or token-bearing
locators as durable source identity.
The bundle hash is `sha256(canonical_json(manifest_json))` with deterministic
key ordering, source-item ordering, UTF-8 encoding, duplicate handling, and
volatile-field exclusions. Non-finite numbers such as `NaN` or `Infinity` are
rejected before hashing.

`SubmissionArtifactPolicyDerivationAgent` derives machine-readable
`SubmissionArtifactPolicy` after guide sufficiency passes or passes with
warnings. A Workstream actor with the `admin` or `project_manager` role
approves the derived policy after any sufficiency warnings are acknowledged.
Workstream then computes the effective project submission artifact policy and compiles the project
`PreSubmitCheckerPolicy`. The generated project `PreSubmitCheckerPolicy`
compiled bundle hash is scoped to the effective project submission artifact
policy hash plus compiler version.
Tasks lock references to the exact guide snapshot, effective project submission
artifact policy hash, and pre-submit checker bundle hash during screening before
entering `READY`.
Pre-submit checks run before submission creation and do not create durable
checker records.
Post-submit/internal checks run after submission lock and do create durable
checker records.

The derivation agent does not generate unrestricted executable checker code.
It produces the machine-readable project submission artifact policy.
Workstream's trusted checker compiler builds and validates the constrained
checker specification using Workstream-approved primitives, then turns that
specification into a deterministic project `PreSubmitCheckerPolicy` bundle
during project setup.
Runtime checks execute the locked compiled bundle against staged artifact hashes
or future content identifiers plus the task's constrained parameters. Tasks do
not rerun the derivation agent or compile a new checker bundle for each task.
The compiler must reject any specification that does not cover every enforceable
effective project submission artifact policy rule. Task runtime parameters come only from trusted
task-contract fields and cannot override required checks, severity, allowed
storage, forbidden artifacts, hash algorithm, or platform defaults.

In the final architecture, guide activation fails unless the guide snapshot and
guide version have a passing or acknowledged guide sufficiency report, approved
project submission artifact policy, effective project submission artifact policy hash, and project
`PreSubmitCheckerPolicy` compiled bundle hash. Chunk 1 creates the records and
enforces the compiled-checker activation dependency; Chunk 2 adds compiler
execution that writes the compiled bundle fields; Chunk 3 makes tasks lock the compiled checker reference
before entering the worker pipeline. The system must surface setup failure
internally as task/project setup incomplete rather than letting workers discover
missing intake rules at submit time.

Reports, derived policies, acknowledgements, effective policies, and checker
bundles bind to the exact `GuideSourceSnapshot` id/hash, not only to
`guide_version`. Any guide or source-material change creates a new snapshot and
invalidates prior sufficiency reports, derived project policies, effective
policies, checker bundles, acknowledgements, and approvals for activation.
A new guide-source snapshot invalidates prior setup records for new activation
and unlocked tasks only. Tasks already locked to an earlier snapshot retain
that policy context unless an explicit audited rebase occurs.

## Alternatives Considered

### Keep using guide prose and task fields

Rejected because it leaves too much room for project drift and unfair worker
feedback.

### Keep artifact intake rules as guide fields

Rejected because the name is too narrow. The policy governs artifacts, hashes,
storage references, packaging, forbidden files, and attestation, not only
evidence.

### Let project admins write checker names manually for pre-submit

Rejected because pre-submit should be generated from the effective submission
artifact policy. Workers and project admins should not choose blocking checker
internals directly for intake.

### Make project owners author `SubmissionArtifactPolicy` directly

Rejected because project owners should provide domain material, not internal
Workstream schema. Workstream owns derivation of the machine-readable contract,
and actors with the `admin` or `project_manager` role approve it before the
project can accept ready tasks.

### Force every project owner through a fixed intake checklist

Rejected because Workstream must support different project types. A guide may be
markdown, URL-backed docs, repository docs, rubric material, examples, or any
project-specific source material. Guide sufficiency is evaluated by Workstream
agents against the project and task shape instead of by forcing one universal
checklist.

### Combine pre-submit and post-submit checker policy

Rejected because pre-submit answers whether a packet can be submitted at all,
while post-submit answers whether a finalized submission can move to human review.

## Boundaries Preserved

- Auth/session: still only verifies external Flow authentication tokens.
- Permission/policy: actors with the `admin` or `project_manager` role approve
  project policy setup; workers do not provide policy versions or checker names.
- Project-owner boundary: project owners provide open-ended guide material and
  business terms; Workstream evaluates sufficiency, derives policy, and owns
  internal controls.
- Checker-code boundary: agents derive constrained project policy; Workstream's
  trusted compiler builds and validates checker specifications, then compiles
  deterministic checker bundles. Unrestricted generated checker code is not the
  default path.
- Source-material security: project-owner docs, URLs, examples, and repository
  docs are untrusted input; embedded tool instructions, prompt-injection text,
  credential-bearing refs, signed URLs, token-bearing refs, and local filesystem
  paths cannot become policy authority. Ordinary URL query parameters are
  allowed only as temporary inputs to approved retrieval adapters and are not
  persisted as durable source identity.
- Payment/execution: no payment or contribution records in this initiative.
- Persistence/data: schema changes land through Alembic and async SQLAlchemy.
- Presentation/API: backend-first; no frontend implementation.
- CI/deployment: no workflow weakening.

## Rollout/Migration Strategy

1. Add dedicated guide source snapshot, guide sufficiency, submission artifact
   policy, and effective project submission artifact policy records.
2. Replace transitional guide-field artifact rules and task-level artifact/evidence
   shortcuts; no v0.1 compatibility alias is required.
3. Add the Workstream-owned derivation/approval boundary for project policy.
4. Compute effective project submission artifact policy in service code and validate defaults cannot weaken.
5. Add async guide sufficiency, policy derivation execution, and trusted checker
   compiler behavior.
6. Add task locked-context fields for guide snapshot, effective project submission artifact policy,
   and generated project pre-submit checker bundle.
7. Migrate submission creation from transitional task fields to the locked task
   context and generated project pre-submit checker bundle.
8. Split post-submit checker policy naming/provenance.

## Verification Strategy

- Unit-level policy merge tests for default + project policy.
- Postgres-backed API tests for guide sufficiency report, project policy
  creation, immutable source snapshots, effective project submission artifact policy persistence,
  and guide activation.
- Tests proving a guide cannot activate without passing or acknowledged guide
  sufficiency bound to the current source snapshot, approved project submission
  artifact policy, and effective project submission artifact policy hash.
- Tests proving a task cannot enter `READY` without locked guide snapshot,
  effective project submission artifact policy hash, and generated project pre-submit checker bundle.
- Tests proving malicious or credential-bearing source material cannot weaken
  Workstream defaults, grant tool authority, or persist unsafe source refs.
- Submission API tests proving blocking pre-submit failure creates no submission
  row, version, task transition, durable checker run, or submission-created audit.
- Real API drill proving clean pass and `needs_revision` resubmission.
- Stale wording and Markdown link scans.

## Review Strategy

Required reviewers:

- senior engineering: data model, lifecycle, service boundaries
- QA/test: Postgres-backed proof and regression coverage
- security/auth: storage refs, hash rules, unsafe path/URL rejection
- product/ops: worker/project-manager semantics and fairness
- architecture: policy/source-of-truth boundaries
- docs: naming and guide/policy wording
- reuse/dedup: avoid duplicate checker/policy logic
- test delta: ensure tests cover new behavior

CI integrity is required only for chunks that touch workflows or test tooling.

## Sequencing

Start with guide/source/policy bundle foundation. Do not start submission
runtime rewiring until immutable guide-source snapshots, guide sufficiency
reports, project policy objects, defaults, effective project submission artifact policy hash,
generated project pre-submit checker bundle, task locked-context fields, and
activation/ready guards are accepted.

## Visibility API Extension

The post-actor-registry Terminal Benchmark live API drill proved the lifecycle
but required direct database inspection to continue through project setup and
policy approval. The next implementation sequence closes that gap before the
drill is rerun. The work is split across narrow chunks because it crosses
project setup, task worker visibility, submission finalization, checker reads,
and audit proof.

The target API surface is:

| # | API | Status |
|---:|---|---|
| 1 | `GET /api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest` | New |
| 2 | `GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports` | New |
| 3 | `GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}` | New |
| 4 | `GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies` | New |
| 5 | `GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}` | New |
| 6 | `GET /api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy` | New |
| 7 | `GET /api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy` | New |
| 8 | `GET /api/v1/tasks/{task_id}/work-context` | New |
| 9 | `GET /api/v1/tasks/{task_id}/submission-requirements` | New |
| 10 | `GET /api/v1/tasks/{task_id}/locked-context` | New |
| 11 | `POST /api/v1/submissions/{submission_id}/finalize` | New public finalization handoff |
| 12 | `GET /api/v1/submissions/{submission_id}/checker-runs` | Existing; keep and cover |
| 13 | `GET /api/v1/checker-runs/{checker_run_id}` | Existing; keep and cover |
| 14 | `GET /api/v1/tasks/{task_id}/audit-events` | Existing; keep and cover |

Implementation sequence:

| Chunk | Scope | APIs |
|---|---|---|
| `WS-POL-001-12` | Project setup-run and project policy visibility | 1-7 |
| `WS-POL-001-13` | Task work context, submission requirements, and operator locked context | 8-10 |
| `WS-POL-001-14` | Submission finalize, system actor audit semantics, and no-DB drill coverage | 11-14 plus existing pre-submit preflight |

`ProjectSetupRun` is a non-authoritative orchestration ledger. It records that
automatic setup was queued and how far the Celery job progressed, but policy
truth remains in `GuideSufficiencyReport`, `SubmissionArtifactPolicy`,
`EffectiveProjectSubmissionArtifactPolicy`, and `PreSubmitCheckerPolicy`.
The setup run records the Celery task id, lifecycle status, current step,
output report/policy ids, bounded errors, and timestamps. Enqueue writes
`queued`; enqueue failure writes `enqueue_failed`; the Celery worker updates
`running_sufficiency_agent`, `sufficiency_blocked`,
`running_policy_derivation_agent`, `policy_draft_ready`, `setup_blocked`, or
`failed`.

Project setup and policy APIs require project setup operator access. For v0.1,
that means a verified token with `admin` or `project_manager`.

Worker-facing visibility must be useful without leaking internal compiler
authority. Workers can see guide/work context and exact submission
requirements only for tasks they can work on. Operators can see full locked
provenance and compiled checker policy summaries.

Submission finalization should be the public handoff into the pre-review gate.
For v0.1, finalization is an `admin` or `project_manager` operation and is
idempotent for the latest submitted version. The external actor authorizes the
request and receives the API response, but pre-review checker execution is
audited as `workstream-system:pre-review-gate` with requester provenance in
the event payload. The system actor never authorizes HTTP requests.
