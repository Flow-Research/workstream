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

GuideSufficiencyReport
  Workstream-owned assessment of whether the guide is sufficient

WorkstreamDefaultSubmissionArtifactPolicy
  platform-owned, non-bypassable safety rules

ProjectSubmissionArtifactPolicy
  Workstream-derived, admin-or-project-manager-approved machine-readable intake rules

EffectiveSubmissionArtifactPolicy
  deterministic merge of default + project policy

PreSubmitCheckerPolicy
  persisted and locked checker rules for draft packet intake

PostSubmitCheckerPolicy
  durable checker rules for locked submission review readiness
```

Project owners provide open-ended project material. Workstream does not enforce
a universal checklist. `ProjectGuideSufficiencyAgent` reviews the guide and task
shape asynchronously. Blocking gaps stop activation and create clarification
requests for the project owner. Warnings can be accepted only by a Workstream
actor with the `admin` or `project_manager` role.

Project owner material is always treated as untrusted data. Internal agents must
not execute embedded instructions from guide text, URLs, repository docs, or
examples. Fetching source material must use approved adapters or allowlisted
retrieval paths, reject signed URLs, query-bearing refs, credential-bearing refs,
and local filesystem paths, and persist only sanitized source refs.

`SubmissionArtifactPolicyDerivationAgent` derives machine-readable
`ProjectSubmissionArtifactPolicy` after guide sufficiency passes. A Workstream
actor with the `admin` or `project_manager` role approves the derived policy.
Workstream then computes the effective policy and persists the generated
`PreSubmitCheckerPolicy` snapshot/hash locked to the guide version. Pre-submit
checks run before submission creation and do not create durable checker records.
Post-submit/internal checks run after submission lock and do create durable
checker records.

The derivation agent does not generate unrestricted executable checker code.
It produces a constrained checker specification using Workstream-approved
primitives. Workstream's trusted checker compiler turns that specification into
the deterministic `PreSubmitCheckerPolicy` bundle. Runtime checks execute the
locked compiled bundle against staged artifact hashes or future content
identifiers.

If no passing or acknowledged guide sufficiency report, approved project
submission artifact policy, effective policy hash, and persisted generated
pre-submit checker policy exist for the guide version, guide activation fails
and tasks using that guide cannot enter the ready worker pipeline. The system
must surface setup failure internally as task/project setup incomplete rather
than letting workers discover missing intake rules at submit time.

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

### Force every project owner through a fixed intake checklist

Rejected because Workstream must support different project types. A guide may be
markdown, URL-backed docs, repository docs, rubric material, examples, or any
project-specific source material. Guide sufficiency is evaluated by Workstream
agents against the project and task shape instead of by forcing one universal
checklist.

### Combine pre-submit and post-submit checker policy

Rejected because pre-submit answers whether a packet can be submitted at all,
while post-submit answers whether a locked submission can move to human review.

## Boundaries Preserved

- Auth/session: still only verifies external Flow authentication tokens.
- Permission/policy: actors with the `admin` or `project_manager` role approve
  project policy setup; workers do not provide policy versions or checker names.
- Project-owner boundary: project owners provide open-ended guide material and
  business terms; Workstream evaluates sufficiency, derives policy, and owns
  internal controls.
- Checker-code boundary: agents derive constrained checker specifications;
  Workstream compiles deterministic checker bundles. Unrestricted generated
  checker code is not the default path.
- Source-material security: project-owner docs, URLs, examples, and repository
  docs are untrusted input; embedded tool instructions, prompt-injection text,
  credential-bearing refs, signed URLs, query-bearing refs, and local filesystem
  paths cannot become policy authority.
- Payment/execution: no payment or contribution records in this initiative.
- Persistence/data: schema changes land through Alembic and async SQLAlchemy.
- Presentation/API: backend-first; no frontend implementation.
- CI/deployment: no workflow weakening.

## Rollout/Migration Strategy

1. Add dedicated guide sufficiency, submission artifact policy, effective
   policy, and pre-submit policy records.
2. Replace transitional `evidence_policy`, `required_files`, and
   `required_evidence` usage; no v0.1 compatibility alias is required.
3. Add the Workstream-owned derivation/approval boundary for project policy.
4. Compute effective policy in service code and validate defaults cannot weaken.
5. Persist generated pre-submit checker policy snapshot/hash for the guide
   version.
6. Add async guide sufficiency and policy derivation execution.
7. Migrate submission creation to the locked generated pre-submit policy.
8. Split post-submit checker policy naming/provenance.

## Verification Strategy

- Unit-level policy merge tests for default + project policy.
- Postgres-backed API tests for guide sufficiency report, project policy
  creation, generated pre-submit policy persistence, and guide activation.
- Tests proving a guide cannot activate without passing or acknowledged guide
  sufficiency, approved project submission artifact policy, effective policy
  hash, and persisted generated pre-submit checker policy.
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

Start with guide/policy bundle foundation. Do not start submission runtime
rewiring until the guide sufficiency report, project policy object, defaults,
effective policy hash, persisted generated pre-submit checker policy, and
activation guards are accepted.
