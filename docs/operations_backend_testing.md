# Backend Testing Operations

## Guide document runtime

Guide uploads preserve original files in ArtifactStore. Bounded PDF/OOXML
format admission runs locally; the agent reads documents in its isolated
provider workspace. There is no local guide extractor or Pillow/PDF
parser dependency. Use the [Developer Quickstart](../README.md#developer-quickstart)
for the supported backend environment. Scripted runtime tests prove contracts;
real-provider document reading requires the explicit live probe and credentials
from the ignored backend `.env`.

Workstream's application tests run against a new local Postgres database per
invocation. Provisioning and cleanup use the admin database; the application
phase receives only a strict `workstream_test_<12 lowercase hex>` database and an ephemeral login without elevated authority.

## Local PostgreSQL diagnostic

Use PostgreSQL 16, matching Backend CI, for reset-schema fingerprint checks.
Catalog identity rendering can differ across major versions even when the
schema is equivalent. A changed fingerprint requires comparing the actual
schema objects on the CI engine; never bypass the check or accept an additional
hash merely to make a different local engine pass.

This focused sequential command checks PostgreSQL provisioning and cleanup. It
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

Run both phases for this sequential local diagnostic. Hosted CI instead
uses nine independent matrix jobs, one per semantic lane, with a 20-minute lane
limit and a separate fail-closed fan-in job.

The runner removes the admin URL before child launch, overwrites both child database URLs,
removes the nonlocal override, redacts complete URLs, and writes only credential-free metadata.
It attempts to drop the owned database and ephemeral login after success,
failure, timeout, or interruption. Host termination or a database error can
prevent cleanup; recover manually with the database provisioning credential, targeting only the exact strict database and role names reported by local catalog inspection.

## Diagnostic coverage, not a quality quota

All coverage collection uses `backend/pyproject.toml` with
`concurrency = ["thread", "greenlet"]`. SQLAlchemy async operations switch
greenlets within a thread; default thread-only tracing can assign executed
lines to the wrong source file. Do not override that setting in local or
hosted coverage commands. The coverage-contract suite checks actual line
attribution across SQLAlchemy async switches using the repository configuration.
This setting changes measurement, not test selection or exclusions.

Backend and MCP coverage percentages do not gate merges. Backend combines the
nine lane artifacts once for diagnostics, without subsystem/per-file quotas or
focused reruns to raise a number. Artifact integrity and complete test execution
remain blocking. The old floor-computation CLI and unused quota-policy helpers
are removed; their module retains the shared lexical test-safety owner.

Before adding a test, identify the behavior and failure it detects and inspect
existing proof. Before deleting one, name its surviving behavior owner or explain
why its requirement is retired. Preserve authorization, data isolation, lineage,
rollback, concurrency, retry and real storage/database proof. Real API drills
complement these tests; they do not replace controlled failure-path tests.

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

The public task portion of this drill ends at project-authorized claim/start.
It checks that revoked grants deny work and explicitly issues fresh authority
before continuing. The self-activated eligibility endpoint and JSON-packet
submission POST are removed. A passing drill does not certify hidden
admission-backed Submission creation, finalization or post-submit routing.
Those owners require their own bounded integration evidence.

Checker, finalization and review persistence tests may use the explicit stored
Submission fixture in `backend/tests/submission_fixtures.py`. It seeds retained
packet prerequisites and runs the existing finalization/enqueue owners; it is
not a public API or ART-admission success simulation. Tests of new Submission
creation must use the real admission-backed command, not this fixture.

If provisioning fails, confirm the local PostgreSQL provisioning credential can create/drop databases and roles, terminate owned sessions, and reach the named admin database. Diagnostics omit credentials.

## Hosted semantic-lane full-suite proof

The required GitHub check remains `Backend / test`. Eight matrix jobs each own a
digest-pinned PostgreSQL service container, a pinned-source MinIO image,
and exactly one dependency lane. A step-level curl health loop admits MinIO
before collection. This is semantic fan-out, not arbitrary test-count sharding:
lane ownership remains repository-defined and exact.

The explicit inventory lives in `backend/scripts/test_lane_catalogue.py`.
Authorization preflight runs alongside the nine lanes. The final `test` job
requires both preflight and every lane to succeed before validating evidence and
coverage; failed, cancelled or skipped prerequisites remain blocking. This saves
serial waiting on valid changes at the cost of lane work when preflight fails.
Assertion-map validation analyzes each exact historical revision/module once per
invocation, then checks every referenced node and assertion against that analysis.
It does not cache current source or reuse analysis across validation calls.

The seven ordinary lanes use private, 2 GiB RAM-backed PostgreSQL data directories
to reduce ephemeral reset I/O. A runtime guard verifies the mount, capacity,
data directory and enabled `fsync`, `full_page_writes` and `synchronous_commit`
before tests. Real SQL, transaction, lock, isolation, and full hosted behavior
checks remain.
The schema-contract lane and aggregate job retain disk-backed databases.
This is not a production configuration or proof of host-power-loss durability:
[Docker tmpfs data disappears when the container stops](https://docs.docker.com/engine/storage/tmpfs/).
An exhausted mount fails the job; it does not silently change storage or skip tests.

The `project_lifecycle_a`, `project_lifecycle_b`, and `project_lifecycle_c` lanes
partition PROJECT nodes; `task_lifecycle_a`, `task_lifecycle_b`, and `task_lifecycle_c` use the same
deterministic partition mechanism for TASK and checker nodes. The single `schema_contracts` lane owns all baseline/PostgreSQL schema, reset and
isolated-runner contracts. The
`shared_foundations_a` and `shared_foundations_b` lanes deterministically
partition exact node IDs from the remaining authorization, artifact, API, and
infrastructure modules. Every collected test node, including each Alembic and
shared-foundation node, belongs to exactly one lane.

Each matrix job binds its checkout to `GITHUB_SHA`, installs and asserts exact
Ruff `0.15.22`, runs lint and docstrings, and starts MinIO. The runner discovers,
validates and collects the full canonical inventory before executing its one
lane; the aggregate independently recollects and validates complete execution.
There is no duplicate standalone inventory pass in each matrix job.
Each lane receives a distinct
runner-created database and role plus a distinct MinIO prefix custody record.
Both shared-foundation jobs run in separate MinIO containers, use the actual
`workstream-artifacts` test bucket, and receive distinct run prefixes; other
lanes create, probe, and remove distinct buckets.
The isolated-runner self-tests remain in the canonical manifest as the explicit
`admin_runner_self_test` execution kind. The lane orchestrator runs only those
nodes directly with the admin URL while stripping application database URLs;
every ordinary node remains behind isolated-runner custody and never receives
the admin credential.

Backend and Agent Gates do not run on review-state events. Agent Gates runs
the repository process and documentation checks for each PR head; protected-branch
review rules independently enforce exact-head human approval.
Superseded Agent Gates runs for the same PR are cancelled without repeating the
full backend suite.

Each matrix job uploads an artifact named for GitHub's checked-out PR merge-tree
SHA, lane and numeric run attempt, containing its manifest, lane evidence,
isolation record, and coverage data. The final `test`
job runs with `if: always()`, downloads available diagnostic bundles, then
rejects any failed, cancelled, or skipped matrix result before fan-in. Fan-in
selects the highest numeric attempt available for each of the nine declared
lanes from separately downloaded artifact directories. It rejects malformed,
foreign or future attempt names and never falls back from an incomplete or
corrupt latest bundle to an older passing one. For the selected bundles it
requires byte-identical manifests and heads, verifies every bound digest, and
rejects symlinks or surplus lanes.

After fan-in, independent validation rejects missing, duplicated, foreign,
deselected, unexpectedly skipped, interrupted, or partially completed nodes.
It also binds the exact head, manifest, per-lane isolation metadata, evidence,
and coverage-file SHA-256 digests. Only then are exactly nine regular,
non-symlink coverage files copied byte-for-byte for one literal
`coverage combine`. Percentages are diagnostic, with no global or subsystem
floor. The real API contract drill remains a separate
isolated invocation inside the final required job.

### Evidence bundle

Each executed lane uploads one seven-day bundle per attempt, and the final job
uploads the reconciled `.ci/test-lanes` tree and downloaded diagnostics under its
own attempt-specific artifact name. Older diagnostic artifacts are preserved.
Its summary
records the exact head, canonical node count, nine lane results, elapsed time,
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
- API contract or evidence-integrity failure: the required job remains failed;
  lane completion cannot compensate. A lower coverage percentage is not a failure.

On the same exact head, rerun failed lanes (and their dependent final job), or
rerun only the final job when the lane evidence already passed. Successful lanes
not rerun retain their previous attempt's evidence; a rerun lane's newest bundle
must independently pass all existing checks. A failed, cancelled or skipped
required job still blocks fan-in. Never edit or upload evidence manually.
Review submission or dismissal does not rerun Backend because
it does not change the tested tree. A new PR commit starts a new run and cancels
the superseded same-PR run. Every new commit requires complete evidence because
its head and digests differ. Each lane bundle records its job-start epoch;
missing or malformed timing fails the final evidence step. Hosted evidence
records whole Backend wall time from the earliest selected lane start, lane
aggregate/slowest execution timing, and whether
the eight-minute target was met. Timing uses the same bundle selection as
evidence. On a retry this wall time includes the wait between selected attempts;
it is not fresh-run execution latency. When the repository owner explicitly accepts
a measured target miss at the human merge checkpoint, that performance result
does not override otherwise passing correctness, custody, service-contract,
API, and complete-execution gates. Coverage is diagnostic only. Never skip
nodes or add a silent fallback to meet the target.

## Retired changed-scope behavior mutation

The hosted `Behavior Mutation Gate` is temporarily removed. Its callable-wide
selection mutated unchanged executable lines whenever a small declaration or
callable fragment changed, creating blockers that could not be resolved by the
owning behavior assertions without implementation snapshots or gate bypasses.

Backend semantic lanes, lint, docstring checks, service-contract proof,
internal reviews, CodeRabbit, and human merge approval remain required.
Test-coverage percentages are diagnostic only; the percentage floors and four
duplicate coverage-only reruns are retired. The
mutation policy, claim schema, examples, pinned manifest, and prior evidence
remain in the repository as design input for a future changed-line-aware gate.
They are not active contribution requirements. Behavior-mutation enforcement
must not resume until a fresh changed-line-aware plan is approved and proves
that unchanged executable lines cannot block a declaration-only change.

### Behavior ownership catalogue foundation

The replacement foundation is a read-only engineering QA catalogue under
`.ci/behavior-ownership/`. Its canonical `partition.v1.json` assigns every
eligible non-`__init__` module to exactly one population group and binds the
protected-base commit plus a digest over the assignment authority. Validation
rejects missing, relocated, duplicated, modified, branch-local, or incomplete
partitions.

Run its commands from `backend/`:

```bash
.venv/bin/python -m scripts.behavior_ownership inventory
.venv/bin/python -m scripts.behavior_ownership generate --group auth
.venv/bin/python -m scripts.behavior_ownership validate
```

The generator is deterministic and emits only `candidate` records. Candidates
never satisfy reviewed ownership or activate a gate. Reviewed executable
records bind exact AST callables, pytest nodes, outcomes, boundaries, and
reviewers. `structural_only` records require a reviewed reason, cannot contain
callable or test fields, and fail validation when the target contains an
executable callable or module-level runtime behavior such as calls, branches,
loops, raises, awaits, mutation, I/O, SQL, validators, or other side effects.
Until population and a separately approved changed-line reactivation chunk are
complete, Backend lanes and real API integration checks remain the hosted
test authority; no percentage quota substitutes for meaningful behavior proof.

### Local coverage-context evidence

Coverage contexts can suggest which exact tests execute a callable, but they do
not prove assertions or establish reviewed ownership. Generate one temporary,
non-catalogue artifact from a clean committed tree:

```bash
cd backend
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
.venv/bin/python -m scripts.behavior_ownership context-evidence \
  --target backend/scripts/behavior_ownership.py \
  --test-module tests/test_behavior_ownership.py \
  --output "$tmp_dir/context-evidence.json"
.venv/bin/python -m scripts.behavior_ownership validate-context-evidence \
  --input "$tmp_dir/context-evidence.json"
```

The command reuses semantic-lane pytest collection and completion custody,
rejects dirty trees, skipped/deselected/partial execution, stale heads,
overwrite attempts, digest drift, runs over two minutes, and artifacts over 10
MiB. The private output contains only exact Git/test/callable/line metadata and
its digest. It contains no environment values, credentials, payloads, logs, or
database values; keep it outside `.ci/behavior-ownership/` and do not commit it.
The catalogue validator never consumes this artifact, and no workflow or
required check invokes the command.

Only pytest `|run` coverage contexts count as callable-execution evidence.
Fixture setup and teardown coverage is intentionally excluded because it does
not prove that the test body exercised the callable.

## Module-boundary validation

Run the modular-monolith boundary gate from the repository root:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/module_boundaries.py validate --protected-base origin/main
```

It checks the canonical 12-module registry, exact protected non-AUTH private
edges, public API leaks, unknown modules, cyclic public dependencies,
dynamic-import hiding, and agreement with the WS-AUTH-003 ledger. The edge
inventory is temporary recovery evidence; do not add an edge to make a feature
pass. Remove the dependency through the owning module's typed public API.
The sole non-ledgered owner-private composition exception is the exact
`backend/app/adapters/<owner>/__init__.py` file importing that same owner's
private implementation to construct typed public ports. Nested adapter files
and cross-owner private imports remain scanned and must be repaired or remain
exact protected-base debt.
