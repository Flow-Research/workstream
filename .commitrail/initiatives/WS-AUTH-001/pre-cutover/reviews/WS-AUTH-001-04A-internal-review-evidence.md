# Internal Review Evidence: WS-AUTH-001-04A

## Chunk

`WS-AUTH-001-04A` - Request And Error Context

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: `4fd6db9ebe9911d30ec85657903b71707fc3bbfb`

Reviewed production SHA: `cdcaf77f4a73d091afd54232f378f9a2831376c5`

Reviewed at: 2026-07-13T19:34:02Z

Reviewer run IDs: engineering-architecture=AUTH-04A-4FD6DB9-ENG-ARCH-20260713;
qa-ci-test-delta=AUTH-04A-4FD6DB9-QA-CI-20260713;
security-product-docs-reuse=AUTH-04A-4FD6DB9-SEC-PROD-20260713

The final revision differs from the reviewed production SHA only by additive
real-ASGI test changes: scalar validation context is exercised, and logging
tests establish and restore capture after in-process Alembic configuration
disables an existing logger. Final test-delta review confirmed identical
production blobs and retained the complete prior review results.

## Reviewed Change

- Added pure ASGI request context that validates or generates canonical request
  and correlation UUIDs and overwrites only the two response ID headers.
- Added stable privacy-bounded nested error objects while retaining existing
  top-level compatibility fields, status codes, and response headers.
- Added truthful per-route OpenAPI error and response-header contracts without
  changing the route or dependency-consumer inventories.
- Added bounded correlation-only request failure logging before and after
  response start.
- Added real-ASGI behavior, compatibility, privacy, concurrency, OpenAPI,
  inventory, streaming, background-task, and API-drill proof.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | The bounded ASGI and error helpers are maintainable and preserve compatibility. |
| QA/test | PASS | None | The behavior matrix covers success, failure, privacy, headers, schemas, and inventory through real ASGI paths. |
| security/auth | PASS | None | Invalid identifiers, validation context, unhandled failures, and logs remain privacy bounded and fail closed. |
| product/ops | PASS | None | No role, grant, lifecycle, or product-authority behavior changed. |
| architecture | PASS | None | Pure ASGI middleware changes response-start headers only; rate controls and adapter migration remain separate. |
| CI integrity | PASS | None | No workflow, dependency, threshold, exclusion, or bypass changed. |
| docs | PASS | None | The authorization runbook and durable loop state describe the implemented boundary and inactive follow-up. |
| reuse/dedup | PASS | None | Shared builders centralize error and OpenAPI behavior without duplicating provider or factory boundaries. |
| test delta | PASS | None | No assertion, raises block, skip, xfail, or skipTest line was removed or weakened. |

## Valid Findings Addressed

- Replaced broad global OpenAPI error claims with per-route applicable statuses
  and explicit response ID headers.
- Added bounded pre-response failure logging and proved post-response-start
  failure behavior without reflecting exceptions or identity data.
- Completed real-ASGI proof for malformed headers, every stable error branch,
  concurrent isolation, streaming, background tasks, and compatibility headers.
- Added exact route and protected-consumer inventory digests and additive schema
  assertions for task domain errors.
- Reconciled lifecycle memory and recorded the 350-line scope checkpoint.
- Added the final scalar validation-context branch test; production code did not
  change after the final production review.

## Commands Run

```bash
(cd backend && isolated-runner pytest -q tests/test_api_controls.py tests/test_app.py tests/test_auth.py tests/test_tasks.py)
(cd backend && isolated-runner pytest -q --cov=app tests/test_api_controls.py tests/test_app.py tests/test_auth.py tests/test_tasks.py)
(cd backend && for file in app/core/api_controls.py app/main.py app/api/deps/auth.py app/modules/tasks/router.py; do coverage report --include="$file" --precision=2 --fail-under=90; done)
(cd backend && pytest -q tests/test_isolated_database_runner.py)
(cd backend && isolated-runner pytest -q -x --ignore=tests/test_isolated_database_runner.py)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-db> python scripts/api_contract_e2e.py)
(cd backend && ruff check app tests scripts)
(cd backend && docstr-coverage --config .docstr.yaml)
python3 scripts/check_loop_memory_state.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --unified=0 origin/main...HEAD -- backend/tests | (! rg '^-(.*assert|.*pytest\.raises|.*pytest\.mark\.(skip|xfail)|.*skipTest)')
git diff --check
```

Results:

- focused real-ASGI behavior matrix: 235 passed;
- changed-file statement coverage: API controls 98.08 percent, application
  factory 90.82 percent, auth dependencies 90.70 percent, and task router 92.36
  percent;
- isolated-runner lifecycle suite: 16 passed;
- API contract drill: passed;
- Ruff, docstring threshold, stale wording, authorization docs, artifact
  contracts, Markdown links, loop memory, Agent Gates, additive test-delta, and
  diff hygiene: passed;
- complete isolated backend regression run: exposed one order-dependent logging
  capture failure after 114 passes; the failing Alembic-before-ASGI order and
  both logging branches pass after the test-only repair.

## Evidence Gate

Evidence gate: PASS WITH EXTERNAL COMPLETE-SUITE PROOF PENDING

The reviewed implementation stays inside the approved request/error contract
and below the 500 non-comment production-line hard stop. It adds no migration,
rate counter, grant, role, identity state, product permission, route, dependency
consumer, or later AUTH behavior. GitHub Backend must supply complete-suite
proof before merge; the exact locally failing order now passes.

## Remaining Risks

- GitHub Backend must complete the full regression suite, and Agent Gates must
  repeat repository checks on the published branch before human merge.
- The repository-wide coverage improvement initiative remains paused at its
  last official 79.249908 percent result; this AUTH chunk proves each changed
  production file at or above 90 percent and does not claim a new whole-app
  baseline.
- PostgreSQL rate controls and provider-neutral `IdentityIssuerVerifier`
  adoption remain separate reviewed chunks with unmet prerequisites.

## Stop Condition

After ready PR publication, stop for complete GitHub checks and explicit human
review. Do not merge or start AUTH-04B or AUTH-05 automatically.
