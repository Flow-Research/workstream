# Internal Review Evidence: WS-AUTH-001-04B

## Chunk

`WS-AUTH-001-04B` - PostgreSQL Rate Controls

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: `4fb846c76029dc0bebb11ef90982207f162b54c9`

Reviewed production SHA: `67484b508637b7fc893e441e7afb5f5b34dd7715`

Reviewed at: 2026-07-14T04:39:18Z

Reviewer run IDs: engineering-architecture-docs-reuse=AUTH-04B-4FB846C-ENG-20260714;
qa-ci-test-delta=AUTH-04B-4FB846C-QA-20260714;
security-privacy-product=AUTH-04B-4FB846C-SEC-20260714

The final SHA differs from the reviewed production SHA only by additive tests
and review memory. Exact-head review confirmed identical production blobs and
that the boundary test fails the prior recoverable-`SecretStr` behavior.

## Reviewed Change

- Added PostgreSQL-owned fixed-window counters with database-clock boundaries,
  atomic saturating upsert, bounded lock-safe pruning, and durable denial.
- Added privacy-keyed HMAC-SHA256 derivation and unattached first-access and
  administrative-mutation dependencies with canonical 429/503 behavior.
- Added guarded migration `0017_api_controls` and exact preservation/downgrade
  custody proof.
- Kept the rate key outside Pydantic's structured input/error graphs across
  constructor, environment, layered dotenv, and all public model validators.
- Bound future artifact adapter I/O to central AUTH-07 permissions, AUTH-09
  service principals, and exact operation/resource authorization evidence.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Database ownership, configuration privacy, and the 480-line bounded implementation are maintainable. |
| QA/test | PASS | None | Behavior, concurrency, migration, failure, and secret object-graph tests are genuine and mutation-sensitive. |
| security/auth | PASS | None | No raw or recoverable rate key remains in persistence, structured errors, or exception graphs. |
| product/ops | PASS | None | Dependencies remain unattached; artifact authority stays central and later chunks remain inactive. |
| architecture | PASS | None | Reuses shared sessions/errors and introduces no parallel authorization or storage authority path. |
| CI integrity | PASS | None | No workflow, threshold, exclusion, dependency, or bypass was weakened. |
| docs | PASS | None | AUTH operations and inactive ART contracts match the implemented boundaries. |
| reuse/dedup | PASS | None | One repository/service/dependency path owns rate controls. |
| test delta | PASS | None | Additive tests; no assertion, raises, skip, xfail, or skipTest weakening. |

## Valid Findings Addressed

- Made session-open, prune, execute, commit, rollback, cancellation, and
  missing-database behavior explicit and privacy bounded.
- Proved concurrent increments, downstream rollback independence, database
  time, same-clock `updated_at`, saturation, and deadlock-safe pruning.
- Locked downgrade before checking emptiness and preserved representative
  `0016` artifact rows.
- Removed the secret from Pydantic's public field graph and closed constructor,
  environment, layered-dotenv, mapping, JSON, string-mapping, malformed JSON,
  non-ASCII, and exception-chain retention paths.
- Added deterministic BaseSettings boundary instrumentation proving that only
  `None`, never a raw value or `SecretStr`, enters Pydantic validation.
- Reconciled ART planning so credentials and receipts never create authority.

## Verification Results

- focused isolated PostgreSQL rate/config matrix: 77 passed;
- changed subsystem statement coverage: 97 percent aggregate; dependency 96,
  config 97, model 100, repository 100, and service 99 percent;
- final direct configuration/object-graph suite: 59 passed;
- exact AUTH-04B migration test: 1 passed, 8 deselected;
- Backend CI repair order (AUTH-04B migration test followed by rate suite):
  22 passed; the migration test restores Alembic head after cleanup;
- earlier migration-inclusive repaired matrix: 78 passed;
- real API contract E2E: passed;
- Ruff, docstring threshold, stale wording, authorization docs, artifact
  contracts, Markdown links, loop memory, 36 Agent Gates, additive test delta,
  and diff hygiene: passed.

The repository-wide local coverage run was interrupted by the host shutdown and
is not claimed. GitHub Backend retains the unchanged 78 percent global floor;
the materially changed subsystem exceeds the required 90 percent threshold.
The first PR Backend run reached 82.12 percent but failed on test-owned schema
cleanup; the bounded test isolation repair requires a final Backend rerun.

## Evidence Gate

Evidence gate: PASS WITH GITHUB GLOBAL SUITE PENDING

The reviewed implementation is 480 changed non-comment production lines,
below the 500-line hard stop. It adds no protected-route consumer, actor role,
grant, product permission, artifact runtime, or AUTH-05 behavior.

## Stop Condition

Publish a ready PR, then stop for GitHub Backend, Agent Gates, CodeRabbit, and
explicit human review. Do not merge or start AUTH-05 automatically.
