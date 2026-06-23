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

## Chunks

### WS-POL-001-01: Guide Policy Bundle Foundation

Goal:

Add first-class guide sufficiency, `SubmissionArtifactPolicy`, effective policy,
and persisted `PreSubmitCheckerPolicy` backend records and schemas. Define
Workstream default submission artifact rules in code and validate that project
policy cannot weaken defaults.

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
- Dedicated guide sufficiency report model/table exists.
- Guide sufficiency report supports `passed`, `blocked`, and
  `passed_with_warnings`.
- Project policy is scoped to project id + guide version.
- Project policy records are Workstream-derived and approved by `admin` or
  `project_manager`, not direct project owner-authored schema.
- Workstream default policy is represented in code.
- Effective policy merge rejects attempts to weaken defaults.
- Effective submission artifact policy hash is persisted for the guide version.
- Generated `PreSubmitCheckerPolicy` snapshot/hash is persisted and locked to
  the guide version.
- Guide activation requires passing or acknowledged guide sufficiency, approved
  submission artifact policy, effective policy hash, and persisted generated
  pre-submit checker policy.
- Project-owner source refs are sanitized and cannot contain signed URLs,
  query-bearing refs, credential-bearing refs, or local filesystem paths.
- Embedded instructions in guide material cannot grant tool authority or weaken
  Workstream default policy.
- Transitional `evidence_policy`, `required_files`, and `required_evidence` are
  replaced, not preserved as compatibility aliases.

Verification:

- Postgres-backed FastAPI/API tests cover policy create/update, guide
  sufficiency activation blocking, warning acknowledgement, default weakening
  rejection, source-ref sanitization, and pre-submit policy locking.
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

Run `ProjectGuideSufficiencyAgent` and
`SubmissionArtifactPolicyDerivationAgent` asynchronously against open-ended
project guide material.

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
  sufficiency report for a guide version.
- Blocking guide gaps stop activation and create project-owner clarification
  requests.
- Warnings can be acknowledged only by `admin` or `project_manager`.
- `SubmissionArtifactPolicyDerivationAgent` runs async after sufficiency passes
  or warnings are acknowledged.
- Derived policy cannot weaken Workstream defaults.
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
  version.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Async job boundaries, sufficiency severity behavior, and clarification request
shape.

### WS-POL-001-03: Submission Creation Uses Effective Policy

Goal:

Move submission creation pre-submit gate from transitional task fields to the
effective submission artifact policy and generated pre-submit checker policy.

Risk:

L1

Depends on:

`WS-POL-001-02`

Allowed files:

```text
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

- Blocking pre-submit failure creates no submission row, submission version,
  submitted transition, or durable checker run.
- Blocking pre-submit failure returns `pre_submission_checker_failed` with
  structured pass/fail/warning details, not review decision values.
- Passing pre-submit creates a submission stamped with locked policy context.

Verification:

- Postgres-backed FastAPI/API tests cover clean submission, blocking pre-submit
  failure, no-row/no-version/no-transition/no-durable-checker side effects, and
  stamped locked policy context.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

No-row/no-version/no-transition guarantee and `pre_submission_checker_failed`
feedback shape.

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
- API responses do not expose internal-only routes to workers.

Verification:

- Postgres-backed checker tests cover pre-submit feedback without durable
  `CheckerRun`, post-submit `CheckerRun` creation against locked
  `PostSubmitCheckerPolicy`, and worker-facing response filtering.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Field naming and migration safety.

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
