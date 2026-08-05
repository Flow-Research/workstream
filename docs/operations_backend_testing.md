# Backend Testing Operations

## Native guide-extractor runtime

The approved v0.1 image extractor supports CPython 3.11 or 3.12 on Linux glibc
x86_64. Its Pillow dependency is installed only from the approved hash-bound
manylinux wheels. Python 3.13, macOS, ARM, and musl environments intentionally
fail the guide-extractor dependency gate rather than resolving an unapproved
native artifact.

Workstream's application tests run against a new local Postgres database per
invocation. Provisioning and cleanup use the admin database; the application
phase receives only a strict `workstream_test_<12 lowercase hex>` database and an ephemeral login without elevated authority.

## Local PostgreSQL diagnostic

This legacy sequential command checks PostgreSQL provisioning and cleanup. It
is not complete full-suite proof because it does not start or bind a MinIO
provider. Use the hosted semantic-lane workflow below for authoritative
PostgreSQL, MinIO, exact-node, timing, API, and coverage custody.

Keep the admin URL in the environment with `postgresql+asyncpg` and a loopback host.
Never put real or shared credentials in arguments, logs, evidence, or configuration.

```bash
cd backend
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
export WORKSTREAM_TEST_ADMIN_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@localhost:5433/postgres'
.venv/bin/python -m pytest -q tests/test_isolated_database_runner.py
.venv/bin/python scripts/run_isolated_tests.py --metadata-json "$tmp_dir/database.json" -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py
unset WORKSTREAM_TEST_ADMIN_DATABASE_URL
```

Run both phases for the legacy sequential local diagnostic. Hosted CI instead
uses five independent matrix jobs, one per semantic lane, with a 20-minute lane
limit and a separate fail-closed fan-in job.

The runner removes the admin URL before child launch, overwrites both child database URLs,
removes the nonlocal override, redacts complete URLs, and writes only credential-free metadata.
It attempts to drop the owned database and ephemeral login after success,
failure, timeout, or interruption. Host termination or a database error can
prevent cleanup; recover manually with the database provisioning credential, targeting only the exact strict database and role names reported by local catalog inspection.

## Candidate coverage floor

`coverage_policy.py --compute-floor` is a read-only preparation command. Point
`--coverage-json` at temporary complete-app coverage JSON; the command validates
the application-file inventory and prints the exact statement percentage
truncated to six places. It does not configure or enforce a floor, write
evidence, connect to Postgres, or act as the CI coverage policy. Keep coverage
JSON temporary and non-secret; 01B2 owns baseline publication and enforcement.

## Focused checks
The API-guard tests are statically DB-free:

```bash
.venv/bin/python -m pytest -q tests/test_api_contract_e2e.py
```

Runner lifecycle tests require the same admin environment variable:

```bash
.venv/bin/python -m pytest -q tests/test_isolated_database_runner.py
```

Run the destructive API drill only against `workstream_test`, `test_workstream`, or a runner-derived local name:

```bash
WORKSTREAM_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@localhost:5433/workstream_test' .venv/bin/python scripts/api_contract_e2e.py
```

Do not use `WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE` for ordinary proof.

If provisioning fails, confirm the local PostgreSQL provisioning credential can create/drop databases and roles, terminate owned sessions, and reach the named admin database. Diagnostics omit credentials.

## Hosted semantic-lane full-suite proof

The required GitHub check remains `Backend / test`. Five matrix jobs each own a
digest-pinned PostgreSQL service container, a digest-pinned MinIO container,
and exactly one dependency lane. A step-level curl health loop admits MinIO
before collection. This is semantic fan-out, not arbitrary test-count sharding:
lane ownership remains repository-defined and exact.

The lanes are balanced by measured dependency ownership: `project_lifecycle`
owns project tests, `task_lifecycle` owns task and checker tests,
`schema_contracts_a` and `schema_contracts_b` deterministically partition exact
node IDs from the measured 12-minute `test_alembic.py` hotspot;
`schema_contracts_a` also owns reset and isolated-runner contracts, and
`shared_foundations` owns the remaining authorization, artifact, API, and
infrastructure tests. Every non-partitioned module belongs to exactly one lane;
every collected test node, including each Alembic node, belongs to exactly one
lane.

Each matrix job binds its checkout to `GITHUB_SHA`, installs and asserts exact
Ruff `0.15.22`, runs lint and docstrings, starts MinIO, and validates the full
canonical inventory before executing its one lane. Each lane receives a distinct
runner-created database and role plus a distinct MinIO bucket/prefix custody
record. `shared_foundations` owns the actual `workstream-artifacts` test bucket
and a unique run prefix; other lanes create, probe, and remove distinct buckets.
The isolated-runner self-tests remain in the canonical manifest as the explicit
`admin_runner_self_test` execution kind. The lane orchestrator runs only those
nodes directly with the admin URL while stripping application database URLs;
every ordinary node remains behind isolated-runner custody and never receives
the admin credential.

Backend does not run on review-state events. The narrow guide-extractor
dependency approval check runs in Agent Gates instead, so submitting or
dismissing the exceptional exact-head dependency approval refreshes a fast gate
without repeating the full backend suite.

Each matrix job uploads a fixed-name artifact bound to GitHub's checked-out PR
merge-tree SHA, containing its manifest, lane evidence, isolation record, and coverage data. The final `test`
job runs with `if: always()`, downloads available diagnostic bundles, then
rejects any failed, cancelled, or skipped matrix result before fan-in. Fan-in
accepts exactly the five declared lane directories,
requires byte-identical manifests and heads, verifies every bound digest, and
rejects symlinks or surplus lanes.

After fan-in, independent validation rejects missing, duplicated, foreign,
deselected, unexpectedly skipped, interrupted, or partially completed nodes.
It also binds the exact head, manifest, per-lane isolation metadata, evidence,
and coverage-file SHA-256 digests. Only then are exactly five regular,
non-symlink coverage files copied byte-for-byte for one literal
`coverage combine`. The 78 percent global floor and every protected 90 percent
subsystem floor remain blocking. The real API contract drill remains a separate
isolated invocation inside the final required job.

### Evidence bundle

Each lane uploads one seven-day bundle, and the final job uploads the reconciled
`.ci/test-lanes` tree. Its summary
records the exact head, canonical node count, five lane results, elapsed time,
and raw-file digests. Per-lane evidence records collected, completed, skipped,
and deselected exact node IDs plus the bound resource-isolation metadata and
coverage digest. Resource metadata is mode `0600`, omits credentials, and proves
database, role, bucket, prefix, probe, and cleanup custody.
Redacted lane logs are uploaded for diagnosis but are not trusted fan-in or
coverage evidence.
If startup or provisioning fails before isolation metadata exists, the failed
lane records null metadata fields, a nonzero exit, and interrupted custody; it
cannot satisfy independent validation or be mistaken for successful proof.

The validator accepts only safe repository-local regular files and exact schema
keys. It rejects symlinks, traversal, stale heads, digest drift, unexpected
lanes, zero collection, incomplete execution, resource cleanup failure, and
coverage tampering before coverage combination.

### Failure diagnosis and reruns

- Collection or collection-validation failure: inspect the canonical manifest,
  lane assignment, and exact checked-out-tree binding. No execution evidence is valid.
- Lane failure: inspect the named private log and evidence result; confirm its
  database/role and MinIO namespace cleanup without exposing credentials.
- Execution-validation failure: inspect node reconciliation, isolation metadata,
  and raw coverage digests before considering the test output.
- API contract or coverage failure: the required job remains failed; lane
  completion cannot compensate for either boundary.

Rerun the complete workflow on the same exact head. Never edit or upload
evidence manually. Review submission or dismissal does not rerun Backend because
it does not change the tested tree. A new PR commit starts a new run and cancels
the superseded same-PR run. Every new commit requires complete evidence because
its head and digests differ. Each lane bundle records its job-start epoch;
missing or malformed timing fails the final evidence step. Hosted evidence
records whole Backend wall time from the earliest lane start, lane
aggregate/slowest execution timing, and whether
the eight-minute target was met. When the repository owner explicitly accepts
a measured target miss at the human merge checkpoint, that performance result
does not override otherwise passing correctness, custody, service-contract,
API, and coverage gates. Never lower coverage, skip nodes, or add a silent
fallback to meet the target.

## Retired changed-scope behavior mutation

The hosted `Behavior Mutation Gate` is temporarily removed. Its callable-wide
selection mutated unchanged executable lines whenever a small declaration or
callable fragment changed, creating blockers that could not be resolved by the
owning behavior assertions without implementation snapshots or gate bypasses.

Backend semantic lanes, the repository-wide 78 percent coverage floor, named
90 percent subsystem floors, lint, docstring coverage, service-contract proof,
internal reviews, CodeRabbit, and human merge approval remain unchanged. The
mutation policy, claim schema, examples, pinned manifest, and prior evidence
remain in the repository as design input for a future changed-line-aware gate.
They are not active contribution requirements. Behavior-mutation enforcement
must not resume until a fresh changed-line-aware plan is approved and proves
that unchanged executable lines cannot block a declaration-only change.
