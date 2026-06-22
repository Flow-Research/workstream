# Plan: WS-POL-001 - Submission Artifact Policy Foundation

## Proposed Approach

Implement policy-driven submission intake in narrow slices.

First, add the policy foundation without changing the full submission runtime.
Then derive generated pre-submit policy. Then move submission creation to the
effective policy. Then split post-submit checker policy naming and provenance.
Finally, verify revision resubmission and real API flows.

## Design Chosen

The product model is:

```text
ProjectGuide
  human-facing instructions

ProjectSubmissionArtifactPolicy
  Workstream-derived, admin-or-project-manager-approved machine-readable intake rules

WorkstreamDefaultSubmissionArtifactPolicy
  platform-owned, non-bypassable safety rules

EffectiveSubmissionArtifactPolicy
  deterministic merge of default + project policy

PreSubmitCheckerPolicy
  generated checker rules for draft packet intake

PostSubmitCheckerPolicy
  durable checker rules for locked submission review readiness
```

Project owners provide human-facing setup material. Workstream derives the
machine-readable project submission artifact policy from that material, then a
Workstream actor with the `admin` or `project_manager` role approves it.
Pre-submit checks run before submission
creation and do not create durable checker records. Post-submit/internal checks
run after submission lock and do create durable checker records.

If no approved project submission artifact policy exists for the active guide,
guide activation fails and tasks using that guide cannot enter the ready worker
pipeline. The system must surface setup failure internally as task/project setup
incomplete rather than letting workers discover missing intake rules at submit
time.

## Alternatives Considered

### Keep using guide prose and task fields

Rejected because it leaves too much room for project drift and unfair worker
feedback.

### Use project guide `evidence_policy` as the long-term object

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

### Combine pre-submit and post-submit checker policy

Rejected because pre-submit answers whether a packet can be submitted at all,
while post-submit answers whether a locked submission can move to human review.

## Boundaries Preserved

- Auth/session: still only verifies external Flow authentication tokens.
- Permission/policy: actors with the `admin` or `project_manager` role approve
  project policy setup; workers do not provide policy versions or checker names.
- Project-owner boundary: project owners provide guide material,
  examples, rubrics, payment inputs, and artifact expectations in plain
  language; Workstream turns that material into approved policy.
- Payment/execution: no payment or contribution records in this initiative.
- Persistence/data: schema changes land through Alembic and async SQLAlchemy.
- Presentation/API: backend-first; no frontend implementation.
- CI/deployment: no workflow weakening.

## Rollout/Migration Strategy

1. Add dedicated policy model/API while keeping transitional fields readable.
2. Add the Workstream-owned derivation/approval boundary for project policy.
3. Compute effective policy in service code and validate defaults cannot weaken.
4. Generate pre-submit checker policy from effective policy.
5. Migrate submission creation to effective policy.
6. Split post-submit checker policy naming/provenance.
7. Retire or alias transitional `evidence_policy`, `required_files`, and
   `required_evidence` usage after tests prove the new path.

## Verification Strategy

- Unit-level policy merge tests for default + project policy.
- Postgres-backed API tests for project policy creation and guide activation.
- Tests proving a guide cannot activate without an approved project submission
  artifact policy.
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

Start with policy foundation. Do not start submission runtime rewiring until the
policy object, defaults, and merge rules are accepted.
