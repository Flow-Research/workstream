# Plan: WS-QUAL-001 Backend Coverage Floor

## Approach

1. Establish the isolated least-privilege test-database provisioner.
2. Establish reproducible `pytest-cov` measurement, full `app` inventory proof,
   machine-readable evidence, and a base-ref-enforced non-decreasing ratchet.
3. Cover project setup/policy/correction service behavior and reach at least 82%.
4. Cover project repository/router behavior and reach at least 84%.
5. Cover task service/repository/router behavior and reach at least 86%.
6. Cover checker service/runner/repository/router/worker behavior and reach at
   least 88%.
7. Close the enumerated adapter/core/worker gaps and set the permanent CI floor
   to exactly 90 percent or higher.

Each coverage-raising implementation chunk changes tests and coverage
configuration only. Chunk 01A is the explicit exception for its isolated
database runner, API drill guards, CI wiring, and operations runbook. Any
production defect exposed by a test stops the active chunk and is repaired in a
separately scoped change rather than hidden inside coverage work.

## Threshold policy

- Coverage JSON supplies exact `covered_lines` and `num_statements`. The first
  clean main measurement becomes the initial enforced floor, truncated to six
  decimal places only so the exact suite passes.
- Every later chunk raises or preserves the floor; no chunk may lower it.
- A committed evidence summary records tree SHA, Python/coverage/pytest-cov
  versions, covered statements, total statements, computed percent, configured
  floor, database name, and Alembic head. It never records a credentialed URL.
- A policy checker compares the branch configuration and evidence with the
  merge-base version. The configured percentage cannot decrease. When the
  application denominator is unchanged, covered statements cannot decrease;
  denominator changes require explicit evidence and CI-integrity review.
- The final chunk is incomplete unless `fail_under = 90` and CI passes at 90 or
  above while measuring every module under `backend/app`.
- `omit`, `include`, `source`, and coverage pragmas may not exclude application
  debt to satisfy the target.

## Mechanical integrity policy

A permanent policy check parses `pyproject.toml`, the backend workflow, and
coverage JSON. It inventories every `backend/app/**/*.py`, rejects coverage
`omit`, `include`, `exclude_lines`, or `exclude_also` rules, rejects application
coverage pragmas, rejects a narrowed `--cov` target, verifies the canonical
full-suite command, and verifies the threshold against the base ref.
It also asserts measured coverage is at least the configured six-decimal floor
and the chunk milestone. The workflow proof preserves install, full Ruff,
docstring coverage, complete pytest, and API drill steps; it rejects removed
steps, narrowed test selection, `continue-on-error`, and `|| true`. Coverage
chunks may only replace the existing pytest invocation with the canonical
coverage command and raise its threshold.

Missing base coverage evidence is accepted only when initializing
`WS-QUAL-001-01` against a base that has no WS-QUAL coverage policy. After that
initialization, missing or malformed base/branch evidence is fatal.

## Test quality policy

New tests must assert externally meaningful results: returned values, persisted
state, emitted audit records, queued work, mapped HTTP errors, or fail-closed
behavior. Pure branch execution without an outcome assertion is insufficient.
Coverage percentage is a safety signal, not a reason to add a test. Every added
test must identify the real behavior or safety invariant it protects and assert
an observable outcome. Tests whose only value is executing previously uncovered
lines are rejected even when they increase the measured percentage.
Each chunk records added/modified/deleted/skipped tests and scans its diff for
`skip`, `xfail`, deleted assertions, selection changes, and coverage pragmas.
Tests reuse existing domain fixtures in their owning test file; copied database
reset, actor/project/task factories, HTTP clients, and queue helpers are banned.

The default 500-line budget is additions plus deletions from the merge base across
implementation/config/test/workflow/runbook files. `.agent-loop` planning,
evidence, status, and trust-bundle lines are reported separately and excluded
from that implementation-size numerator. The policy checker emits both counts
and fails above the reviewed per-chunk cap supplied by the contract. Later
chunks use the default 500 cap.

The combined chunk 01 was split after all L1 reviewer groups rejected a proposed
1,100-line cap. Chunk 01A retains the reviewed 700-line limit for the database
lifecycle boundary. Chunk 01B consumes its CLI contract and keeps coverage/CI/
evidence review independent. Later chunks retain the default 500-line cap.

The blocked 01B1 candidate is further split by responsibility. `01B1A` owns
read-only coverage arithmetic and config/evidence/metadata parsers. `01B1B`
then owns repository-delta scope, executable weakening detection, and deleted-
assertion proof. `01B2` remains the later configuration, evidence publication,
and CI enforcement boundary. Each replacement chunk has its own review, PR,
merge-memory, and start checkpoint.

## Alternatives rejected

- Setting 90 immediately without tests: correctly makes every PR red and gives
  no reviewable repair path.
- Diff-only coverage: useful as a supplement but does not satisfy the requested
  repository-wide 90 percent floor.
- Excluding large services or generated-looking schemas: hides product risk and
  makes the percentage misleading.
- One giant coverage PR: crosses project, task, checker, CI, and auth boundaries
  and fails the repository circuit-breaker.

## Isolated database contract

`WORKSTREAM_TEST_DATABASE_URL` is authoritative for tests. A shared runner
accepts a parent-only admin DSN through `WORKSTREAM_TEST_ADMIN_DATABASE_URL` and
requires exact scheme `postgresql+asyncpg` plus host `localhost`, `127.0.0.1`, or
`::1`. It derives a name matching `^workstream_test_[a-f0-9]{12}$` from the
canonical worktree path plus a nonce. The name must full-match before safely
quoted identifier use; catalog values are parameterized.

Ownership begins only after `CREATE DATABASE` succeeds. Collision or create
failure never attaches to, terminates, or drops an existing database. After
catalog ownership validation, cleanup terminates sessions for the exact owned
`datname` and the runner-created unique ephemeral role, including a role session
on the admin database that would otherwise block `DROP ROLE`. It drops only the
owned database and role after child success, nonzero exit, timeout, or
interruption; unrelated database and role sessions survive.

The child environment removes `WORKSTREAM_TEST_ADMIN_DATABASE_URL` and
`WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE`, overwrites both test/runtime database
URLs with the derived target, and exposes no admin credential. Parent output and
errors redact both credentialed admin and target URLs. CI's service database is
already isolated per job. API drill guards accept the strict derived name; the
runner makes the nonlocal override unavailable to ordinary coverage proof.

## Verification

Every chunk runs focused tests, Ruff, `pip check`, stale-wording and Markdown
checks, policy/inventory proof, test-delta scan, and an isolated full-suite
coverage command. The final chunk also runs the real API contract drill and
proves CI uses the same 90 percent command.
