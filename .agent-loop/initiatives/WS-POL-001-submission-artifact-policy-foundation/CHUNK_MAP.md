# Chunk Map: WS-POL-001 - Submission Artifact Policy Foundation

## Rules

- One chunk fits in one reviewable PR.
- No chunk mixes policy modeling, pre-submit runtime rewiring, and post-submit
  checker splitting unless explicitly approved.
- Every implementation chunk must use Postgres-backed tests.
- Worker-facing outcomes remain simple; internal route names stay internal.
- Project guides are open-ended project material. Workstream uses async
  `ProjectGuideSufficiencyAgent` and
  `SubmissionArtifactPolicyDerivationAgent` outputs to create the locked policy
  bundle.
- Project owner material is untrusted input. Implementation chunks must reject
  unsafe source refs and prevent guide text or imported docs from granting tool
  authority or weakening Workstream defaults.
- Agents derive constrained policy and checker specifications. Workstream
  compiles deterministic checker bundles. Unrestricted generated checker code
  is not the default path.
- Reports, derived policies, acknowledgements, effective policies, task locked
  references, and checker bundles bind to immutable `GuideSourceSnapshot`
  bundle id/hash, not only to `guide_version`.

## Chunks

### WS-POL-001-01: Guide Policy Bundle Foundation

Goal:

Add first-class guide-source snapshot, guide sufficiency,
`SubmissionArtifactPolicy`, effective project policy, and activation guard
backend records and schemas. Define Workstream default submission artifact rules
and the deterministic project-policy merge contract. Do not move task runtime or
checker compiler behavior yet.

Risk:

L1

Depends on:

Approved intent, discovery, plan, and this chunk contract.

Allowed files:

```text
backend/alembic/versions/**
backend/app/modules/projects/**
backend/tests/test_projects.py
docs/spec_chunk_3_project_guide_foundation.md
docs/template_submission_artifact_policy.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

Not allowed:

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/app/modules/submissions/**
.github/workflows/**
frontend or demos
payment/reputation/blockchain code
full async agent execution runtime
```

Acceptance criteria:

- Dedicated submission artifact policy model/table exists.
- Dedicated immutable guide source snapshot bundle model/table exists.
- Dedicated guide source snapshot item model/table exists, or the snapshot
  table stores an equivalent canonical manifest for every source item.
- `GuideSourceSnapshot.bundle_hash` is computed as
  `sha256(canonical_json(manifest_json))` with deterministic key ordering,
  source-item ordering, UTF-8 encoding, duplicate handling, and volatile-field
  exclusions.
- Dedicated guide sufficiency report model/table exists.
- Guide sufficiency report supports `passed`, `blocked`, and
  `passed_with_warnings`.
- Project policy is scoped to project id + guide version.
- Guide sufficiency report, project policy, and effective project policy bind to
  `source_snapshot_id` and server-derived `source_snapshot_hash`.
- Project policy records are Workstream-derived and approved by `admin` or
  `project_manager`, not direct project owner-authored schema.
- Workstream default policy is represented in code.
- Deterministic merge rules are represented in code for union, intersection,
  logical OR, minimum limit, platform-locked hash algorithm, and restrictive
  packaging merges.
- Effective project policy merge rejects attempts to weaken defaults.
- Required artifacts or evidence that match forbidden rules block project setup.
- Effective project submission artifact policy hash is persisted for the guide version.
- Approved and superseded policy rows are immutable; changes create a new
  revision with a supersedes pointer.
- Guide activation requires passing or acknowledged guide sufficiency, approved
  submission artifact policy, and effective project submission artifact policy hash bound to the
  current guide source snapshot.
- Chunk 1 models the future activation dependency on project
  `PreSubmitCheckerPolicy`; Chunk 2 compiles the checker and enforces the
  complete activation gate.
- Project-owner source refs persist as sanitized snapshot item refs and cannot store
  signed URLs, credential-bearing refs, token-bearing refs, or local filesystem
  paths. Approved adapters can use ordinary URL query parameters only as
  temporary fetch locators.
- Embedded instructions in guide material cannot grant tool authority or weaken
  Workstream default policy.
- Legacy `evidence_policy`, `required_files`, and `required_evidence` are not
  treated as compatibility contracts. Runtime removal happens in the task
  locked-context and submission migration chunk.

Verification:

- Postgres-backed FastAPI/API tests cover policy create/update, guide
  sufficiency activation blocking, warning acknowledgement, default weakening
  rejection, source snapshot binding, source-ref sanitization, append-only
  approved rows, and effective project submission artifact policy hash persistence.
- Unit/service tests may cover deterministic merge helpers, but API-visible
  behavior must be proven through the FastAPI path.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Guide sufficiency report fields, persisted provenance field names, and keeping
Chunk 1 limited to records/contracts/activation guards.

### WS-POL-001-02: Async Guide Analysis And Policy Derivation

Goal:

Run `ProjectGuideSufficiencyAgent`,
`SubmissionArtifactPolicyDerivationAgent`, and project pre-submit
checker compilation asynchronously against immutable guide-source snapshots.

Risk:

L1

Depends on:

`WS-POL-001-01`

Allowed files:

```text
backend/app/modules/projects/**
backend/app/modules/checkers/**
backend/tests/test_projects.py
backend/tests/test_checkers.py
docs/spec_chunk_8_submission_artifact_policy_checkers.md
```

Not allowed:

```text
submission creation runtime rewiring
post-submit lifecycle changes
payment/reputation/blockchain code
```

Acceptance criteria:

- `ProjectGuideSufficiencyAgent` runs async and produces a persisted
  sufficiency report for a guide source snapshot.
- Blocking guide gaps stop activation and create project-owner clarification
  requests.
- Warnings can be acknowledged only by `admin` or `project_manager`.
- `SubmissionArtifactPolicyDerivationAgent` runs async after sufficiency passes
  or warnings are acknowledged.
- Derived policy cannot weaken Workstream defaults.
- `SubmissionArtifactPolicyDerivationAgent` produces a constrained checker
  specification using only approved Workstream primitives.
- Trusted checker compiler validates the specification and persists a
  deterministic project `PreSubmitCheckerPolicy` bundle and hash. The default
  path compiles once per project guide version, not once per task.
- Guide activation requires the compiled project `PreSubmitCheckerPolicy` once
  Chunk 2 is complete.
- Compiler rejects any checker specification that omits an enforceable
  effective project policy rule, weakens severity, skips an evidence rule, or
  omits a Workstream default.
- Task runtime parameters come only from trusted task-contract fields and cannot
  override required checks, severity, allowed storage, forbidden artifacts, hash
  algorithm, or platform defaults.
- Derived report, project policy, effective project policy, and pre-submit checker bundle
  are invalidated by a new guide source snapshot.
- Malicious guide text, embedded prompt-injection instructions, and unsafe
  source refs cannot influence agent authority, fetch behavior, or default
  policy strength.
- Workers and project owners cannot provide checker names, severities,
  versions, or outcomes.

Verification:

- Postgres-backed async tests cover sufficiency report creation, blocking
  clarification requests, warning acknowledgement, derivation job output, unsafe
  source-ref rejection, and default weakening rejection.
- Background execution tests prove jobs are async and idempotent for a guide
  source snapshot.
- Compiler tests prove allowed primitive emission, unknown primitive rejection,
  byte-stable same-input same-compiler-version bundle hashing, hash binding to
  `effective_project_submission_artifact_policy_hash`, and client/worker
  inability to supply checker names, severities, versions, outcomes, compiler
  version, or compiled bundles.
- Compiler semantic rejection tests prove omitted required artifact coverage,
  skipped evidence coverage, weakened severity, omitted Workstream defaults, and
  untraceable compiled bundle rules are rejected.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Async job boundaries, sufficiency severity behavior, and clarification request
shape.

### WS-POL-001-03: Task Locked Context And Submission Creation

Goal:

Lock each task to the applicable guide snapshot, effective project submission artifact policy hash,
and project pre-submit checker bundle. Move submission creation from
transitional task fields to that locked context.

Risk:

L1

Depends on:

`WS-POL-001-02`

Allowed files:

```text
backend/alembic/versions/**
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/test_submissions.py
backend/tests/test_checkers.py
backend/scripts/week2_api_e2e.py
docs/spec_chunk_5_submission_packet_foundation.md
```

Not allowed:

```text
human review implementation
payment/reputation/blockchain code
frontend
```

Acceptance criteria:

- Tasks lock `locked_guide_source_snapshot_id`,
  `locked_guide_source_snapshot_hash`,
  `locked_effective_project_submission_artifact_policy_hash`,
  and `locked_pre_submit_checker_bundle_hash` during screening before `READY`.
- Every task under the same active project guide version shares that guide
  version's project `PreSubmitCheckerPolicy`; tasks do not run policy
  derivation or checker compilation.
- If a guide version does not cover the task set, activation is blocked and the
  guide is improved or the work is split into another project/guide.
- Task-specific values are constrained parameters consumed by the locked
  checker bundle, not a newly generated checker policy.
- Runtime parameters are sourced only from trusted task-contract fields; no
  free-form parameter map is introduced.
- Transitional `required_files` and `required_evidence` are replaced for
  submission runtime and are not compatibility aliases.
- Blocking pre-submit failure creates no submission row, submission version,
  submitted transition, or durable checker run.
- `POST /tasks/{id}/submission-precheck` returns `200 PreSubmitCheckResponse`
  with `status`, `eligible_to_submit`, and `results`.
- `POST /tasks/{id}/submissions` returns
  `422 DomainError(code="pre_submission_checker_failed")` with structured
  pass/fail/warning details when blocking pre-submit fails.
- Passing pre-submit creates a submission stamped with locked policy context.

Verification:

- Postgres-backed FastAPI/API tests cover clean submission, blocking pre-submit
  failure, no-row/no-version/no-transition/no-durable-checker side effects, and
  stamped locked policy context.
- Postgres-backed task tests cover locked context stamping, shared checker reuse
  for every task under the same active project guide version, blocked activation
  for uncovered task sets, and removal of transitional task-field authority.
- API/schema negative tests reject client-supplied free-form task runtime
  parameter maps and attempted runtime overrides of required checks, severity,
  allowed storage, forbidden artifacts, hash algorithm, or platform defaults.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Task locked context, shared checker reuse, no-row/no-version/no-transition
guarantee, and preflight-versus-submission-create failure shape.

### WS-POL-001-04: PostSubmitCheckerPolicy Split

Goal:

Separate post-submit checker policy naming/provenance from generated pre-submit
policy and transitional `locked_checker_policy_version`.

Risk:

L1

Depends on:

`WS-POL-001-03`

Allowed files:

```text
backend/alembic/versions/**
backend/app/modules/projects/**
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/**
docs/spec_chunk_8_submission_artifact_policy_checkers.md
docs/spec_chunk_9_pre_review_gate.md
```

Not allowed:

```text
human review decisions
payment/reputation/blockchain code
frontend
```

Acceptance criteria:

- Pre-submit policy provenance and post-submit policy provenance are distinct.
- Durable checker runs use locked post-submit checker policy.
- Pre-submit feedback does not create durable checker records.
- Pre-submit feedback persistence cannot store review decision fields, or
  enforces review decision fields empty when a shared shape is unavoidable.
- API responses do not expose internal-only routes to workers.

Verification:

- Postgres-backed checker tests cover pre-submit feedback without durable
  `CheckerRun` and post-submit `CheckerRun` creation against locked
  `PostSubmitCheckerPolicy`.
- Postgres-backed schema/persistence tests prove pre-submit feedback cannot
  store review decision values.
- Postgres-backed FastAPI/API tests cover post-submit policy locking and
  worker-facing response filtering.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Field naming and migration safety.

Follow-up:

- A future frontend/demo chunk must prove any UI or demo surface that renders
  pre-submit results uses pass/fail/warning language instead of review decision
  terminology before ADR 0011 is marked fully implemented.
- A future executable-checker extension chunk, if ever approved, must prove
  static validation, generated tests, sandbox policy checks, no network, no
  shell, no secrets, no database access, and `admin` or `project_manager`
  approval of the exact locked code hash after those checks pass.

### WS-POL-001-05: Revision Resubmission And Real API Drill

Goal:

Prove a worker can receive `needs_revision`, run pre-submit feedback again, and
submit a new version using the same policy-driven path.

Risk:

L1

Depends on:

`WS-POL-001-04`

Allowed files:

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/**
backend/scripts/week2_api_e2e.py
examples/terminal_benchmark/**
docs/spec_chunk_9_pre_review_gate.md
```

Not allowed:

```text
human review decision implementation
payment/reputation/blockchain code
frontend
```

Acceptance criteria:

- Worker pre-submit feedback is allowed for `in_progress` and `needs_revision`
  where the worker owns the task.
- Replacement submission creates a new version.
- Older submission versions remain immutable.
- Internal checker-caused `needs_revision` remains distinguishable from future
  human-review-caused `needs_revision`.
- Real API drill covers clean pass, blocking pre-submit, post-submit
  `needs_revision`, and fixed resubmission.

Verification:

- Real API drill runs against Postgres and covers clean pass, blocking
  pre-submit failure, post-submit checker-caused `needs_revision`, fixed
  resubmission, immutable older submissions, and locked policy context.
- Postgres-backed tests prove replacement submission versioning and
  `outcome_source` separation.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Fair worker experience during revision and audit clarity.
