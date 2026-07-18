# Chunk Contract: WS-QUAL-001-01B Coverage Policy And Baseline

Status: implementation stopped by the 500-line circuit breaker. Superseded only
if the proposed 01B1/01B2 split receives internal and explicit human approval.

## Goal

Turn the isolated complete-backend coverage measurement into a reproducible,
non-decreasing CI policy with machine-readable baseline evidence. This chunk
establishes the ratchet; it does not add tests merely to raise coverage.

## Risk And Scope

- Risk: L1 CI/test policy and evidence integrity
- SLA: P1
- Implementation cap: 500 changed lines outside `.agent-loop`
- Allowed:
  - `backend/pyproject.toml`
  - `backend/scripts/coverage_policy.py`
  - `backend/tests/test_coverage_contract.py`
  - `.github/workflows/backend.yml`
  - `docs/operations_backend_testing.md`
  - `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/evidence/coverage-baseline.json`
  - WS-QUAL/global loop memory and review evidence
- Forbidden:
  - `backend/app/**`, migrations, schemas, public APIs, auth, product behavior,
    runner/API-drill implementation, unrelated tests, coverage exclusions or
    pragmas, skipped/xfail tests, weakened assertions, or threshold reduction

## Acceptance Criteria

- `pytest-cov==7.1.0` remains an explicit development dependency. Full-app
  provisioned coverage measures statements for exactly `app`, with report
  precision six and one configured `fail_under` equal to the initialized
  six-place baseline floor. The separate artifact coverage report retains its
  independent `--fail-under=90` gate.
- Coverage policy inventories every `backend/app/**/*.py` file and requires a
  corresponding file entry in coverage JSON. It rejects missing files, a
  narrowed `--cov`, `omit`, `include`, `source`, `exclude_lines`,
  `exclude_also`, and application coverage pragmas.
- The configured floor, current measured percentage, and evidence percentages
  use `Decimal` or integer arithmetic. The initialized floor is the current
  covered-statements percentage truncated, never rounded up, to six places.
- Baseline evidence is canonical sorted JSON with a trailing newline at the
  allowed evidence path. Schema v1 contains exactly `schema_version`,
  `base_merge_sha`, `measured_tree_sha`, `covered_lines`, `num_statements`,
  `measured_percent`, `configured_floor`, `minimum_milestone`,
  `python_version`, `coverage_version`, `pytest_cov_version`, `database_name`,
  and `alembic_head`. Decimal strings have six places; SHAs are full lowercase
  hex; no URL, password, credential, or role secret is stored.
- The CLI has three mutually exclusive modes. `--compute-floor` is read-only
  and prints the truncated six-place candidate. `--initialize
  --evidence-output <canonical-path>` is local-only, refuses `CI`, requires the
  merge base to lack evidence, and writes evidence once. Default mode is
  read-only validation through `--evidence <canonical-path>`; CI uses only this
  mode and never creates or rewrites evidence. Success exits zero; every policy
  violation exits two with `coverage-policy: <stable_code>` on stderr.
- Initialization requires runner metadata `tree_sha` to equal the clean local
  checkout `HEAD`, exactly one current Alembic head, and a strict derived
  database name. It writes `measured_tree_sha=HEAD` and
  `base_merge_sha=merge-base` before any evidence/status/review commit follows.
- Validation supports three explicit evidence states:
  - Bootstrap PR: base evidence is absent, branch evidence is present, its
    `base_merge_sha` equals the merge base, its measured tree is an ancestor of
    checkout `HEAD`, and every changed path after that tree is an enumerated
    evidence/status/review path.
  - Updated later evidence: base evidence is present and branch evidence
    differs; the same merge-base and evidence-only descendant rules apply.
  - Unchanged historical evidence: branch evidence equals base evidence, so the
    current measurement is validated without pretending the historical measured
    tree is the current tree.
- In every state, runner metadata binds to the actual checkout `HEAD`, including
  a GitHub synthetic merge commit. A synthetic merge is accepted only when its
  tree differs from `measured_tree_sha` through enumerated evidence/status/review
  paths. Base advancement, rebase drift, or any executable change after the
  measured tree fails and requires remeasurement on a new implementation commit.
- Pull-request validation compares with the fetched base branch. Push-main
  validation compares with the exact nonzero `github.event.before` commit, never
  `HEAD` itself. The initial baseline merge push may use bootstrap evidence when
  that prior commit lacks evidence and `base_merge_sha` equals it. A missing,
  zero, non-commit, or non-ancestor push base fails closed. Real Git tests prove
  push-main rejects a reduced configured floor, reduced covered count, and
  denominator drift even when branch evidence is edited consistently.
- Enumerated post-measurement paths are the canonical baseline evidence,
  WS-QUAL review files, initiative `STATUS.md`/`CHUNK_MAP.md`, and global
  `LOOP_STATE.md`/`WORK_QUEUE.md`/`REVIEW_LOG.md`. No other path may differ in
  bootstrap or updated-evidence validation.
- Base comparison prevents a lower configured floor or measured covered count
  when the application denominator is unchanged. Denominator changes fail
  closed and require explicit CI-integrity review in a separately amended
  contract rather than an implicit bypass.
- For 01B initialization, `minimum_milestone` is derived from and must equal the
  configured six-place baseline floor. Validation requires measured coverage
  and configured floor to meet it, and prevents the milestone from decreasing
  against base evidence. Later coverage chunks supply their contract milestone
  explicitly when updating evidence.
- The policy imports `changed_files`, `numstat`, and `diff_text` from the root
  `scripts/workstream_agent_gate.py`; it does not duplicate Git-diff parsing.
  It filters `.agent-loop/**` from the 500-line implementation numerator and
  enforces test-delta integrity. Python AST/config parsing identifies executable
  skip/xfail usage; application source scanning identifies coverage pragmas;
  parsed workflow steps identify selection narrowing and CI bypasses; filtered
  diff text identifies deleted assertions. Inert fixture strings in policy tests
  must not trigger, and the policy-test file receives no blanket exemption.
- CI preserves install, full Ruff, docstring, all 16 runner lifecycle tests,
  all remaining provisioned tests, artifact 90 percent coverage, and the real
  API drill. The provisioned phase writes coverage JSON and runner metadata to
  a shell-owned temporary directory, then runs read-only validation with no
  `|| true`, `continue-on-error`, test narrowing, or full-app threshold
  override. The artifact subsystem's independent threshold remains required.
- Policy tests assert stable diagnostics and exit codes for valid initialization
  and validation plus malformed/missing evidence, inventory loss, exclusion
  config/pragmas, narrowed coverage command, below-floor measurement, base
  regression, denominator drift, stale metadata/tree SHA, unsafe database name,
  missing Alembic head, scope overflow, test weakening, CI bypasses, inert
  negative-fixture strings, evidence-only descendants, synthetic PR checkout,
  base advancement/rebase drift, executable post-measurement change, bootstrap
  merge push, invalid/zero push base, and push-main floor/count/denominator
  regression against the before SHA. Provenance cases use temporary real Git
  repositories rather than mocks of Git output.
- No test is added solely to execute uncovered application lines. This chunk's
  tests protect the coverage and CI policy boundary itself.
- The runbook documents two-pass bootstrap, canonical validation, evidence
  updates, ratchet behavior, and failure recovery. The admin DSN is supplied
  only through the environment/CI secret facility, never CLI arguments, files,
  logs, or committed evidence. Only strict ephemeral database name and Alembic
  metadata may persist; shell traps remove temporary coverage/runner files.

## Bootstrap And Verification

1. Implement the policy's read-only parsing and `--compute-floor` mode without
   changing the configured floor or writing evidence.
2. Run a threshold-disabled isolated candidate measurement into an OS temporary
   directory and compute the candidate floor.
3. Write final configuration, remaining policy validation, tests, workflow, and
   runbook; commit every non-evidence file.
4. On that exact clean commit, run the canonical isolated complete suite with
   the configured floor. Run local-only `--initialize` from the same coverage
   JSON and runner metadata, writing the canonical evidence path.
5. Commit only evidence/status/review files after the reviewed implementation
   SHA. Re-run default read-only validation and the internal evidence gate.

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

## Review And Stop

Required tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta.

Human review focus: full-app inventory, exact floor arithmetic, initialization
provenance, non-decreasing base comparison, CI non-bypass, and no line-chasing
tests or production changes.

Stop on scope expansion, production changes, exclusions, shared database state,
unreviewed denominator drift, a missed floor, more than 500 implementation
lines, or any need to weaken CI/tests. Do not start chunk 02.
