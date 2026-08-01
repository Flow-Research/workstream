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
uses four concurrent semantic lanes with a 20-minute lane limit inside a
45-minute job, leaving a bounded validation and cleanup window.

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

The required GitHub check remains `Backend / test`. One job owns one
digest-pinned PostgreSQL service container, one digest-pinned MinIO container
started in-step and published on `127.0.0.1:9000`, and four concurrent
dependency lanes. A step-level curl health loop admits MinIO before collection.
This avoids arbitrary shard fan-out and artifact fan-in while retaining exact
node and coverage custody.

The lanes are balanced by measured dependency ownership: `project_lifecycle`
owns project tests, `task_lifecycle` owns task and checker tests,
`schema_contracts` owns migrations and reset contracts, and
`shared_foundations` owns the remaining authorization, artifact, API, and
infrastructure tests. Every discovered module must belong to exactly one lane.

The job binds the checkout to `GITHUB_SHA`, installs and asserts exact Ruff
`0.15.22`, runs lint and docstrings, starts MinIO, then collects every canonical
pytest node. The independent evidence validator must
accept the collection before execution begins. Each lane receives a distinct
runner-created database and role plus a distinct MinIO bucket/prefix custody
record. `shared_foundations` owns the actual `workstream-artifacts` test bucket
and a unique run prefix; other lanes create, probe, and remove distinct buckets.
The isolated-runner self-tests remain in the canonical manifest as the explicit
`admin_runner_self_test` execution kind. The lane orchestrator runs only those
nodes directly with the admin URL while stripping application database URLs;
every ordinary node remains behind isolated-runner custody and never receives
the admin credential.

After execution, independent validation rejects missing, duplicated, foreign,
deselected, unexpectedly skipped, interrupted, or partially completed nodes.
It also binds the exact head, manifest, per-lane isolation metadata, evidence,
and coverage-file SHA-256 digests. Only then are exactly four regular,
non-symlink coverage files copied byte-for-byte for one literal
`coverage combine`. The 78 percent global floor and every protected 90 percent
subsystem floor remain blocking. The real API contract drill remains a separate
isolated invocation inside the same required job.

### Evidence bundle

The workflow uploads the `.ci/test-lanes` tree even on failure. Its summary
records the exact head, canonical node count, four lane results, elapsed time,
and raw-file digests. Per-lane evidence records collected, completed, skipped,
and deselected exact node IDs plus the bound resource-isolation metadata and
coverage digest. Resource metadata is mode `0600`, omits credentials, and proves
database, role, bucket, prefix, probe, and cleanup custody.
If startup or provisioning fails before isolation metadata exists, the failed
lane records null metadata fields, a nonzero exit, and interrupted custody; it
cannot satisfy independent validation or be mistaken for successful proof.

The validator accepts only safe repository-local regular files and exact schema
keys. It rejects symlinks, traversal, stale heads, digest drift, unexpected
lanes, zero collection, incomplete execution, resource cleanup failure, and
coverage tampering before coverage combination.

### Failure diagnosis and reruns

- Collection or collection-validation failure: inspect the canonical manifest,
  lane assignment, and exact-head binding. No execution evidence is valid.
- Lane failure: inspect the named private log and evidence result; confirm its
  database/role and MinIO namespace cleanup without exposing credentials.
- Execution-validation failure: inspect node reconciliation, isolation metadata,
  and raw coverage digests before considering the test output.
- API contract or coverage failure: the required job remains failed; lane
  completion cannot compensate for either boundary.

Rerun the complete job on the same exact head. Never edit or upload evidence
manually. Every new commit requires a complete new run because its head and
digests differ. Hosted evidence always records the exact wall time and whether
the eight-minute target was met. When the repository owner explicitly accepts
a measured target miss at the human merge checkpoint, that performance result
does not override otherwise passing correctness, custody, service-contract,
API, and coverage gates. Never lower coverage, skip nodes, or add a silent
fallback to meet the target.
