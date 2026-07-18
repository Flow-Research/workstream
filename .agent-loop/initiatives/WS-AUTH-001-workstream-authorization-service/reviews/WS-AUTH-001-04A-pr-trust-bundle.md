# PR Trust Bundle: WS-AUTH-001-04A

## Chunk

`WS-AUTH-001-04A` - Request And Error Context

## Goal

Give every API response canonical request and correlation identifiers and a
stable privacy-bounded error object without changing product authority or
breaking existing clients.

## Human-Approved Intent

The user explicitly started AUTH-04 after AUTH-03 memory merged through PR
#110. Required L1 review split request/error context from PostgreSQL rate
controls before implementation. This PR contains only the reviewed 04A child;
04B and later authorization chunks remain inactive.

## What Changed

- Added strict canonical request/correlation UUID handling in pure ASGI
  middleware.
- Added stable nested error objects while preserving legacy response fields,
  status codes, and headers.
- Added per-route OpenAPI error and response-header documentation.
- Added privacy-bounded correlation-only failure logs.
- Added real-ASGI behavior, inventory, schema, and API drill coverage.

## Why It Changed

Workstream needs traceable API failures and a dependable error contract before
authority enforcement and rate controls expand, but existing consumers cannot
be forced through a breaking response migration.

## Design Chosen

Pure ASGI middleware reads raw header pairs, stores effective IDs on request
scope state, and edits only `http.response.start` headers. Shared response
builders and exception handlers own JSON shapes. Existing compatibility fields
remain additive beside the canonical nested object.

## Alternatives Rejected

- `BaseHTTPMiddleware`, response buffering, or response-body rewriting.
- Collapsed framework header parsing that cannot detect duplicate fields.
- Replacing existing top-level error fields in one breaking migration.
- Global OpenAPI statuses that routes cannot actually emit.
- Adding PostgreSQL rate controls or provider-adapter migration to this chunk.

## Scope Control

The production change remains below the contract's 500 non-comment line hard
stop. No route, dependency consumer, database model, migration, setting,
permission, role, grant, actor state, rate counter, or product lifecycle changed.

## Product Behavior

Clients receive canonical `X-Request-ID` and `X-Correlation-ID` headers on
success and failure. Errors gain a required nested object with stable code,
message, bounded details, correlation ID, and retryability while retaining
existing compatible fields and headers. Product authorization is unchanged.

## Acceptance Criteria Proof

Real-ASGI tests cover missing, valid, malformed, duplicate, non-ASCII, nil,
uppercase, non-hyphenated, unsupported-version, and comma-joined identifiers;
concurrency; success and every required error class; validation privacy;
streaming; background tasks; duplicate unrelated headers; task compatibility;
OpenAPI schemas; and exact route/dependency inventories.

## Tests And Checks

- 235 focused behavior tests passed.
- Every changed production file exceeds 90 percent statement coverage: 98.08,
  90.82, 90.70, and 92.36 percent respectively.
- The isolated-runner lifecycle suite passed 16/16 and the live API contract
  drill passed.
- Ruff, docstring threshold, stale scans, Markdown links, loop memory, Agent
  Gates, additive test delta, and diff hygiene passed.
- A complete local run found one Alembic logging-state test interaction after
  114 passes; its exact order passes after repair. GitHub Backend must provide
  the complete-suite rerun before merge.

## Test Delta

No assertion, `pytest.raises`, skip/xfail marker, or `skipTest` line was removed
or weakened. New proof exercises actual FastAPI routes through ASGI transport.

## CI Integrity

No workflow, package, dependency, threshold, exclusion, or bypass changed.
GitHub Backend and Agent Gates remain mandatory before merge. The separate
whole-app coverage initiative remains paused at its official 79.249908 percent
baseline; this chunk's changed-file threshold is at least 90 percent.

## Reviewer Results

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test-delta review pass. Production was reviewed
at `cdcaf77`; final reviewed candidate `4fd6db9` received exact-head confirmation
for both additive test repairs with identical production blobs and no weakened
tests.

## External Review

GitHub Backend, Agent Gates, CodeRabbit, and explicit human review begin after
the ready PR is published. None substitutes for the completed internal review.

## Remaining Risks

- Rate controls are intentionally absent and remain owned by inactive 04B.
- Provider-neutral `IdentityIssuerVerifier` adoption depends on the shared
  external-service adapter foundation and a separate reviewed AUTH chunk.
- The canonical nested error is additive; compatibility fields remain until a
  separately reviewed removal is safe.

## Follow-Up Work

After this PR merges and memory is updated, AUTH-04B still requires a separate
explicit user start. AUTH-05 and later cutover chunks remain proposed.

## Human Review Focus

Inspect duplicate-ID rejection, response-start-only header mutation, error and
log privacy, exact legacy compatibility, per-route OpenAPI truth, and unchanged
route/dependency inventories.

## Human Merge Ownership

Only the user may approve and merge this PR. Publication is not merge approval,
and no later AUTH chunk starts automatically.
