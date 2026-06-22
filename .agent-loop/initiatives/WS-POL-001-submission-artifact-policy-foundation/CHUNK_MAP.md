# Chunk Map: WS-POL-001 - Submission Artifact Policy Foundation

## Rules

- One chunk fits in one reviewable PR.
- No chunk mixes policy modeling, pre-submit runtime rewiring, and post-submit
  checker splitting unless explicitly approved.
- Every implementation chunk must use Postgres-backed tests.
- Worker-facing outcomes remain simple; internal route names stay internal.
- Project owners provide setup material in plain language; Workstream derives
  machine-readable submission artifact policy and actors with the `admin` or
  `project_manager` role approve it.

## Chunks

### WS-POL-001-01: Submission Artifact Policy Foundation

Goal:

Add first-class `SubmissionArtifactPolicy` backend records and schemas, define
Workstream default submission artifact rules in code, and validate that project
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
```

Acceptance criteria:

- Dedicated submission artifact policy model/table exists.
- Project policy is scoped to project id + guide version.
- Project policy records are Workstream-derived and approved by `admin` or
  `project_manager`, not direct project owner-authored schema.
- Workstream default policy is represented in code.
- Effective policy merge rejects attempts to weaken defaults.
- Guide activation requires valid submission artifact policy.
- Existing `evidence_policy` transitional behavior is not silently broken.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Policy ownership, project-owner intake checklist, policy field names, default
rule set, migration strategy, and whether `evidence_policy` remains a temporary
compatibility alias.

### WS-POL-001-02: Generated PreSubmitCheckerPolicy

Goal:

Generate pre-submit checker policy from effective submission artifact policy and
expose it only as server-owned policy context.

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

- Pre-submit checker policy is generated, not client-supplied.
- Generated policy contains Workstream defaults plus project additions.
- Generated policy names match registered pre-submit checker behavior.
- Workers cannot provide checker names, severities, versions, or outcomes.

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Generated policy persistence/derivation choice and exact naming.

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

Required reviewers:

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

Human review focus:

Fair worker experience during revision and audit clarity.
