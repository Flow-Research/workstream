# WS-ART-001-02D External Review Response

## Comments addressed

- GitHub Backend run `29889565612`, shard 3: the exact OpenAPI inventory test
  still expected 62 total and 60 protected routes. The nine intended hidden
  Operator routes make the exact inventories 71 total and 69 protected.
  Commit `536213ff` updates both exact counts and both full sorted-inventory
  SHA-256 hashes. The assertion remains fail-closed.

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

## Remaining risks

The full hosted backend rerun and cumulative coverage gates remain required.
CodeRabbit did not provide a substantive review due to its external rate limit.
