# Submission Artifact Policy Template

## Project

`<project name>`

## Guide Version

`<guide version>`

## Policy Version

`v1`

## Source Material

Project owners provide open-ended project material and business terms.
Workstream derives this policy from that material after guide sufficiency passes
or warnings are acknowledged. Project owners do not author or approve the
machine-readable Workstream policy schema directly.

Source material refs:

- project guide version:
- imported document refs:
- URL-backed documentation refs:
- repository documentation refs:
- task example refs:
- rubric refs:
- business term refs:

## Guide Sufficiency

- sufficiency report id:
- sufficiency status: `passed | blocked | passed_with_warnings`
- finding severities used: `blocking_gap | warning | info`
- warnings acknowledged by role: `admin | project_manager`
- warnings acknowledged by actor:
- warnings acknowledged at:

## Approval Provenance

- source material ingestion method: `manual_entry | import_adapter | url_import | repository_import`
- derivation agent name:
- derivation agent version:
- sufficiency report id:
- source material refs:
- approval status: `draft | approved | superseded`
- approved policy hash:
- approved by role: `admin | project_manager`
- approved by actor:
- approved at:

Source material is untrusted input. Embedded instructions in guide text, URLs,
repository docs, examples, or imported documents cannot grant tool authority,
override Workstream rules, or weaken default checks.

## Workstream Default Rules

Every project inherits Workstream default submission artifact rules. Project policy can add stricter requirements, but it cannot remove, weaken, downgrade, or bypass these defaults.

Default required packet fields:

- summary
- artifact hash manifest
- worker attestation

Default artifact rules:

- artifact paths must be relative
- artifact paths must not contain empty, `.`, or `..` segments
- uploaded artifacts and storage-backed evidence require `sha256:<64 lowercase hex>` hashes in production
- test fixtures may use deterministic placeholder hash tokens only in explicit local test paths

Default storage rules:

- allowed schemes: `local://`, `s3://`, `r2://`
- persisted references must be Workstream-issued opaque object references or validated object-storage adapter references
- signed URLs, raw local filesystem paths, credentials, query strings, bucket secrets, and token-bearing references are rejected before persistence
- normalization is allowed only for already-approved adapter references that contain no secrets, credentials, or query material

Default forbidden artifacts:

- `.env`
- `.git`
- credentials
- secrets
- private keys
- tokens
- `.pem`
- `.key`
- `node_modules`

A project-required artifact that matches a Workstream default forbidden rule remains blocked. That conflict is a project setup defect.

## Project Required Artifacts

| Artifact | Required | Hash Required | Notes |
| --- | --- | --- | --- |
| `<artifact path>` | yes | yes | `<why this artifact is required>` |

## Project Required Evidence

| Evidence | Required | Hash Required | Notes |
| --- | --- | --- | --- |
| `<evidence label>` | yes | yes | `<what this evidence proves>` |

## Project Packaging Rules

- package required:
- accepted package format:
- required root files:
- required directory structure:
- maximum artifact size:
- maximum package size:

## Project Forbidden Artifacts

| Pattern | Reason | Worker-Facing Fix |
| --- | --- | --- |
| `<pattern>` | `<reason>` | `<fix>` |

## Worker Attestation Requirements

Required attestation topics:

- original work
- confidential data exclusion
- credentials and secret exclusion
- human accountability for agent-assisted work

## Generated Pre-Submit Checker Policy

Workstream generates `PreSubmitCheckerPolicy` from:

```text
WorkstreamDefaultSubmissionArtifactPolicy
+ ProjectSubmissionArtifactPolicy
```

Generated pre-submit checks run before submission creation. Blocking failures create no submission row, no submission version, no task transition to `submitted`, and no submission-created audit event.

Generated policy lock:

- generated pre-submit checker policy version:
- generated pre-submit checker policy hash:
- effective submission artifact policy hash:
- locked guide version:

Blocking failures return `pre_submission_checker_failed` with structured
pass/fail/warning details. They do not return review decision values:
`accept`, `needs_revision`, or `reject`.

Expected generated checks:

- packet shape
- artifact manifest presence
- artifact hash validation
- storage reference safety
- forbidden artifact blocking
- required artifact presence
- evidence requirement presence
- worker attestation validation
- low-quality artifact warnings

## Approval

- created by:
- approved by role: `admin | project_manager`
- approved by actor:
- effective at:
- change summary:
