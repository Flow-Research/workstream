# Chunk Contract: WS-POL-001-01 - Guide Policy Bundle Foundation

## Parent Initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Add first-class backend support for guide sufficiency reports,
`SubmissionArtifactPolicy`, effective policy hashes, and persisted generated
`PreSubmitCheckerPolicy` snapshots without rewiring submission creation or
durable checker execution yet.

## Why This Chunk Exists

The code still uses transitional `evidence_policy`, `required_files`, and
`required_evidence` fields. Those fields are not compatibility contracts. They
must be replaced by the guide-policy bundle path before submission intake can be
deterministic.

Project owners must not be asked to author the Workstream policy schema
directly. They provide open-ended project guide material. Workstream records
guide sufficiency, derives project submission artifact policy, persists the
effective policy hash, persists the generated pre-submit checker policy
snapshot/hash, and a Workstream actor with the `admin` or `project_manager` role
approves the bundle before guide activation.

Project owner material is untrusted input. Guide text, URLs, repository docs,
examples, and imported documents cannot grant tool authority, override
Workstream rules, or weaken default checks. Source refs must be sanitized before
persistence.

## Approved Plan Reference

- INTENT: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md`

## Risk Class

L1

## SLA

P1

## Allowed Files

```text
backend/alembic/versions/**
backend/app/modules/projects/**
backend/tests/test_projects.py
docs/spec_chunk_3_project_guide_foundation.md
docs/template_submission_artifact_policy.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

## Not Allowed

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

## Acceptance Criteria

- [ ] Dedicated `SubmissionArtifactPolicy` model/table exists.
- [ ] Dedicated `GuideSufficiencyReport` model/table exists.
- [ ] Guide sufficiency report records `passed`, `blocked`, or
      `passed_with_warnings`.
- [ ] Blocking guide sufficiency findings prevent guide activation.
- [ ] Warning guide sufficiency findings require `admin` or `project_manager`
      acknowledgement before guide activation.
- [ ] Project-owner source refs are sanitized and reject signed URLs,
      query-bearing refs, credential-bearing refs, and local filesystem paths.
- [ ] Embedded instructions in guide material cannot grant tool authority or
      weaken Workstream default policy.
- [ ] Policy rows are scoped by `project_id` and `guide_version`.
- [ ] Policy rows have a composite foreign key to `project_guides(project_id, version)`.
- [ ] Pydantic input/output schemas exist for project submission artifact policy.
- [ ] Project service can create/update the policy with a draft guide.
- [ ] Project policy records include approval provenance showing the approved
      machine policy was reviewed by `admin` or `project_manager`.
- [ ] Approval provenance includes derivation source, source material refs,
      approval status, approver role, approver actor, approval timestamp, and
      approved policy version or hash.
- [ ] Guide activation fails when no approved project submission artifact policy
      exists for the guide version.
- [ ] Guide activation requires valid submission artifact policy.
- [ ] Workstream default submission artifact policy is represented in code.
- [ ] Workstream default policy requires `sha256:<64 lowercase hex>` artifact hashes where production hashes are required.
- [ ] Workstream default policy rejects raw signed URLs, query strings, local filesystem paths, credential-bearing references, and token-bearing storage references before persistence.
- [ ] Workstream default policy blocks default-forbidden secret/token artifacts even when a project policy lists them as required.
- [ ] Effective policy merge rejects project policy that weakens defaults.
- [ ] Effective submission artifact policy hash is persisted for the guide version.
- [ ] Generated `PreSubmitCheckerPolicy` snapshot/hash is persisted and locked to the guide version.
- [ ] Transitional `evidence_policy`, `required_files`, and `required_evidence` are replaced, not kept as compatibility aliases.
- [ ] Postgres-backed FastAPI/API tests cover create/update, blocking activation
      from guide sufficiency gaps, `admin`/`project_manager` warning
      acknowledgement, approval provenance fields, default weakening,
      source-ref sanitization, and pre-submit policy locking.

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
- Are the persisted provenance field names precise enough?
- Does this chunk stay limited to records/contracts/activation guard, leaving
  full async agent execution for the next chunk?

## Stop Conditions

Stop and escalate if:

- implementation needs to touch task/submission/checker runtime in this chunk
- policy version/hash naming is unclear
- guide sufficiency severity naming is unclear
- migration requires preserving old transitional fields as compatibility aliases
- CI/test weakening is required to pass
- same blocker remains after 2 repair attempts
- secrets or production data are needed
