# WS-ART-001-02D External Review Response

## Comments addressed

- GitHub Backend run `29889565612`, shard 3: the exact OpenAPI inventory test
  still expected 62 total and 60 protected routes. The nine intended hidden
  Operator routes make the exact inventories 71 total and 69 protected.
  Commit `536213ff` updates both exact counts and both full sorted-inventory
  SHA-256 hashes. The assertion remains fail-closed.
- GitHub Backend run `29890458009`: preflight, API E2E, and all four shards
  passed. The final unchanged artifact foundation gate reported 89.50 percent,
  0.50 percentage point below its required 90 percent. Commit `f1b9480c` adds
  meaningful focused coverage for every canonical binding resolver branch,
  unknown-type fail-closed behavior, bounded pages, and deterministic project
  deduplication. It changes no production code or threshold.
- GitHub Backend run `29891405683`: all shards passed and the unchanged gate
  improved to 89.70 percent. Commit `45725a85` adds branch-specific tests for
  binding/content/replica/verification-job audit composition, unknown resource
  handling, and missing lineage. The focused union gains 14 statements against
  the remaining roughly 13-statement gap, without production or gate changes.
- GitHub Backend run `29893224494` reached 89.98 percent. Commit `4e53bf64`
  covers the exact missing canonical-resource branch and proves authority/page
  work does not run after concealed not-found.
- Final Backend run `29894507010`: preflight, API E2E, all four shards,
  repository coverage, every cumulative scoped gate, and the artifact
  foundation gate pass. Artifact foundation coverage is exactly 90.00 percent
  (4,370 statements, 437 missed).

## Comments deferred

- CodeRabbit produced no findings because its review was rate-limited. Its
  required status is green, but this is not represented as substantive review
  evidence.

## Human decisions needed

None before the hosted rerun. Explicit human approval remains required to merge
PR #177.

## Commands rerun

- exact OpenAPI inventory generation: 71 total, 69 protected;
- `pytest tests/test_api_controls.py::test_openapi_documents_request_error_and_response_context -q`:
  1 passed;
- `ruff check tests/test_api_controls.py`: PASS;
- `git diff --check`: PASS;
- all nine internal reviewer tracks: PASS on `536213ff`.
- `pytest tests/test_artifact_authorization.py -q`: 26 passed;
- all nine internal reviewer tracks: PASS on `f1b9480c`.
- `pytest tests/test_artifact_authorization.py -q`: 28 passed;
- all nine internal reviewer tracks: PASS on `45725a85`.
- `pytest tests/test_artifact_authorization.py -q`: 30 passed;
- all nine internal reviewer tracks: PASS on `4e53bf64`.

## Remaining risks

Hosted backend and cumulative coverage gates pass. CodeRabbit did not provide a
substantive review due to its external rate limit. Explicit human merge approval
remains required.
