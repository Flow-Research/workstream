# PR Trust Bundle: WS-AUTH-001-04B

## Chunk

`WS-AUTH-001-04B` - PostgreSQL Rate Controls

## Goal

Provide privacy-keyed, cross-replica PostgreSQL rate controls for future first
access and authority mutations without attaching them to production routes.

## Human-Approved Intent

The user explicitly started AUTH-04B after AUTH-04A and its post-merge memory
merged. The approved boundary is a cross-replica PostgreSQL rate-control
foundation only: dependencies remain unattached, product authority remains in
later AUTH chunks, and only the user may approve PR merge.

## What Changed

- Added atomic database-time fixed-window counters with durable denial,
  saturation safety, and bounded lock-safe pruning.
- Added HMAC-keyed server dependencies for `first_access` and
  `admin_mutation`; both remain unattached.
- Added migration `0017_api_controls` with guarded downgrade custody.
- Added non-retaining secret configuration across constructor, environment,
  layered dotenv, and Pydantic's public model-validation methods.
- Clarified that artifact production I/O requires central AUTH permissions,
  service principals, and exact resource authorization before adapter work.

## Design

Each consume owns a short independent committed session. One PostgreSQL upsert
uses one `statement_timestamp()` CTE to insert, reset, increment, saturate, and
return authoritative window state. HMAC framing stores only scope and a 32-byte
digest. The server key is private `SecretStr` state assigned only after
successful Pydantic validation; Pydantic receives no recoverable key object.

## Scope Control

The production delta is 480 non-comment lines, below the 500-line hard stop.
No route consumer, actor/grant behavior, product authority, artifact runtime,
AUTH-05 implementation, Redis counter, or in-memory cross-replica state was
added.

## Behavior Proof

Tests cover exact limits, repeated denial, expiry, database-clock retry values,
concurrency, cross-session durability, downstream rollback, saturation,
pruning, unavailable database phases, cancellation, privacy-safe persistence,
schema constraints, migration races, and representative artifact preservation.
Secret tests traverse structured error objects and complete exception graphs
and instrument the BaseSettings boundary directly.

## Acceptance Criteria Proof

- PostgreSQL owns one clock-bound atomic upsert, durable denial, saturation,
  and bounded lock-safe pruning.
- Persistence contains only exact scope and a 32-byte HMAC digest.
- Constructor, environment, layered dotenv, and all public validation methods
  retain no raw or recoverable secret in structured errors or exception graphs.
- Migration proof covers populated `0016` preservation, exact schema guards,
  refusal on nonempty downgrade, writer races, empty downgrade, and re-upgrade.
- Route/dependency inventory proves neither new dependency is attached.
- Artifact adapter I/O remains inactive behind central AUTH-07/AUTH-09 gates.

## Evidence Commands And Results

- 77 focused isolated PostgreSQL tests passed at 97 percent changed-subsystem
  statement coverage.
- 59 final configuration/object-graph tests passed.
- Exact AUTH-04B migration and real API E2E passed.
- The exact CI failure order now passes 22/22 after the migration test restores
  Alembic head following destructive cleanup.
- Ruff, docstring threshold, stale scans, links, loop memory, 36 Agent Gates,
  additive test delta, and diff hygiene passed.
- GitHub Backend must provide the unchanged repository-wide 78 percent floor;
  the interrupted local global run is not evidence.

## Reviewer Results

| Reviewer | Result | Blocking findings |
|---|---:|---|
| Senior engineering / architecture / docs / reuse | PASS | None |
| QA / test delta / CI integrity | PASS | None |
| Security / privacy / product ops | PASS | None |

Reviewed implementation SHA is `922778b`; reviewed production SHA is
`67484b5`. Later reviewed heads contain only tests, evidence, and lifecycle
memory unless explicitly recorded in the external-review response.

## CI And Gate Integrity

- [x] No workflow, threshold, exclusion, skip, or coverage bypass changed.
- [x] Changed AUTH-04B subsystem remains above 90 percent coverage.
- [x] Repository docstring gate passes at 95.8 percent.
- [x] Internal evidence, loop memory, stale scans, links, and Agent Gates pass.
- [ ] Backend must pass the repaired exact PR head at the 78 percent global floor.
- [ ] Explicit human review and merge approval remain pending.

## External Review

Ready PR #113 is open. Agent Gates passed on the prior published head.
CodeRabbit completed its available review with one valid test-deduplication
nit addressed; its later incremental review was rate-limited. The first Backend
run reached 82.12 percent coverage but exposed test-owned schema cleanup. All
final-head external checks and explicit human review remain pending. None
replaces the completed internal review.

## Remaining Risks

- The dependencies are intentionally unattached; later owning chunks must add
  route-specific permissions and consumer tests.
- Secret rotation resets effective counters and requires the documented
  cross-replica quiescence procedure.
- The global suite and 78 percent repository floor remain GitHub-owned because
  the local run was interrupted by host shutdown.

## Human Review Focus

Inspect transaction custody, HMAC framing/privacy, database-time math, pruning
lock order, migration downgrade refusal, secret object-graph non-retention, and
the fact that no production route consumes either dependency.

## Human Merge Ownership

Only the user may approve and merge this PR. Publication is not merge approval,
and AUTH-05 does not start automatically.
