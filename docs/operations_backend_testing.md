# Backend Testing Operations
Workstream's application tests run against a new local Postgres database per
invocation. Provisioning and cleanup use the admin database; the application
phase receives only a strict `workstream_test_<12 lowercase hex>` database and an ephemeral login without elevated authority.

## Local full suite
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

Run both phases. The second can exceed three hours locally; CI gives the child 210 minutes and the job 240 minutes so cleanup retains a bounded window.

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

## Hosted parallel full-suite proof

The required GitHub check remains `Backend / test`. It is the final fan-in for:

1. `preflight`: evidence gate, lint, docstrings, isolated-runner test, exact test
   collection, and deterministic four-shard plan;
2. `shards`: four independent jobs, each with its own digest-pinned PostgreSQL
   service, runner-owned migrated database, real digest-pinned MinIO, and
   coverage file;
3. `api_e2e`: the real API contract proof in a separate isolated database; and
4. `test`: exact artifact validation, coverage combination, the 78 percent
   repository floor, and all protected 90 percent subsystem floors.

Matrix job state is the live progress view. The isolated runner continues to
buffer and redact pytest output, so a running shard does not stream individual
test names. The final check reports shard duration and balance metadata after
all evidence is authenticated.

### Evidence bundles

The preflight plan and four fixed shard bundles are retained for seven days.
Their names include the actual checked-out tree SHA. Each shard bundle contains
only `coverage.data` and allowlisted `result.json`; the result binds the tree,
manifest, shard, modules, collected and completed pytest node IDs, duration, and
SHA-256 of the exact coverage bytes. Repository-owned pytest hooks record the
final selected inventory and lifecycle completions in the same process; fan-in
requires exact equality and matches stable test-base cardinalities to preflight.
Bundles never contain database URLs or passwords, MinIO
credentials, environment dumps, or runner database metadata.

The fan-in accepts exactly four expected regular-file bundles. It rejects stale
tree or manifest bindings, missing/extra/duplicate nodes or modules, altered
coverage, symlinks, path traversal, unexpected files, failed/cancelled/skipped
upstream jobs, and missing artifacts before `coverage combine` runs.

### Failure diagnosis and reruns

- `preflight` failure: inspect evidence/lint/runner/collection output. No shard
  evidence is valid until preflight succeeds.
- one `shards` matrix failure: inspect that shard's database, MinIO, collection,
  or test failure. The final required check must fail even if other shards pass.
- `api_e2e` failure: inspect the independent API contract job; coverage cannot
  compensate for it.
- `test` failure: inspect dependency-result validation, exact bundle fan-in, then
  the named global or subsystem coverage report.

A complete workflow rerun creates evidence for the same checked-out tree and is
the clearest recovery. GitHub may rerun failed jobs, but the fan-in still rejects
missing or stale artifacts; never upload or edit bundles manually. A new commit
always requires a complete new run because its tree SHA differs.

Four shards reduce wall-clock latency by using more concurrent runner minutes.
Review shard durations and total Actions consumption after deployment before
changing the shard count. If parallel execution is unstable or does not justify
its cost, revert the single implementation PR to restore the prior sequential
workflow; do not lower coverage, skip a shard, or add a silent fallback.
