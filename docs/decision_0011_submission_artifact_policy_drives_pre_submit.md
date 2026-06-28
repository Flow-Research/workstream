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

- immutable `GuideSourceSnapshot` bundle for the exact guide/source material evaluated
- passing or acknowledged `GuideSufficiencyReport`
- approved `ProjectSubmissionArtifactPolicy`
- persisted `EffectiveProjectSubmissionArtifactPolicy` hash
- persisted generated project `PreSubmitCheckerPolicy` compiled bundle hash
- `PostSubmitCheckerPolicy`
- `ReviewPolicy`
- `RevisionPolicy`
- `PaymentPolicy`

Project owners provide open-ended project material in plain language. Workstream
must not force every project owner through one universal intake checklist.

Workstream binds all downstream setup records to the exact guide source
snapshot, not only to `guide_version`. `GuideSourceSnapshot` records include the
guide id, canonical manifest JSON, bundle hash, and capture timestamp. Snapshot
items record source kind, sanitized durable ref, ingestion adapter, content
hash, optional future content id, media type, and capture timestamp. The bundle
hash is `sha256(canonical_json(manifest_json))`. Canonical JSON uses UTF-8,
sorted object keys, no insignificant whitespace, and source items sorted by
`(source_kind, durable_ref, content_hash)`. Volatile database ids, capture
timestamps, and transient fetch locators are excluded from the canonical
manifest. Duplicate source items with the same `source_kind + durable_ref` are
rejected before hashing. Changing any included document, example, rubric,
repository doc, or inline guide body creates a new snapshot and invalidates
prior sufficiency reports, derived policies, effective policies, checker specs,
checker bundles, acknowledgements, and approvals for activation.
A new guide-source snapshot invalidates prior setup records for new activation
and unlocked tasks only. Tasks already locked to an earlier snapshot retain
that policy context unless an explicit audited rebase occurs.

URL-backed guide ingestion separates the temporary fetch locator from durable
source identity. Approved retrieval adapters can fetch legitimate documentation
that uses ordinary query parameters. Query strings are temporary fetch inputs
only. Workstream must not persist query strings, signed URLs, credentials,
token-bearing refs, or local filesystem paths. The durable source record is an
opaque sanitized source ref plus content hash or future content id.

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

The derivation agent does not generate unrestricted executable checker code as
the default path. It produces a machine-readable artifact-intake contract and a
constrained pre-submit checker specification using Workstream-approved
primitives.

`SubmissionArtifactPolicy` is the Workstream-derived, admin-or-project-manager-approved machine-readable contract for worker submissions. It defines:

- required artifacts
- required evidence references
- artifact manifest rules
- artifact hash rules
- maximum file and package size rules
- allowed storage reference forms
- forbidden artifacts
- worker attestation requirements
- project-specific packaging requirements

Workstream owns a default submission artifact policy. Every project inherits it.

Project policy can add stricter requirements, but it cannot remove, weaken, downgrade, or bypass Workstream defaults.

Approval provenance is part of the policy contract. A policy record must make
approval testable with source/provenance state such as derivation source,
`lifecycle_status`, approver actor, approval timestamp, and approved policy
version/hash.

The runtime contract is:

```text
EffectiveProjectSubmissionArtifactPolicy =
  WorkstreamDefaultSubmissionArtifactPolicy
  + ProjectSubmissionArtifactPolicy

PreSubmitCheckerPolicy =
  trusted compiler output from EffectiveProjectSubmissionArtifactPolicy
```

`SubmissionArtifactPolicyDerivationAgent` produces a constrained checker
specification at project setup time. Workstream's trusted checker compiler
validates that specification and persists the project-level
`PreSubmitCheckerPolicy`.

Project policies define project-wide artifact intake rules for a guide
snapshot. The dominant operating model is one project guide, one effective
project policy, and one project pre-submit checker bundle reused by every task
under that guide version. `ProjectGuideSufficiencyAgent` is responsible for
checking that the guide and derived policy cover the project's task set. If the
guide does not cover the tasks, activation is blocked and the guide is improved
or the work is split into another project/guide. Workstream does not hide guide
coverage problems by generating new task-specific policies.

`PreSubmitCheckerPolicy` is locked to the effective project submission artifact policy hash. It is
not derived on read, manually edited by workers, or supplied by clients. Workers
submit only draft packet fields. They do not choose checker names, policy
versions, blocking rules, severities, or outcomes. Each task stores locked
references to the applicable guide snapshot, effective project submission artifact policy hash, and
pre-submit checker bundle hash before entering the worker pipeline. Task-specific
values are constrained runtime parameters consumed by the shared checker, not
new checker generation. For v0.1, those parameters come only from trusted
task-contract fields already owned by Workstream; there is no free-form
parameter map. Runtime parameters may fill placeholders, but they cannot change
required checks, severity, allowed storage, forbidden artifacts, hash algorithm,
or platform defaults.

The compiled `PreSubmitCheckerPolicy` is deterministic checker logic, not an
agent judgment loop. Runtime checks execute the locked compiled checker bundle
against exact staged artifact hashes or future content identifiers.

The compiler must prove semantic coverage between
`EffectiveProjectSubmissionArtifactPolicy` and the compiled checker bundle.
Every enforceable effective project policy rule must produce deterministic
checker logic. The compiler rejects checker specifications that omit a required
artifact, skip an evidence rule, weaken severity, omit a platform default, or
produce a bundle whose rules are not traceable back to the effective project
policy.

Approved pre-submit checker primitives include:

- `require_file`
- `allow_extension`
- `forbid_extension`
- `require_manifest_field`
- `validate_json_schema`
- `check_directory_structure`
- `require_minimum_evidence`
- `verify_hash`
- `limit_file_size`

Project-specific executable checker code is not part of the default path. If a
future project requires logic that cannot fit the constrained checker
specification, the extension path must require static validation, generated
tests, sandboxed execution, no network, no shell, no secrets, no database access,
`admin` or `project_manager` approval of the exact code hash after those checks
pass, and a locked code hash.

Blocking pre-submit failures prevent submission creation. When blocking pre-submit checks fail:

- no `Submission` row is created
- no submission version is assigned
- no task transition to `submitted` occurs
- no submission-created audit event is written
- the response does not use review decision values: `accept`, `needs_revision`, or `reject`

Pre-submit has two API contracts:

```text
POST /tasks/{id}/submission-precheck
200 PreSubmitCheckResponse
{
  "status": "failed",
  "eligible_to_submit": false,
  "results": [...]
}
```

```text
POST /tasks/{id}/submissions
422 DomainError
{
  "code": "pre_submission_checker_failed",
  "details": {
    "status": "failed",
    "eligible_to_submit": false,
    "results": [...]
  }
}
```

`pre_submission_checker_failed` is the submission-creation error code. It is not
a review decision and is not the response type for the preflight endpoint.

Pre-submit checks are authoritative for submission intake. They are not authoritative proof for human review readiness. Review readiness still requires post-submit internal checker runs against a locked submission.

## Implementation Enforcement Contract

This ADR defines the required product contract. `WS-POL-001-01` implements the
project setup records, source snapshot binding, effective project policy
materialization, and project pre-submit checker policy provenance. Downstream
pre-submit runtime execution and compiler enforcement remain in later chunks.

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
responses do not expose internal-only routes. If any UI or demo surface renders
pre-submit results, a later frontend/demo chunk must prove the same wording
separation before this ADR can be closed as fully implemented.

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

The effective policy merge is deterministic:

| Field | Merge rule |
| --- | --- |
| `required_artifacts` | union by canonical artifact key |
| `required_evidence` | union by canonical evidence key |
| `forbidden_artifacts` | union |
| `attestation_terms` | union |
| `manifest_required` | logical OR |
| `artifact_hash_required` | logical OR |
| `allowed_storage_schemes` | intersection |
| `artifact_hash_algorithm` | platform-locked `sha256`; project policy cannot change it and task runtime parameters cannot override it |
| `maximum_file_size_bytes` | minimum non-null limit |
| `maximum_package_size_bytes` | minimum non-null limit |
| `packaging` | restrictive merge; conflicts block activation |

Conflicts block setup before workers see tasks. A project-required artifact that
matches a forbidden rule is not accepted as a runtime edge case.

Approved policy and checker content, hashes, source bindings, and approval
provenance are immutable:

```text
draft      -> mutable
approved   -> immutable
superseded -> immutable
```

Changing an approved policy, effective policy, or compiled checker bundle
creates a new row with a `supersedes_*` reference. During that locked
replacement transaction, Workstream may update only the prior row's lifecycle
closeout metadata (`lifecycle_status = superseded`, `superseded_at`) for
operator-visible lineage. Policy bodies, effective policies, compiled bundles,
hashes, source snapshot bindings, and approval provenance are never edited in
place. For `PreSubmitCheckerPolicy`, `compiled_bundle` is the canonical JSON
source of truth and `compiled_bundle_hash` is the hash of that canonical JSON.
`checker_names` and `checker_configs` are derived index projections only.
Project guide APIs expose stable checker provenance and hash fields;
compiler-owned bundle internals are retrieved through the checker runtime
boundary.

Task, submission, and revision provenance fields named
`locked_pre_submit_checker_bundle_hash` store
`PreSubmitCheckerPolicy.compiled_bundle_hash`. They do not store
`PreSubmitCheckerPolicy.policy_hash`.

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
- post-submit checker policy must remain separate from generated project pre-submit checker policy
