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
- Hardened activation so a guide cannot activate unless the project pre-submit checker policy is `compiled` and its compiled bundle hash matches canonical bundle JSON.
- Updated Week 1 real API E2E and existing backend tests to create the required setup bundle before activation.

## Scope Control

Allowed files changed:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**`
- `.agent-loop/LOOP_STATE.md`
- `backend/alembic/versions/0006_submission_artifact_policy_foundation.py`
- `backend/app/db/models.py`
- `backend/app/modules/projects/**`
- `backend/tests/test_projects.py`
- `backend/tests/test_tasks.py`
- `backend/tests/test_checkers.py`
- `backend/scripts/week1_api_e2e.py`
- `docs/spec_chunk_3_project_guide_foundation.md`

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
- Compiled pre-submit checker activation guard: `backend/tests/test_projects.py`
- Active guide bundle response: `backend/tests/test_projects.py`
- Real API lifecycle drill: `backend/scripts/week1_api_e2e.py`

## Tests And Checks Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py -q
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week1_api_e2e.py
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check origin/main..HEAD
```

Result summary:

```text
ruff passed.
Project test suite passed: 74 passed.
Backend test suite passed: 165 passed.
Week 1 real API E2E passed.
Docstring coverage passed: 100.0%.
Markdown link check passed.
Stale wording check passed.
Agent gate returned REVIEW_REQUIRED as expected for L1 risky-path work.
git diff --check passed.
```

## Reviewer Results

Reviewed code SHA: `de41f8701eb2ce98b2e355d984c60d9c0a0e7a34`

Reviewed at: `2026-06-27T13:31:03Z`

Reviewer run IDs: see `WS-POL-001-01-internal-review-evidence.md`.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Low risks documented for later active-guide validation reuse and duplicate snapshot conflict mapping. |
| QA/test | PASS AFTER FIXES | None | Packaging merge and compiled bundle hash issues fixed. |
| security/auth | PASS AFTER FIXES | None | Encoded source ref, approval provenance, and compiled bundle hash issues fixed. |
| product/ops | PASS AFTER FIXES | None | Activation no longer accepts pending or corrupt pre-submit checker context. |
| architecture | PASS WITH LOW RISKS | None | Production runtime remains project-scoped and no per-task checker generation was added. |
| CI integrity | PASS AFTER FIXES | None | Evidence was the only pending lifecycle gate. |
| docs | PASS AFTER FIXES | None | Contract/spec/plan verification wording fixed; evidence is now current. |
| reuse/dedup | PASS WITH LOW RISKS | None | Temporary duplicated compiler fixture helpers accepted until Chunk 2. |
| test delta | PASS WITH LOW RISKS | None | Tests strengthened; no skip/weakened assertions found. |

## Remaining Risks

- Chunk 2 must replace direct test/E2E compiled-field mutation with the trusted compiler path.
- Chunk 3 must add task locked-context fields and move submission runtime to the locked project checker bundle.
- Active-guide reads should fail closed on drift before task locked-context relies on them.
- Duplicate source snapshot conflicts should be mapped to a clean API response later.

## Human Review Focus

Please inspect:

- migration and model constraints for policy provenance and compiled checker rows
- `ProjectService` merge/sanitization/activation logic
- the new API routes and response shape for active guide bundle
- test coverage around default non-weakening, source ref sanitization, activation blocking, and supersession

## Human Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
