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

The `guide_source_snapshot.v2` manifest uses UTF-8 canonical JSON with sorted
object keys and no insignificant whitespace. It includes server-owned snapshot,
generation, item id, and item order facts plus non-authoritative source metadata.
Caller byte hashes, content ids, excerpts, provider refs, and fetch locators are excluded.

Source snapshot items:

| Item ID | Item Order | Source Kind | Source Label | Ingestion Adapter | Media Type |
| --- | --- | --- | --- | --- | --- |
| `<server UUID>` | `<server order>` | `<approved kind>` | `<sanitized display label>` | `<adapter>` | `<declared media type>` |

Temporary fetch locators are adapter inputs only. Source labels must not
store query strings, signed URLs, credentials, token-bearing refs, local
filesystem paths, or private storage paths.

Caller excerpts are not accepted. Setup agents receive only canonical bounded
content produced from exact verified ART bindings and extraction usages.

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

All defaults are named and versioned in the central Workstream pre-submission
checker catalogue. The locked project policy adds constrained rules to that
same catalogue execution; it does not create another API or registry. Catalogue
availability is deployment-owned. A disabled mandatory entry makes submission
preparation unavailable, while a disabled advisory entry is explicitly recorded
and does not silently pass. Project configuration cannot disable either class.

Default required packet fields:

- summary
- contributor attestation

The hidden Workstream-default executor consumes these catalogue-owned semantics
without reading project-rule configuration. It validates one server-generated
sealed tree and emits only bounded, path-redacted same-request results. Project
rules are a later phase of the same effective plan, not a second checker API.

Workstream generates the archive commitment and semantic artifact manifest
after safely inspecting the submitted outer ZIP. Clients do not supply an
artifact hash manifest as packet input; later APIs may expose an immutable
server-generated manifest reference.

Default artifact rules:

- artifact paths must be relative
- artifact paths must not contain empty, `.`, or `..` segments
- uploaded artifacts and storage-backed evidence require `sha256:<64 lowercase hex>` hashes in production
- test fixtures may use deterministic placeholder hash tokens only in explicit local test paths
- Workstream normalizes regular-file executable intent from valid Unix ZIP mode
  metadata; non-Unix/invalid metadata defaults to non-executable
- executable intent participates in semantic identity, but never by itself
  authorizes a checker or service to execute the file

Default storage rules:

- clients submit exactly one outer ZIP through Workstream submission-bundle
  preparation and receive only Workstream operation/admission IDs
- persisted product references are immutable Workstream artifact bindings
- verified admissions may remain unbound and capacity-charged in `ready` or
  terminal `stale`; clients cannot expire, release, or delete them
- signed URLs, raw local filesystem paths, provider references, credentials,
  query strings, bucket secrets, and token-bearing references are rejected
  before persistence

Default high-confidence forbidden artifacts:

- `.env`
- `.git`
- exact known credential files
- exact known private-key files
- `.pem`
- `.key`

Broad names such as `token`, `secret`, `credential`, or dependency directories
are not universal blockers solely because a path contains the word. They must
be a narrowly defined high-confidence match, an advisory catalogue check, or a
locked project-specific rule.

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

Failed submission-bundle preparation returns
`pre_submission_checker_failed` with bounded same-request status, eligibility,
and pass/fail/warning details. The frozen legacy preflight endpoint remains
non-authoritative until WS-ARCH-001-02I removes it with the legacy Submission
path after every submission context and downstream prerequisite is live; no
ID-addressed evidence-read route exists. These results never use review decision values:
`accept`, `needs_revision`, or `reject`. After verified preparation,
final Submission creation consumes the ready admission under fresh authority
and does not rerun scratch-bound checks.

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
