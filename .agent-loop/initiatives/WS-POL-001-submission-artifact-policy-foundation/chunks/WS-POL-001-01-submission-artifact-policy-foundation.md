# Chunk Contract: WS-POL-001-01 - Guide Policy Bundle Foundation

## Parent Initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Add first-class backend support for immutable guide-source snapshots, guide
sufficiency reports, `SubmissionArtifactPolicy`, effective project submission
artifact policy hashes, append-only approval lifecycle, and activation guards without rewiring
submission creation, task runtime, checker compiler behavior, or durable checker
execution yet.

## Why This Chunk Exists

The code still uses transitional `evidence_policy`, `required_files`, and
`required_evidence` fields. Those fields are not compatibility contracts. They
must be replaced by the guide-policy bundle path before submission intake can be
deterministic.

Project owners must not be asked to author the Workstream policy schema
directly. They provide open-ended project guide material. Workstream records
guide-source snapshots, guide sufficiency, project submission artifact policy,
effective project submission artifact policy hash, and a Workstream actor with
the `admin` or `project_manager` role approves the bundle before guide
activation.

The generated project pre-submit checker policy is deterministic compiled policy, not
unrestricted generated checker code. This first chunk defines the record
contract and activation dependency; the async derivation and trusted compiler
behavior land in the next chunk.

Project owner material is untrusted input. Guide text, URLs, repository docs,
examples, and imported documents cannot grant tool authority, override
Workstream rules, or weaken default checks. Approved adapters can use temporary
fetch locators for source ingestion, but durable source identity must be an
immutable `GuideSourceSnapshot` bundle with a canonical manifest, sanitized
source item refs, and per-item content hashes.

## Approved Plan Reference

- INTENT: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md`

## Current Planning PR Scope

PR #26 is the planning approval PR for this initiative. It may update the
initiative plan, chunk map, architecture docs, operating docs, templates, and
engineering-loop gates needed to make the implementation contract unambiguous.

The implementation scope below applies after this planning PR is approved. It
does not authorize runtime product behavior in the planning PR, and it does not
require the planning PR to be limited to backend implementation files.

Planning PR scope exceptions:

- `.agent-loop/**`
- `docs/**`
- `scripts/check_stale_workstream_wording.py`
- `scripts/test_agent_gates.py`

Planning PR non-scope:

- product runtime behavior
- database schema changes
- API behavior changes
- frontend/demo changes
- workflow/dependency changes
- payment, reputation, settlement, or blockchain code

## Risk Class

L1

## SLA

P1

## Implementation Allowed Files

```text
backend/alembic/versions/**
backend/app/modules/projects/**
backend/tests/test_projects.py
docs/spec_chunk_3_project_guide_foundation.md
docs/template_submission_artifact_policy.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

## Implementation Not Allowed

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/app/modules/submissions/**
.github/workflows/**
demos/**
examples/**
frontend/**
payment/reputation/blockchain code
object-storage implementation
human review implementation
```

## Implementation Boundaries

- Routers only translate HTTP requests/responses and map domain errors.
- Services own policy merge rules, Workstream default validation, guide
  sufficiency gating, guide activation checks, Workstream-owned policy
  derivation boundaries, and permission-aware orchestration.
- Repositories only persist and query policy records.
- Schemas only define API input/output contracts and validation shape.
- Full async agent execution is not part of this chunk. This chunk models the
  records/contracts and activation guard those agents will use.
- Trusted checker compiler behavior is not part of this chunk. This chunk
  models the persisted fields and invariants later compiler output must satisfy.

## Acceptance Criteria

- [ ] Dedicated `SubmissionArtifactPolicy` model/table exists.
- [ ] Dedicated immutable `GuideSourceSnapshot` bundle model/table exists.
- [ ] Dedicated `GuideSourceSnapshotItem` model/table exists, or the snapshot
      stores an equivalent canonical manifest for every source item.
- [ ] `GuideSourceSnapshot.bundle_hash` is computed as
      `sha256(canonical_json(manifest_json))` using UTF-8, sorted object keys,
      no insignificant whitespace, deterministic source-item ordering,
      volatile-field exclusions, and duplicate source-item rejection.
- [ ] Dedicated `GuideSufficiencyReport` model/table exists.
- [ ] Guide sufficiency report records `passed`, `blocked`, or
      `passed_with_warnings`.
- [ ] Guide sufficiency report binds to `source_snapshot_id` and server-derived
      `source_snapshot_hash` from `GuideSourceSnapshot.bundle_hash`.
- [ ] Blocking guide sufficiency findings prevent guide activation.
- [ ] Warning guide sufficiency findings require `admin` or `project_manager`
      acknowledgement before guide activation.
- [ ] Durable source snapshot item refs are sanitized and reject signed URLs,
      credential-bearing refs, token-bearing refs, and local filesystem paths.
- [ ] Approved retrieval adapters can use ordinary URL query parameters only as
      temporary fetch locators and never persist them as durable source
      authority.
- [ ] Embedded instructions in guide material cannot grant tool authority or
      weaken Workstream default policy.
- [ ] Policy rows are scoped by `project_id` and `guide_version`.
- [ ] Policy rows have a composite foreign key to `project_guides(project_id, version)`.
- [ ] Policy rows bind to `source_snapshot_id` and server-derived
      `source_snapshot_hash` from `GuideSourceSnapshot.bundle_hash`.
- [ ] Pydantic input/output schemas exist for project submission artifact policy.
- [ ] Project service can create/update the policy with a draft guide.
- [ ] Project policy records include approval provenance showing the approved
      machine policy was reviewed by `admin` or `project_manager`.
- [ ] Approval provenance includes derivation source, source material refs,
      lifecycle status, approver role, approver actor, approval timestamp, and
      approved policy version or hash.
- [ ] Guide activation fails when no approved project submission artifact policy
      exists for the guide version.
- [ ] Guide activation requires valid submission artifact policy.
- [ ] The activation contract models project `PreSubmitCheckerPolicy` as a
      required final activation dependency; Chunk 2 enforces it after compiler
      execution exists.
- [ ] Workstream default submission artifact policy is represented in code.
- [ ] Workstream default policy requires `sha256:<64 lowercase hex>` artifact hashes where production hashes are required.
- [ ] Persisted artifact/storage refs reject raw signed URLs, query strings,
      local filesystem paths, credential-bearing references, and token-bearing
      storage references before persistence.
- [ ] Workstream default policy blocks default-forbidden secret/token artifacts even when a project policy lists them as required.
- [ ] Effective project policy merge implements deterministic rules for union,
      intersection, logical OR, minimum limit, platform-locked hash algorithm,
      and restrictive packaging merges.
- [ ] Effective project policy merge rejects project policy that weakens defaults.
- [ ] Required artifact or evidence rules that match forbidden rules block
      project setup as conflicts.
- [ ] Effective project submission artifact policy hash is persisted for the guide version.
- [ ] Approved and superseded policy/effective-policy rows are immutable.
- [ ] Changing an approved policy creates a new revision with a supersedes
      pointer.
- [ ] Legacy `evidence_policy`, `required_files`, and `required_evidence` are
      not treated as compatibility aliases. Runtime replacement of task fields
      happens in the task locked-context and submission migration chunk.
- [ ] Postgres-backed FastAPI/API tests cover create/update, blocking activation
      from guide sufficiency gaps, `admin`/`project_manager` warning
      acknowledgement, approval provenance fields, default weakening,
      source snapshot binding, source-ref sanitization, append-only rows, and
      effective project submission artifact policy hash persistence.

## Verification Commands

```bash
cd backend && .venv/bin/python -m ruff check app tests
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
```

## Required Reviewers

Every listed reviewer must end with one exact result value:

- `PASS`
- `PASS AFTER FIXES`
- `PASS WITH LOW RISKS`
- `N/A - with approved reason`

Baseline:

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops

Conditional:

- [ ] architecture
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta
- [ ] CI integrity: `N/A - with approved reason` unless workflows or test tooling change

## Human Review Focus

- Are the guide sufficiency report fields precise enough?
- Are the guide source snapshot fields precise enough?
- Are the persisted provenance field names precise enough?
- Does this chunk stay limited to records/contracts/activation guard, leaving
  full async agent execution, trusted compiler behavior, task locked context, and
  submission runtime migration for later chunks?

## Stop Conditions

Stop and escalate if:

- implementation needs to touch task/submission/checker runtime in this chunk
- policy version/hash naming is unclear
- guide sufficiency severity naming is unclear
- migration requires preserving old transitional fields as compatibility aliases
- CI/test weakening is required to pass
- same blocker remains after 2 repair attempts
- secrets or production data are needed
