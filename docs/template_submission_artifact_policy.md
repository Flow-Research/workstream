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
or passes with warnings. Project owners do not author or approve the
machine-readable Workstream policy schema directly. Sufficiency warnings must be
acknowledged before this policy can be approved or used for guide activation.

Source snapshot:

- guide source snapshot id:
- guide source snapshot bundle hash:
- manifest json:
- captured at:

Bundle hash algorithm:

```text
sha256(canonical_json(manifest_json))
```

Canonical JSON uses UTF-8, sorted object keys, no insignificant whitespace, and
source items sorted by `(source_kind, durable_ref, content_hash)`. Exclude
database ids, capture timestamps, and transient fetch locators. Reject duplicate
source items with the same `source_kind + durable_ref` before hashing.

Source snapshot items:

| Source Kind | Durable Ref | Ingestion Adapter | Content Hash | Artifact Content ID | Media Type | Content Excerpt |
| --- | --- | --- | --- | --- | --- | --- |
| `<inline_markdown / url_doc / repository_doc / example / rubric / imported_file / representative_task / task_sample>` | `<opaque sanitized ref>` | `<adapter>` | `sha256:<hash>` | `<ArtifactContent id after ingest>` | `<media type>` | `<bounded untrusted excerpt when needed>` |

Temporary fetch locators are adapter inputs only. Durable source refs must not
store query strings, signed URLs, credentials, token-bearing refs, local
filesystem paths, or private storage paths.

`content_excerpt` is optional, bounded, and included in the source snapshot
bundle hash when present. It is source material for setup agents only; it cannot
grant authority, weaken defaults, or replace deterministic checker rules.

## Guide Sufficiency

- sufficiency report id:
- sufficiency status: `passed | blocked | passed_with_warnings`
- finding severities used: `blocking_gap | warning | info`
- warnings acknowledged by Project Manager grant id:
- warnings acknowledged by ActorProfile id:
- warnings acknowledged at:

## Approval Provenance

- source material ingestion method: `manual_entry | import_adapter | url_import | repository_import`
- derivation agent name:
- derivation agent version:
- sufficiency report id:
- source snapshot id:
- source snapshot bundle hash:
- lifecycle status: `draft | approved | superseded`
- approved policy hash:
- approved by Project Manager grant id:
- approved by ActorProfile id:
- approved at:

Source material is untrusted input. Embedded instructions in guide text, URLs,
repository docs, examples, or imported documents cannot grant tool authority,
override Workstream rules, or weaken default checks.

## Workstream Default Rules

Every project inherits Workstream default submission artifact rules. Project policy can add stricter requirements, but it cannot remove, weaken, downgrade, or bypass these defaults.

Default required packet fields:

- summary
- artifact hash manifest
- contributor attestation

Default artifact rules:

- artifact paths must be relative
- artifact paths must not contain empty, `.`, or `..` segments
- uploaded artifacts and storage-backed evidence require `sha256:<64 lowercase hex>` hashes in production
- test fixtures may use deterministic placeholder hash tokens only in explicit local test paths

Default storage rules:

- clients submit bytes through Workstream upload sessions and receive only
  Workstream artifact IDs
- persisted product references are immutable Workstream artifact bindings
- signed URLs, raw local filesystem paths, provider references, credentials,
  query strings, bucket secrets, and token-bearing references are rejected
  before persistence

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

## Effective Policy Merge Rules

| Field | Merge Rule |
| --- | --- |
| required artifacts | union by canonical artifact key |
| required evidence | union by canonical evidence key |
| forbidden artifacts | union |
| attestation terms | union |
| manifest required | logical OR |
| hash required | logical OR |
| allowed storage schemes | intersection |
| hash algorithm | platform-locked `sha256`; project policy cannot change it and task runtime parameters cannot override it |
| maximum file size bytes | minimum non-null limit |
| maximum package size bytes | minimum non-null limit |
| packaging rules | restrictive merge; conflicts block setup |

## Project Required Artifacts

| Key | Path | Required | Hash Required | Description |
| --- | --- | --- | --- | --- |
| `<canonical artifact key>` | `<safe relative path>` | yes | yes | `<why this artifact is required>` |

`key` is the canonical merge identity. Two artifact rules with the same key must be identical or setup blocks.

## Project Required Evidence

| Key | Label | Required | Hash Required | Description |
| --- | --- | --- | --- | --- |
| `<canonical evidence key>` | `<contributor-facing label>` | yes | yes | `<what this evidence proves>` |

`key` is the canonical merge identity. `label` is contributor-facing display text.

## Project Packaging Rules

- package required:
- accepted package format:
- required root files:
- required directory structure:
- maximum file size bytes:
- maximum package size bytes:

## Project Forbidden Artifacts

| Pattern | Reason | Contributor-Facing Fix |
| --- | --- | --- |
| `<pattern>` | `<reason>` | `<fix>` |

## Contributor Attestation Requirements

Required attestation topics:

- original work
- confidential data exclusion
- credentials and secret exclusion
- human accountability for agent-assisted work

## Generated Pre-Submit Checker Policy

Workstream generates project-level `PreSubmitCheckerPolicy` from:

```text
EffectiveProjectSubmissionArtifactPolicy
+ constrained checker specification
```

Pre-submit checks from the locked project pre-submit checker policy run before submission creation. Blocking failures create no submission row, no submission version, no task transition to `submitted`, and no submission-created audit event.

Compiler coverage requirement:

- every enforceable effective project policy rule maps to deterministic checker logic
- required artifacts and evidence rules cannot be omitted
- Workstream defaults cannot be omitted or weakened
- severity cannot be downgraded by project policy or task runtime parameters

Generated policy lock:

- generated project pre-submit checker policy version:
- generated project pre-submit checker bundle hash:
- effective project submission artifact policy hash:
- locked guide version:

Tasks lock this project checker compiled bundle hash before entering the contributor pipeline. Tasks
do not derive or compile their own checker by default.

Blocked submission-create attempts return `pre_submission_checker_failed` with
structured pass/fail/warning details.
The preflight endpoint returns `PreSubmitCheckResponse` with `status`,
`eligible_to_submit`, and `results`. Neither path returns review decision
values: `accept`, `needs_revision`, or `reject`.

Expected generated checks:

- packet shape
- artifact manifest presence
- artifact hash validation
- storage reference safety
- forbidden artifact blocking
- required artifact presence
- evidence requirement presence
- contributor attestation validation
- low-quality artifact warnings

## Approval

- created by:
- approved by Project Manager grant id:
- approved by ActorProfile id:
- effective at:
- change summary:
- supersedes policy id:

Approved and superseded policies are immutable. Changes create a new revision.
