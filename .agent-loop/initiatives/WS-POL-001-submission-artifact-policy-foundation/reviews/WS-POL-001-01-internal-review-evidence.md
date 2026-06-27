# Internal Review Evidence: WS-POL-001-01

## Chunk

WS-POL-001-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: de41f8701eb2ce98b2e355d984c60d9c0a0e7a34

Reviewed at: 2026-06-27T13:31:03Z

Reviewer run IDs: 019f0928-7056-7b92-a6fc-272f594bf922, 019f0928-7609-7061-b7b6-af73aaa22711, 019f0928-7cc8-7c03-a03e-79ec1d709ac5, 019f0928-87b0-7442-9c1a-3c06a93822d2, 019f0928-90fa-7832-9fb5-03734f02e43e, 019f0928-9cde-7981-af5f-a423001ad637, 019f0930-a518-7461-815b-d8ebcef426dd, 019f0930-ab10-7830-858e-596e920114bb, 019f0930-b2ca-7050-8cbc-dec2341ee1e8, 019f0930-ba53-7a81-a039-b7eeef749e14, 019f0935-546d-7ac2-aaac-a8c0030bcf7b, 019f0935-58a6-7833-a50c-1b2e8875e9ee

After reviewed SHA `de41f8701eb2ce98b2e355d984c60d9c0a0e7a34`, only review evidence, initiative status, loop state, and PR trust-bundle files changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Confirmed implementation scope, activation repair, project-layer boundaries, and no per-task checker generation. Low risks: active-guide reads should reuse stronger validation before task locked-context consumption; duplicate source snapshot conflicts may need graceful mapping later. |
| QA/test | PASS AFTER FIXES | None | Initial High finding on restrictive packaging merge and Medium finding on compiled bundle hash validation were fixed. Confirmed packaging merge, pending compiler rejection, mismatched bundle hash rejection, encoded unsafe refs, and real API coverage. |
| security/auth | PASS AFTER FIXES | None | Initial Medium findings on percent-encoded unsafe refs, approval role provenance, and compiled bundle hash trust were fixed. Confirmed decoded sanitizer checks, approval role enforcement, DB constraints, and canonical compiled bundle hash recomputation. |
| product/ops | PASS AFTER FIXES | None | Initial High finding that activation accepted `pending_compilation` was fixed. Confirmed activation now rejects pending or corrupt pre-submit checker context and does not expand task runtime migration in this chunk. |
| architecture | PASS WITH LOW RISKS | None | Confirmed production changes stay project-scoped, task/checker/submission runtime modules are untouched, and direct compiler-field writes are limited to test/E2E setup until Chunk 2. |
| ci integrity | PASS AFTER FIXES | None | Confirmed no workflow/package/test gate weakening, no skip/xfail bypass, strengthened verification contract, and expected `REVIEW_REQUIRED` agent-gate result for the L1 migration/policy diff. Evidence was the only pending lifecycle gate and is provided here. |
| docs | PASS AFTER FIXES | None | Initial docs findings on CHUNK_MAP allowed files, migration reference, activation-boundary wording, and verification-command coverage were fixed. This evidence file resolves the final docs/evidence-gate finding. |
| reuse/dedup | PASS WITH LOW RISKS | None | Confirmed duplicated compiled-checker fixture helpers are acceptable until Chunk 2 introduces the real compiler path. Existing checker manifest hash helper is not the right abstraction for policy JSON. |
| test delta | PASS WITH LOW RISKS | None | Confirmed tests were strengthened, no tests skipped or weakened, and legacy `evidence_policy` authority was replaced with approved submission artifact policy plus a positive legacy-field non-requirement test. |

## Valid Findings Addressed

- Blocked guide activation unless project `PreSubmitCheckerPolicy` is `compiled`
  and has compiler-owned `compiled_bundle` and `compiled_bundle_hash` fields.
- Added service validation that `compiled_bundle_hash` is `sha256:<64 lowercase
  hex>` and equals the canonical JSON hash of `compiled_bundle`.
- Added DB constraints for compiled pre-submit rows and approved submission
  artifact policy provenance.
- Required approved submission artifact policy rows to carry
  `approved_by_role` in `admin | project_manager`, approved actor, and timestamp
  before activation.
- Decoded durable source refs before secret/local/traversal checks so encoded
  token, credential, password, local path, backslash, and traversal refs cannot
  persist into `GuideSourceSnapshotItem` or policy provenance.
- Implemented restrictive packaging merge semantics instead of storing nested
  default/project packaging inputs as the effective policy.
- Synced the active chunk map, plan, spec, and chunk contract so they all state
  that Chunk 1 enforces the compiled-checker activation dependency while Chunk
  2 implements the trusted compiler path that writes those fields.
- Updated the chunk verification contract to include `ruff check app tests
  scripts`, full backend tests, Week 1 real API E2E, docstring coverage,
  Markdown links, stale wording, internal evidence, agent gate, and diff check.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts/week1_api_e2e.py
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py -q -k 'compiled_rows_require_bundle_fields or draft_policy_cannot_be_approved_after_guide_activation'
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py -q -k 'source_snapshot_rejects_credential_and_local_refs or approval_merges_packaging_rules or mismatched_pre_submit_checker_bundle_hash or compiled_rows_require_bundle_fields or approval_requires_provenance'
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py -q
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week1_api_e2e.py
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check origin/main..HEAD
```

## Results

```text
ruff passed.
Focused repaired project tests passed: 2 passed, 62 deselected.
Focused sanitizer/packaging/hash/provenance tests passed: 27 passed, 47 deselected.
Project test suite passed: 74 passed.
Backend test suite passed: 165 passed.
Week 1 real API E2E passed.
Docstring coverage passed: 100.0%.
Markdown link check passed for 4 changed Markdown files.
Stale wording check passed.
git diff --check passed.
Agent gate result: REVIEW_REQUIRED because this is a large L1 migration/policy chunk touching risk-sensitive files.
```

## Remaining Risks

- Chunk 2 must replace test/E2E direct `PreSubmitCheckerPolicy` compiled-field
  mutation with the real trusted compiler path.
- Chunk 3 must add task locked-context fields and submission runtime migration;
  this chunk intentionally does not move task runtime.
- Before task locked-context consumes active-guide output, `GET active-guide`
  should reuse the same strong validation used by activation or otherwise fail
  closed on drifted compiled bundle state.
- Duplicate source-snapshot bundle conflicts may need an idempotent or mapped
  conflict response in a later polish pass.
