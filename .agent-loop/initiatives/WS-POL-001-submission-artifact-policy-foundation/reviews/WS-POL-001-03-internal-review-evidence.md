# Internal Review Evidence: WS-POL-001-03

## Chunk

WS-POL-001-03

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: a3abfac3bc3a91026856c5e42d8fc873e575d757

Reviewed at: 2026-07-02T18:01:15Z

Reviewer run IDs: 019f23ce-73a7-7292-8f9a-aaa6831243e7, 019f23ce-b2c4-7f93-83ca-baef093608fc, 019f23ce-eae4-7142-9415-32f04ca3b609, 019f23cf-2895-7a72-9b05-f498d27de703, 019f23cf-6422-7710-a22c-cfe2ebfe0de8, 019f23cf-a1e3-7750-a021-3c12c4bd7457, 019f23d3-efa1-7d11-a518-b991430a420f, 019f23d4-2623-75f2-bcdc-faf025e37a82, 019f23d4-6cb0-7861-9440-f5a79d2885df, 019f23db-c704-71f3-b85e-ff49d9c0f81a, 019f23dc-31f1-7451-b77e-b43b762dc9a3, 019f23dc-7941-7313-beaf-023e249390d0, 019f23dc-d948-75c1-a10e-eeed53c5c86c, 019f23f0-18d9-7ec0-ace7-48c81a8b3300, 019f23f0-6480-71c1-92ee-beed81e2be24, 019f23f0-9e3f-7240-8dae-09d4b961b12a, 019f23f0-d661-7eb0-b510-d25f1c9752ff, 019f23f1-2672-7622-be4e-0ea79ac614fa, 019f23f1-741a-7be1-9d00-87b24090d019, 019f23f6-77eb-7390-811c-f32fd24d2e34, 019f23f6-d5b0-7121-afdc-18cfbe81773c, 019f23f7-2a4f-7013-a7dc-a7e47071000c

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed the E2E repair updates the real packet to satisfy locked policy instead of weakening production checkers. |
| qa/test | PASS | None | Confirmed the real API E2E now exercises the current policy contract and passed locally. |
| security/auth | PASS | None | Confirmed locked context, confidentiality, evidence, attestation, and auth boundaries remain intact. |
| product/ops | PASS WITH LOW RISKS | None | Confirmed worker-facing semantics remain correct. Low residual: HTTP drill covers the passing packet; failure separation remains covered in task/checker tests. |
| architecture | PASS WITH LOW RISKS | None | Confirmed project-scoped checker architecture is preserved. Low residual: trust bundle scope/state needed refresh, fixed here. |
| docs | PASS AFTER FIXES | None | Contract wording was clear; stale evidence binding was fixed by updating this artifact to the repaired SHA. |
| reuse/dedup | PASS | None | Confirmed the E2E repair remains minimal and does not duplicate production checker helper logic. |
| test delta | PASS WITH LOW RISKS | None | Low residual: revision-flow coverage remains deferred to `WS-POL-001-05`; E2E repair does not weaken tests. |
| ci integrity | PASS AFTER FIXES | None | Confirmed no CI/test gate weakening; stale evidence and missing CI-integrity contract row were fixed here. |

## Valid Findings Addressed

- Added `docs/spec_chunk_7_checker_runner_registry.md` to the chunk contract as related-doc cleanup after product/ops review found stale pre-submit/post-submit wording.
- Updated `docs/spec_chunk_7_checker_runner_registry.md` so draft malformed or duplicate artifact manifests are described as pre-submit failures that create no submission or durable checker run.
- Updated the checker registry docs to list the current registered checker names, including the Workstream default pre-submit checker names.
- Updated `docs/architecture_data_model.md` so submission provenance is described as implemented for effective project submission artifact policy and project pre-submit checker fields.
- Updated `docs/spec_chunk_5_submission_packet_foundation.md` so historical Chunk 5 scope does not contradict the current lock-triggered post-submit gate.
- Removed stale "architecture target" wording from the Chunk 5 submission packet spec.
- Kept `ProjectGuide.evidence_policy` as an existing v0.1 database field only; it is not treated as a compatibility contract or runtime authority in this chunk.
- Fixed the Week 1 real API E2E script after CI proved it still submitted an old packet shape. The script now supplies `required_evidence_key = "checker_log"` metadata and exact platform/project attestation terms so the real HTTP drill satisfies the locked project `PreSubmitCheckerPolicy`.
- Added `backend/scripts/week1_api_e2e.py` to the chunk contract only for CI drill alignment.
- Added `CI integrity` to the chunk contract reviewer list because the repair touches CI-executed E2E behavior.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests -q
cd backend && .venv/bin/python -m ruff check scripts/week1_api_e2e.py
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week1_api_e2e.py
```

## Results

```text
Ruff app/tests/scripts passed.
Docstring coverage passed: 100.0% (527/527).
Markdown link check passed for 8 changed Markdown files.
Stale wording check passed.
git diff --check passed.
Agent gate result: REVIEW_REQUIRED because this is a large L1 migration/runtime/checker diff touching risk-sensitive files.
Full Postgres-backed backend suite passed before docs-only repair commits: 306 passed in 1680.44s.
Full Postgres-backed backend suite passed in CI on PR #63: 306 passed in 193.72s.
Week 1 real API E2E initially failed in CI because the script submitted an old packet shape missing current required evidence/attestation terms.
Week 1 real API E2E passed locally after repair.
No production backend code changed after the full backend suite.
```

## Remaining Risks

- `WS-POL-001-05` should add public lifecycle coverage for the revision path instead of test setup directly placing a task in `needs_revision`.
- A future migration-focused regression can assert the exact `0007 -> 0006` downgrade removal of locked-context columns and constraints.
- Before more checker-policy expansion, shared path/pattern validation helpers should be extracted from the overlapping setup-policy and runtime checker logic.
