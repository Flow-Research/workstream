# Chunk Contract: WS-QUAL-001-01B2 Baseline Evidence And CI Ratchet

Status: inactive until B1B-R7 merges, its post-merge memory update is complete,
and the user gives a separate explicit start signal.

## Goal, Risk, And Budget

Extend the reviewed policy core with Git provenance and publish the configured
initial full-app floor, canonical evidence, read-only CI ratchet, and runbook.

- Risk: L1 CI/evidence integrity; SLA P1
- Implementation cap: 500 lines outside `.agent-loop`
- Allowed: `backend/scripts/coverage_policy.py`,
  `backend/tests/test_coverage_contract.py`, `backend/pyproject.toml`,
  `.github/workflows/backend.yml`, `docs/operations_backend_testing.md`, the
  canonical WS-QUAL baseline evidence, and WS-QUAL/global memory/reviews
- Forbidden: `backend/app/**`, runner/API-drill implementation, migrations,
  schemas, product/auth behavior, unrelated tests, exclusions, pragmas,
  skips/xfail, weakened assertions, or coverage-raising tests

## Acceptance Criteria

- Add local-only one-write initialization and default read-only validation;
  CI cannot create or rewrite evidence.
- Bind runner metadata to checkout HEAD and new evidence to one clean executable
  tree. Accept only enumerated evidence descendants and correctly handle PR
  synthetic merge commits, base advancement/rebase drift, bootstrap merge push,
  and push comparison with exact nonzero prior revision.
- Real temporary-Git tests prove bootstrap, unchanged/updated evidence, evidence-
  only descendants, executable drift, invalid/non-ancestor bases, and push floor,
  covered-count, milestone, and denominator regressions.
- Behavior tests also reject missing branch/base evidence outside the one
  bootstrap state, current measurement below configured floor/milestone, stale
  runner HEAD/Alembic metadata, narrowed `--cov` or pytest selection, removed
  install/full-Ruff/docstring/lifecycle/provisioned/artifact/API steps,
  full-app threshold override, `|| true`, and `continue-on-error`.
- Configure the candidate six-place full-app floor. CI preserves install, full
  `ruff check app tests scripts`, docstring coverage, all 16 lifecycle tests,
  every remaining provisioned test, independent artifact `--fail-under=90`,
  and the real API drill. Policy validation is read-only with no bypass,
  narrowed coverage/test selection, or full-app threshold override.
- Generate canonical credential-free baseline evidence from a second complete
  isolated run on the committed implementation SHA. Admin DSN stays env-only;
  shell traps remove temporary coverage/metadata.
- Update the runbook with bootstrap, validation, ratchet, credential handling,
  temp cleanup, and recovery.

## Allocation And Circuit Breaker

Forecast: provenance/CLI additions 180 lines, real-Git and CI negative tests
210, pyproject/workflow 45, runbook 35, other approved edits 20; hard total 490
with 10 lines reserve. Run the circuit breaker after provenance/CI tests and
before configuration/workflow/runbook publication. Stop and split again above
400 lines at that checkpoint rather than omitting negative proof.

## Verification And Review

Pull-request CI passes `${{ github.event.pull_request.base.sha }}` as the generic
policy `--base-ref`; push CI passes exact `${{ github.event.before }}` and the
policy rejects zero/invalid/non-ancestor values.

```text
(cd backend && .venv/bin/python -m pip check)
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && .venv/bin/python -m pytest -q tests/test_coverage_contract.py)
(cd backend && tmp_dir=$(mktemp -d) && trap 'rm -rf "$tmp_dir"' EXIT && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$tmp_dir/database.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-report=json:"$tmp_dir/coverage.json" --cov-fail-under=0 && .venv/bin/python scripts/coverage_policy.py --coverage-json "$tmp_dir/coverage.json" --database-metadata "$tmp_dir/database.json" --base-ref origin/main --compute-floor)
# Write final configuration and commit every non-evidence file.
(cd backend && tmp_dir=$(mktemp -d) && trap 'rm -rf "$tmp_dir"' EXIT && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$tmp_dir/database.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-report=json:"$tmp_dir/coverage.json" && .venv/bin/python scripts/coverage_policy.py --coverage-json "$tmp_dir/coverage.json" --database-metadata "$tmp_dir/database.json" --base-ref origin/main --initialize --evidence-output ../.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/evidence/coverage-baseline.json --max-implementation-lines=500 --check-test-delta)
# Commit evidence/status/review files only.
(cd backend && tmp_dir=$(mktemp -d) && trap 'rm -rf "$tmp_dir"' EXIT && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$tmp_dir/database.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-report=json:"$tmp_dir/coverage.json" && .venv/bin/python scripts/coverage_policy.py --coverage-json "$tmp_dir/coverage.json" --database-metadata "$tmp_dir/database.json" --base-ref origin/main --evidence ../.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/evidence/coverage-baseline.json --max-implementation-lines=500 --check-test-delta)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Run the internal evidence gate after all required reviewers pass.

Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta. Human focus:
Git/tree provenance, prior-revision push ratchet, exact floor/evidence, CI
non-bypass, credentials, and no coverage-chasing tests.

Stop above 500 lines or on missed floor/provenance/CI proof. Do not start chunk 02.
