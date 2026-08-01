# Chunk Contract: WS-XINT-003-02A — REV Policy Persistence Adoption

## Goal

Adopt the existing ReviewPolicy and RevisionPolicy tables as immutable,
versioned REV-owned history on current main, preserving legacy facts losslessly
and removing four unused legacy mutation/construction callables. Activate no
route or ActionId.

## Why this chunk exists

PR #195 proved useful persistence semantics but was built from migration head
0033 and an obsolete independent REV writer contract. Current main is at
`0045_guide_metadata_authority`. This child rebuilds only the valid persistence
boundary and leaves external mutation to 02B.

## Risk class

L1 database policy history and downgrade safety.

## Allowed files

```text
backend/alembic/versions/0046_review_revision_policy_persistence.py
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/tests/conftest.py
backend/tests/test_alembic.py
backend/tests/test_projects.py
backend/tests/test_tasks.py
backend/tests/test_artifact_admission.py
backend/scripts/api_contract_e2e.py
docs/architecture_data_model.md
docs/template_project_guide.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/**
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/STATUS.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-03P-review-revision-policy-persistence.md
```

## Not allowed

- Router, authorization catalogue/PREP/runtime, ActionId availability, grant,
  permission, audit-decision, queue, lease, Review, finding, revision execution,
  ART, CON, Task transition, Submission, frontend, or dependency changes.
- A second policy table/model, compatibility alias, in-place active-policy
  update, public writer, or callable legacy upsert/construction path.

## Acceptance criteria

- Migration 0046 descends only from 0045 and creates no second head.
- Existing rows preserve retired values without inventing actor/provenance;
  canonical rows expose explicit policy version/provenance and exact REV tokens.
- Each table has an integer `policy_generation`, immutable policy identity,
  created provenance, nullable supersession provenance, and one database-enforced
  current row per exact project/guide lineage. Migration-existing rows become
  generation 1; 02A does not invent a human superseding actor.
- The database refuses update, delete, and truncate of immutable/activated
  policy history and serializes draft-policy persistence with guide activation.
- Downgrade is lossless only for untouched migrated legacy rows and refuses
  before DDL when canonical history cannot be represented at 0045.
- Models/schemas/read responses distinguish legacy-incomplete from canonical
  policy facts without treating archival fields as active semantics.
- `upsert_review_policy`, `upsert_revision_policy`, `_review_policy_model`, and
  `_revision_policy_model` are absent, with no replacement public writer.
- Internal `add_review_policy_version()` and
  `add_revision_policy_version()` primitives append only, reject caller-facing
  update semantics, and remain unused until 02B.
- Both policy ActionIds remain planned; no route or review lifecycle behavior
  becomes available.
- Focused catalogue and OpenAPI proof confirms both policy actions remain
  planned and no policy mutation route is registered.

## Verification commands

```text
cd backend && .venv/bin/alembic heads
cd backend && .venv/bin/pytest -q tests/test_alembic.py -k review_revision_policy
cd backend && .venv/bin/pytest -q tests/test_projects.py -k 'review_policy or revision_policy'
cd backend && .venv/bin/pytest -q tests/test_tasks.py -k 'review_policy or revision_policy'
cd backend && .venv/bin/pytest -q tests/test_artifact_admission.py::test_committed_put_and_independent_verification_are_fenced
cd backend && .venv/bin/pytest -q tests/test_authorization.py -k 'project_mutation_actions_cannot_issue_prepared_handles_while_planned or project_mutation_resources_and_prepared_scopes_are_closed'
cd backend && .venv/bin/ruff check app/modules/projects tests/conftest.py tests/test_alembic.py tests/test_projects.py tests/test_tasks.py tests/test_artifact_admission.py alembic/versions/0046_review_revision_policy_persistence.py
cd backend && .venv/bin/pytest --cov=app.modules.projects.models --cov=app.modules.projects.repository --cov=app.modules.projects.schemas --cov-branch --cov-report=term-missing --cov-fail-under=90 -q tests/test_projects.py -k 'review_policy or revision_policy'
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

The full suite and coverage floor run in GitHub Actions.

## Required reviewers

Senior engineering, QA/test, security/data, product/ops, architecture,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

Lossless legacy handling, append-only history, draft/activation race safety,
downgrade refusal, removal of dead writers, and absence of activation.

## Stop

Merge and stop. Do not begin 02B automatically.
