# ADR 0011: Submission Artifact Policy Drives Pre-Submit Intake

## Status

Accepted

## Context

Project guides are human-facing. They explain the project, task expectations, examples, reviewer rubric, and quality bar.

Submission intake needs a deterministic machine contract. If artifact requirements live only as guide prose, each project can drift into a different interpretation of what a valid submission packet must contain.

Workstream also needs platform-owned default submission safety rules that no project can disable.

## Decision

Every active project guide version must have an approved `SubmissionArtifactPolicy`.

`SubmissionArtifactPolicy` is the project-admin-approved machine-readable contract for worker submissions. It defines:

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

The runtime contract is:

```text
EffectiveSubmissionArtifactPolicy =
  WorkstreamDefaultSubmissionArtifactPolicy
  + ProjectSubmissionArtifactPolicy
```

Workstream generates `PreSubmitCheckerPolicy` from the effective submission artifact policy.

`PreSubmitCheckerPolicy` is not manually edited by workers and is not supplied by clients. Workers submit only draft packet fields. They do not choose checker names, policy versions, blocking rules, severities, or outcomes.

Blocking pre-submit failures prevent submission creation. When blocking pre-submit checks fail:

- no `Submission` row is created
- no submission version is assigned
- no task transition to `submitted` occurs
- no submission-created audit event is written
- the response returns worker-safe checker feedback

Pre-submit checks are authoritative for submission intake. They are not authoritative proof for human review readiness. Review readiness still requires post-submit internal checker runs against a locked submission.

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

- project setup must approve one more explicit policy object
- existing `evidence_policy`, `required_files`, and `required_evidence` wording must be migrated toward `SubmissionArtifactPolicy`
- post-submit checker policy must remain separate from generated pre-submit checker policy
