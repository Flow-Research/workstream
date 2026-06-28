# Internal Review Evidence: WS-POL-001-01

## Chunk

WS-POL-001-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: a77845bfe041c3fa8d7f9b25b928e76060049ec2

Reviewed at: 2026-06-28T08:56:12Z

Reviewer run IDs: 019f0d6a-6dcb-76e0-8e72-8fc54cda1f48, 019f0d6a-70f0-7e53-ba62-595b136610a9, 019f0d6a-73e8-7d72-9666-f7a486ac9017, 019f0d6a-770b-7b61-a0b8-c6e0a99a2faa, 019f0d6a-7d04-70a0-9aad-6a71b259f765, 019f0d6a-8049-7d72-a111-2db0bd4c19ec, 019f0d6e-9b7b-7340-b4d0-959670f70ab6, 019f0d6e-9e0f-7430-ba15-3a73342d1785

After reviewed SHA `a77845bfe041c3fa8d7f9b25b928e76060049ec2`, only review evidence, initiative status, loop state, and PR trust-bundle files may change before PR publication.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Confirmed the key-based artifact merge repair, project service boundary, and chunk scope. Low follow-ups: define stricter artifact/evidence key grammar and make required rule fields literal or explicitly optional before compiler/runtime chunks. |
| qa/test | PASS WITH LOW RISKS | None | Confirmed required artifacts now merge by canonical `key`, API-level tests cover same-key conflict and identical dedupe, and approval/activation revalidation remains covered. |
| security/auth | PASS WITH LOW RISKS | None | No blocking auth, source-ref, hash, permission, or append-only lifecycle issue. Low follow-ups: make sufficiency report creation explicitly draft-only and prevent warning acknowledgement overwrite. |
| product/ops | PASS WITH LOW RISKS | None | Confirmed setup workflow remains project-scoped, pre-submit failure is separate from review decisions, and pending compiler dependency is correctly deferred to Chunk 2. |
| architecture | PASS WITH LOW RISKS | None | Confirmed no per-task checker model drift, no forbidden task/checker/submission runtime edits, and project-scoped `PreSubmitCheckerPolicy` remains the architecture. |
| ci integrity | N/A - with approved reason | N/A | No workflow, package-script, coverage-threshold, dependency, or test-tooling files changed in the reviewed implementation. |
| docs | PASS | None | Confirmed `docs/template_submission_artifact_policy.md` now matches artifact `key/path/description` and evidence `key/label/description` schema fields. |
| reuse/dedup | PASS WITH LOW RISKS | None | Accepted temporary duplicated compiler-stub setup in tests/E2E until Chunk 2 introduces the trusted compiler path. No missed production abstraction blocks this chunk. |
| test delta | PASS | None | Confirmed two new API-level merge-key tests would fail against the old path-based merge, no skips or weakened assertions, and no test deletions. |

## Valid Findings Addressed

- Fixed the QA finding that effective `required_artifacts` merged by `path` instead of canonical artifact `key`.
- Added API-level regression coverage for same-key/different-path default artifact conflicts.
- Added API-level regression coverage for identical same-key default/project artifact dedupe.
- Updated the operator-facing submission artifact policy template so required artifact and evidence tables match the real schema.
- Preserved the current chunk boundary: this PR models and guards project setup; it does not move task runtime or implement the trusted compiler execution.

## Commands Run

```bash
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py -q -k 'default_artifact_key_conflict or dedupes_identical_default_artifact_key or rejects_default_weakening'
cd backend && .venv/bin/python -m ruff check app/modules/projects/service.py tests/test_projects.py
python3 scripts/check_markdown_links.py docs/template_submission_artifact_policy.md
python3 scripts/check_stale_workstream_wording.py
git diff --check
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
docker compose exec -T postgres psql -U workstream -d workstream_test -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week1_api_e2e.py
```

## Results

```text
Focused merge-key tests passed: 3 passed, 155 deselected.
Full ruff passed.
Docstring coverage passed: 100.0% (435/435).
Full backend test suite passed: 249 passed in 1004.33s.
Week 1 real API E2E passed.
Markdown link check passed for 12 changed Markdown files.
Stale wording check passed.
git diff --check passed.
Agent gate result: REVIEW_REQUIRED because this is a large L1 migration/policy chunk touching risk-sensitive files.
```

## Remaining Risks

- Chunk 2 must replace test/E2E direct `PreSubmitCheckerPolicy` compiled-field mutation with the real trusted compiler path.
- Chunk 2 should lock artifact/evidence key grammar before compiler/runtime consumption.
- Chunk 2 should decide whether `required` remains a boolean or becomes `Literal[True]`.
- Chunk 2 or a setup-hardening follow-up should make sufficiency reports draft-only and warning acknowledgement idempotent.
- Chunk 3 must add task locked-context fields and submission runtime migration; this chunk intentionally does not move task runtime.
