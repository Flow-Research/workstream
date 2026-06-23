# ADR 0011: Submission Artifact Policy Drives Pre-Submit Intake

## Status

Accepted

## Context

Project guides are human-facing. They explain the project, task expectations,
examples, reviewer rubric, and quality bar. A guide can be markdown, imported
documentation, URL-backed docs, repository docs, examples, rubrics, task
instructions, or other project-specific source material.

Submission intake needs a deterministic machine contract. If artifact requirements live only as guide prose, each project can drift into a different interpretation of what a valid submission packet must contain.

Workstream also needs platform-owned default submission safety rules that no project can disable.

## Decision

Every active project guide version must have a complete guide-policy bundle:

- passing or acknowledged `GuideSufficiencyReport`
- approved `ProjectSubmissionArtifactPolicy`
- persisted `EffectiveSubmissionArtifactPolicy` hash
- persisted generated `PreSubmitCheckerPolicy` snapshot/hash

Project owners provide open-ended project material in plain language. Workstream
must not force every project owner through one universal intake checklist.

`ProjectGuideSufficiencyAgent` evaluates whether the guide is sufficient for
submitters, reviewers, and Workstream quality control. Blocking guide gaps stop
activation and create clarification requests back to the project owner. Warnings
remain visible to Workstream actors with the `admin` or `project_manager` role
and must be acknowledged before activation.

`SubmissionArtifactPolicyDerivationAgent` derives
`ProjectSubmissionArtifactPolicy` from the guide material after sufficiency
passes or warnings are acknowledged. The project owner does not approve this
internal policy. A Workstream actor with the `admin` or `project_manager` role
reviews and approves the derived policy before guide activation.

`SubmissionArtifactPolicy` is the Workstream-derived, admin-or-project-manager-approved machine-readable contract for worker submissions. It defines:

- required artifacts
- required evidence references
- artifact manifest rules
- artifact hash rules
- allowed storage reference forms
- forbidden artifacts
- worker attestation requirements
- project-specific packaging requirements

Workstream owns a default submission artifact policy. Every project inherits it.

Project policy can add stricter requirements, but it cannot remove, weaken, downgrade, or bypass Workstream defaults.

Approval provenance is part of the policy contract. A policy record must make
approval testable with source/provenance state such as derivation source,
approval status, approver actor, approval timestamp, and approved policy
version/hash.

The runtime contract is:

```text
EffectiveSubmissionArtifactPolicy =
  WorkstreamDefaultSubmissionArtifactPolicy
  + ProjectSubmissionArtifactPolicy
```

Workstream generates and persists `PreSubmitCheckerPolicy` from the effective
submission artifact policy.

`PreSubmitCheckerPolicy` is locked to the project guide version. It is not
derived on read, manually edited by workers, or supplied by clients. Workers
submit only draft packet fields. They do not choose checker names, policy
versions, blocking rules, severities, or outcomes.

Blocking pre-submit failures prevent submission creation. When blocking pre-submit checks fail:

- no `Submission` row is created
- no submission version is assigned
- no task transition to `submitted` occurs
- no submission-created audit event is written
- the response returns `pre_submission_checker_failed`
- the response includes structured pass/fail/warning details
- the response does not use review decision values: `accept`, `needs_revision`, or `reject`

Pre-submit checks are authoritative for submission intake. They are not authoritative proof for human review readiness. Review readiness still requires post-submit internal checker runs against a locked submission.

## Implementation Enforcement Contract

This ADR defines the required product contract. This planning PR does not claim
the backend implementation already enforces it.

The implementation chunks that close this ADR must prove these enforcement
points before they can be marked complete:

- API response schemas for `pre_submission_checker_failed` must exclude review
  decision fields and values such as `accept`, `needs_revision`, and `reject`.
- Worker-facing UI or demo surfaces that render pre-submit results must use
  pre-submit pass/fail/warning language, not human review decision terminology.
- Pre-submit intake feedback must not be persisted as human review decisions or
  durable post-submit checker results.
- Database schemas or persistence services for pre-submit feedback must not
  store review decision columns for pre-submit outcomes; if a shared shape is
  unavoidable, review-decision fields must be nullable and enforced empty for
  pre-submit records.
- Post-submit checker records and future human review records remain the only
  places that can route toward `needs_revision` as a task outcome.

Chunk `WS-POL-001-03` must prove the API response and no-row/no-version/no-task
transition behavior. Chunk `WS-POL-001-04` must prove post-submit checker
records remain separate from pre-submit feedback and that worker-facing
responses do not expose internal-only routes.

## Default Workstream Submission Artifact Rules

Every submission must include:

- summary
- package hash when a package reference is supplied
- artifact hash manifest
- worker attestation

Every artifact manifest entry must include:

- artifact name or relative path
- artifact hash

Every artifact path must be safe:

- relative path only
- no absolute paths
- no empty segments
- no `.` or `..` traversal segments

Uploaded artifacts and storage-backed evidence require `sha256:<64 lowercase hex>` hashes in production. Test fixtures may use deterministic placeholder hash tokens only in explicit local test paths.

Persisted storage references must be Workstream-issued opaque object references or validated object-storage adapter references. Raw signed URLs, credential-bearing URLs, query strings, local filesystem paths, bucket secrets, and token-bearing references are rejected before persistence. Normalization is allowed only for already-approved adapter references that contain no secrets, credentials, or query material.

Default forbidden artifacts remain blocked even if a project policy accidentally lists them as required. A required artifact that violates the default forbidden policy is a project setup defect.

## Consequences

Positive:

- workers get deterministic pre-submit feedback
- invalid packets are blocked before submission records are created
- project-specific artifact requirements are enforced without rereading guide prose at runtime
- Workstream security defaults cannot be weakened by project configuration
- implementation can test submission intake as a strict contract

Tradeoff:

- project setup must approve one more explicit Workstream-owned policy bundle
- existing `evidence_policy`, `required_files`, and `required_evidence` wording
  must be replaced by `SubmissionArtifactPolicy`; no v0.1 compatibility alias
  is required
- post-submit checker policy must remain separate from generated pre-submit checker policy
