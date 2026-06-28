# PR Trust Bundle: WS-POL-001-01

## Chunk

`WS-POL-001-01` - Guide Policy Bundle Foundation

## Goal

Implement the backend foundation for Workstream's project-scoped submission
artifact policy path without moving task runtime yet.

## Human-Approved Intent

- Intent: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- Plan: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- Chunk contract: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-01-submission-artifact-policy-foundation.md`

## What Changed

- Added immutable guide-source snapshot bundle tables and source snapshot item records.
- Added guide sufficiency reports with blocking and warning acknowledgement gates.
- Added `SubmissionArtifactPolicy`, `EffectiveProjectSubmissionArtifactPolicy`, and project-scoped `PreSubmitCheckerPolicy` records.
- Added API routes and service/repository logic for source snapshots, sufficiency reports, policy create/update/approval, and active guide bundle responses.
- Added Workstream default submission artifact policy rules and deterministic merge behavior.
- Fixed effective required-artifact merging so canonical artifact `key`, not `path`, is the merge identity.
- Hardened activation so a guide cannot activate unless the project pre-submit checker policy is `compiled` and its compiled bundle hash matches canonical bundle JSON.
- Updated Week 1 real API E2E and existing backend tests to create the required setup bundle before activation.

## Scope Control

Allowed files changed:

- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**`
- `backend/alembic/versions/0006_submission_artifact_policy_foundation.py`
- `backend/app/db/models.py`
- `backend/app/modules/projects/**`
- `backend/tests/test_projects.py`
- `backend/tests/test_tasks.py`
- `backend/tests/test_checkers.py`
- `backend/scripts/week1_api_e2e.py`
- `docs/architecture_data_model.md`
- `docs/decision_0011_submission_artifact_policy_drives_pre_submit.md`
- `docs/operations_project_operating_manual.md`
- `docs/spec_chunk_3_project_guide_foundation.md`
- `docs/template_submission_artifact_policy.md`

Files outside scope:

- None.

## Product Behavior

Product behavior changed in the project setup API only. This PR does not move
task runtime or submission runtime to the new policy path.

Guide activation now requires:

- current immutable guide-source snapshot
- passed or acknowledged guide sufficiency report
- approved submission artifact policy with setup-role provenance
- approved effective project submission artifact policy hash
- compiled project pre-submit checker policy bundle/hash
- existing post-submit checker, review, revision, and payment policies

## Acceptance Criteria Proof

- Source snapshot bundle tables and canonical hash: `backend/tests/test_projects.py`
- Source ref/CID sanitization: `backend/tests/test_projects.py`
- Guide sufficiency blocking and warning acknowledgement: `backend/tests/test_projects.py`
- Policy approval provenance and append-only supersession: `backend/tests/test_projects.py`
- Effective policy merge and default non-weakening: `backend/tests/test_projects.py`
- Required artifact merge by canonical key: `backend/tests/test_projects.py`
- Compiled pre-submit checker activation guard: `backend/tests/test_projects.py`
- Active guide bundle response: `backend/tests/test_projects.py`
- Real API lifecycle drill: `backend/scripts/week1_api_e2e.py`

## Tests And Checks Run

```bash
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py -q -k 'default_artifact_key_conflict or dedupes_identical_default_artifact_key or rejects_default_weakening'
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
docker compose exec -T postgres psql -U workstream -d workstream_test -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week1_api_e2e.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
```

Result summary:

```text
Focused merge-key tests passed: 3 passed, 155 deselected.
Full ruff passed.
Docstring coverage passed: 100.0% (435/435).
Full backend test suite passed: 249 passed in 1004.33s.
Week 1 real API E2E passed.
Markdown link check passed for 12 changed Markdown files.
Stale wording check passed.
Agent gate returned REVIEW_REQUIRED as expected for L1 risky-path work.
git diff --check passed.
```

## Reviewer Results

Reviewed code SHA: `a77845bfe041c3fa8d7f9b25b928e76060049ec2`

Reviewed at: `2026-06-28T08:56:12Z`

Reviewer run IDs: see `WS-POL-001-01-internal-review-evidence.md`.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Low follow-ups on artifact/evidence key grammar and `required` field strictness. |
| QA/test | PASS WITH LOW RISKS | None | Confirmed required artifacts merge by canonical key and API regressions cover conflict/dedupe. |
| security/auth | PASS WITH LOW RISKS | None | No blocking auth/source-ref/hash/lifecycle finding; low setup-gate audit follow-ups documented. |
| product/ops | PASS WITH LOW RISKS | None | Confirmed project-scoped setup and pre-submit semantics remain clear. |
| architecture | PASS WITH LOW RISKS | None | Confirmed no per-task checker model drift and no forbidden runtime module edits. |
| CI integrity | N/A - with approved reason | N/A | No workflow, package-script, coverage-threshold, dependency, or test-tooling files changed. |
| docs | PASS | None | Confirmed submission artifact policy template matches the schema. |
| reuse/dedup | PASS WITH LOW RISKS | None | Temporary compiler-stub duplication accepted until Chunk 2. |
| test delta | PASS | None | Tests strengthened; no skipped, deleted, or weakened assertions. |

## External Review

External review is tracked separately in
`.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-01-external-review-response.md`.
For PR #28, GitHub Actions and CodeRabbit passed; the PR is non-draft and
mergeable. Human merge approval is still pending.

## Remaining Risks

- Chunk 2 must replace direct test/E2E compiled-field mutation with the trusted compiler path.
- Chunk 2 should define artifact/evidence key grammar and final `required` field semantics before compiler/runtime consumption.
- Chunk 2 or a setup-hardening follow-up should make sufficiency reports draft-only and warning acknowledgement idempotent.
- Chunk 3 must add task locked-context fields and move submission runtime to the locked project checker bundle.

## Human Review Focus

Please inspect:

- migration and model constraints for policy provenance and compiled checker rows
- `ProjectService` merge/sanitization/activation logic
- the new API routes and response shape for active guide bundle
- test coverage around default non-weakening, source ref sanitization, activation blocking, supersession, and required artifact merge by canonical key

## Human Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
