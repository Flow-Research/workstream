# Backend CI Caches And Measured Lane Balance

- Initiative: `None`
- Durable disposition: `Complete`
- Intended merge outcome: Backend CI reuses an exact content-addressed MinIO
  source image and pip download cache, moves measured workloads into existing
  lane capacity, and retains every test and the fail-closed aggregate.

## Intent

Reduce repeated setup work and repair measured task-lane overload in the required
Backend workflow. Exact cache inputs, retained duration diagnostics and explicit
workload placement preserve complete test and evidence coverage.

## Current behavior

`.github/workflows/backend.yml` builds the source-pinned MinIO image once per
commit because its cache key includes `github.sha`. Backend jobs create fresh
Python environments and repeatedly download the same dependency inputs. The
semantic runner retains each lane log but reports only the 25 slowest pytest
phases, limiting later balancing evidence.

GitHub Backend run `37784941972` on PR #507 is the measurement source for this
slice. Its first MinIO job spent 145 seconds building after a cache miss. Lane
jobs also repeatedly spent about 25--28 seconds installing backend dependencies,
and queued for materially different periods. These measurements describe that
run only; this record makes no hosted performance claim before a candidate run.

## Bounded change

### Allowed

- `.github/workflows/backend.yml`: make the MinIO tar cache key depend on the
  runner OS/architecture, exact `docker/minio/**` content and workflow recipe,
  retaining exact per-run artifact identity, checksums and live provider
  verification.
- `.github/workflows/backend.yml`: restore a pip download cache for the exact
  backend dependency/workflow inputs and save it only after trusted-main
  validation; every job still performs a fresh install into its fresh hosted
  Python environment.
- `backend/scripts/run_test_lanes.py`: retain all pytest duration diagnostics in
  the existing redacted per-lane diagnostic logs without changing selection or
  timeout or treating those logs as fan-in evidence.
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: rebalance measured checker-delivery
  and routing-preparation workloads into the existing three-way project partition;
  preserve every test node, deterministic assignment and all nine lanes.
- `scripts/test_lightweight_agent_gates.py` and
  `backend/tests/test_ci_test_lanes.py`: focused positive and adversarial
  regressions for cache identity, fresh installs, runtime verification, artifact
  identity, and lane duration options.
- `docs/operations_backend_testing.md`: extend the canonical failure/rerun owner
  with the exact failed-job command, repeated-timeout diagnosis, fresh-current-
  tree rule and explicit limits on what the cache optimization can improve.
- `docker/minio/README.md`: describe trusted-main cache publication, exact
  content/workflow/platform reuse and the separate per-run artifact binding.
- `CONTRIBUTING.md`: link contributors to that canonical Backend rerun guidance
  without copying its operational contract.
- This standalone Commitrail record.

### Not allowed

- No product source, migrations, dependencies, lane
  count, test selection, skips, coverage behavior, timeout, retry, runner
  permission, concurrency, service image or branch-protection change.
- No installed virtual-environment cache, broad restore prefix, commit-SHA MinIO
  cache key, unverified image reuse, affected-only tests or hidden failures.
- No lane-count/DAG redesign or performance claim before hosted measurement.

### Timeout repair plan

Backend run `37799550116` tested merge `9ea0fc9a2f9b0f9927ae98f06f9ea0a487daa050`.
TASK B and C exhausted 1200 seconds with 22 and 30 nodes unfinished. Their
databases and MinIO resources were cleaned up; the aggregate correctly failed.
PROJECT A completed in 529 seconds, PROJECT B in 959 and PROJECT C in 758;
TASK A completed in 969. This demonstrates available capacity in the existing
jobs, not that a same-head retry would solve the imbalance.

Move checker execution, post-submit materialization/selection, evaluation
capacity and output-custody/storage proof together to PROJECT A, beside the
existing initial-dispatch and evaluation-delivery owners. Move routing AUTH
PREP proof from TASK C to PROJECT C. Keep the original per-node hash mechanism,
UUID seed, node IDs, isolation, 1200-second limits and exact aggregate custody.
That initial allocation used catalogue/inventory regressions and a
dropped/duplicated-owner mutant. The next measurement below supersedes its
exclusive placement; recorded forecasts are not hosted success.


The next hosted measurement, Backend run `37809916459` at merge
`dbc84f10e1ca1926412856a5f34e4bc91ab49c5d`, disproved the exclusive
PROJECT A placement: it exhausted 1200 seconds after 665 of 745 nodes, with
80 unfinished, zero skips and confirmed PostgreSQL/MinIO cleanup. PROJECT B
finished in 769.294 seconds and PROJECT C in 483.442 seconds. Assigning the
entire delivery group to one runner was the incorrect assumption.

Repair that allocation by partitioning all delivery and routing-preparation
nodes across the same three PROJECT lanes using the existing exact-node hash.
No new jobs, runtime controls, retries, skips, evidence formats or product changes
are allowed. Update the existing ownership regressions to reject an exclusive
placement and retain inventory, exact node identity and fan-in checks. Compare
all 8,803 nodes from that hosted manifest before and after this repair; only these
15 modules may change assignment. Focused tests, a regression mutant restoring
exclusive placement, and independent CI-integrity/security/QA/test-delta review
are required before pushing. Hosted speed remains unproven until fresh CI.

## Design and decisions

The reusable MinIO tar has an exact recipe/platform cache identity: a version,
runner OS and architecture, and a hash of `docker/minio/**` plus the workflow
that owns the build command. Rare workflow-only edits intentionally invalidate
the cache. A cold rebuild is not guaranteed byte-identical because the Docker
recipe consumes live apt repositories. Pull requests can restore only; a cache
miss is saved only after a trusted `main` push verifies the built image. The
cache has no restore prefix. Every workflow attempt still publishes a
SHA-and-attempt-named artifact after loading the tar, checking the image version,
starting it, probing health, and producing a checksum that every consumer verifies.

Pinned cache restore/save actions manage a pip download directory keyed by
Python/platform and the hashes of `backend/pyproject.toml` plus this workflow,
which includes the separate exact Ruff pin. Pull requests restore only; the
validated preflight on a trusted `main` push may save a miss. No installed
environment is cached. Existing `pip install` commands remain mandatory in
preflight, every lane and aggregation.

The lane runner changes `--durations=25` to `--durations=0`; pytest retains all
nontrivial setup/call/teardown timings in the existing diagnostic log. A lane
terminated by the unchanged deadline may not emit the final duration summary,
so completion evidence and interruption metadata remain the authority.

The operator guidance treats rerun as evidence recovery, never a green-result
loop. Removing the observed 145-second rebuild when its exact context is
unchanged does not solve 17-minute queue waits or 20-minute lanes and does not
promise an eight-minute Backend completion time.

## Acceptance criteria

- [x] Unchanged MinIO Docker context and Backend build workflow on the same
  runner OS/architecture use one exact cache key across commits; any context,
  workflow or platform change misses it.
- [x] MinIO cache restore has no broad prefix and cannot bypass image load,
  version execution, live health probe, per-run artifact name or checksum.
- [x] Pull requests never save MinIO or pip caches; only a verified trusted-main
  miss can populate a key that later pull requests restore.
- [x] Backend jobs cache pip downloads only and still run the existing fresh
  package installation commands from exact dependency inputs.
- [x] Ordinary and schema-admin lane commands request complete duration
  diagnostics while retaining the same exact node list, coverage, isolation,
  timeout, log and evidence contracts.
- [x] The nine lanes, full inventory, fan-in failure propagation, CLI dependency,
  aggregate validation, permissions and timeouts are unchanged; only the named
  checker-delivery and routing-preparation workloads change lane ownership;
  all use the existing three-way PROJECT partition.
- [x] Contributor guidance permits only failed-job reruns for a diagnosed
  same-head transient, explains aggregate revalidation of successful lane
  evidence, and requires diagnosis or fresh current-tree CI in the other cases.
- [x] Focused workflow/runner tests and mutation probes fail when cache identity,
  verification, fresh installation, duration output or required gates weaken.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `ci_integrity`, `security`, `qa`, `test_delta`
- Human review focus: Cross-commit cache trust and invalidation, fresh-install
  preservation, exact artifact/runtime verification, unchanged gate propagation,
  and whether duration output remains diagnostic rather than authoritative.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Measured bottlenecks | Inspect PR #507 Backend run `37784941972` job/step timestamps from `/tmp/ws-ci-507-jobs.json` | MinIO build took 145 seconds; repeated lane installs took about 25--28 seconds | Hosted queue and runner variability are uncontrolled |
| Cache custody | `python -m unittest -v scripts.test_lightweight_agent_gates`; checksum-verified actionlint 1.7.7; cache-key, invalid-context and per-job-install relocation mutants | 19 workflow gates passed; candidate linted cleanly; all three cache/install mutants were rejected | A real cross-commit hit requires a trusted-main seed and later hosted run |
| Lane diagnostics | Focused lane/evidence pytest batch plus duration-option mutant | 123 tests passed; reverting both commands to `--durations=25` failed the exact lane-command regression | A timed-out pytest process cannot print its final duration table |
| Full gate preservation | Workflow inventory/fan-in tests, exact diff inspection, Commitrail and Markdown gates | Existing lane count, selection, timeouts, permissions, fan-in and fresh installs remain; repository gates passed | Root owns hosted aggregate validation |
| Timeout diagnosis and allocation | Retained summaries and complete TASK A duration phases from Backend run `37799550116` | TASK B/C interrupted at 1200 seconds; delivery-group transfer forecasts about 152/161 seconds of relief and about 1036 seconds for PROJECT A | Forecast extrapolates TASK A module costs; fresh hosted execution is required |
| Rebalance integrity | Catalogue/runner/evidence/merge focused pytest batch; dropped and duplicated delivery-owner mutations | 124 tests passed; recursive inventory rejected both mutations; all node IDs and existing hash/UUID-seed mechanisms remain | This proves assignment and evidence contracts, not hosted speed |

| Exclusive-placement diagnosis | Actual run `37809916459` PROJECT A/B/C summaries and cleanup records | A interrupted at 1200.966s with 665/745 completed; B/C passed at 769.294/483.442s; A cleanup complete | A interruption prevents a final duration table; previous cost forecast was insufficient |
| Three-way allocation integrity | Replay the retained 8,803-node hosted manifest through the repaired catalogue; recursive inventory validator | Same IDs and execution kinds, exactly once; 127 assignments changed only within the 15 named modules; delivery A/B/C 41/32/39 and routing PREP 28/28/16 | This is a historical inventory replay, not a claim that current-head full CI completed |
| Repair behavior and gates | Focused catalogue/runner/evidence/merge pytest batch; workflow unittest suite; Ruff | 124 passed in 46.13s and 19 workflow tests passed; lint/format clean | Fresh hosted runtime measurement remains required |
| Exclusive-placement regression | Temporarily restore the predecessor catalogue and run the updated exact partition regression, then restore the repair | Predecessor fails because delivery has no three-way partition; restored candidate passes in 0.65s | Existing inventory and fan-in regressions retain loss/duplication/failure checks |

## Review findings

Initial workflow review found that `runner.temp` is not an allowed workflow-level
`env` context. Each existing identity step now exports `PIP_CACHE_DIR` through
`GITHUB_ENV` before installation; actionlint and an invalid-context mutant prove
that regression is rejected. Cache trust review also changed both caches to
restore-only on pull requests and save-on-miss only after trusted-main
verification.

Documentation review also corrected the `gh` command description: `--failed`
is the selective form, while the bare command is the whole-workflow rerun; there
is no `--all` option. The MinIO owner documentation now distinguishes the
trusted cross-commit cache from each SHA-and-attempt-bound artifact.
QA review found that a repository-wide install count could miss moving the
aggregate install into preflight. The regression now inspects preflight, lane
and aggregate blocks independently and requires exactly one cache restore,
environment export and fresh install in order; the relocation mutant fails it.

## Reconciliation

- Current-source reconciliation: Reconciled with `main` at
  `36e8a615f01801cecd6ccf83d7411235ab1cfa8f`; no product or migration owner is
  affected.
- Next usable boundary: Validate the measured allocation in fresh hosted CI and
  measure cross-commit cache reuse before further allocation or DAG changes.
- Remaining risks: GitHub-hosted cache availability and queue time vary outside
  repository control; no improvement is claimed until measured.
