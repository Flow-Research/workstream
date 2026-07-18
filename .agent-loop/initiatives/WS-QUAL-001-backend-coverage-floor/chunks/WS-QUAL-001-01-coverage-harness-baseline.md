# Chunk Contract: WS-QUAL-001-01 Coverage Harness And Baseline

Status: superseded by the reviewed `WS-QUAL-001-01A` / `WS-QUAL-001-01B`
split after implementation exceeded 700 lines and exposed separate database
authority and CI-policy boundaries. Do not execute this combined contract.

## Goal

Create reproducible full-backend coverage measurement, isolate the test
database from concurrent worktrees, record the clean main baseline, and enforce
an initial floor that later chunks may only raise.

## Risk and SLA

- Risk: L1 CI/test infrastructure
- SLA: P1

## Allowed files

```text
backend/pyproject.toml
backend/tests/conftest.py
backend/tests/test_coverage_contract.py
backend/tests/test_api_contract_e2e.py
backend/tests/test_isolated_database_runner.py
backend/scripts/coverage_policy.py
backend/scripts/run_isolated_tests.py
backend/scripts/api_contract_e2e.py
backend/scripts/week2_api_e2e.py
.github/workflows/backend.yml
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
backend/app/**
backend/alembic/**
public API or schema changes
coverage omit/include rules that exclude application modules
coverage pragmas
test deletion or weakened assertions
```

## Acceptance criteria

- `pytest-cov` is a development dependency with compatible bounds.
- Coverage source is exactly `app`; the report includes every importable
  application module and fails below the configured floor.
- Coverage report precision is exactly six. The floor is computed with Decimal
  or integer arithmetic as
  `floor((covered_lines * 100 / num_statements) * 10^6) / 10^6`.
- Bootstrap is two-pass: first run isolated measurement with threshold disabled
  and compute the candidate floor without creating evidence; write final config
  and commit every non-evidence file; then rerun the canonical no-CLI-override
  coverage command on that exact implementation tree and initialize evidence
  from the second-pass JSON with `HEAD` as `measured_tree_sha`.
- CI runs the same complete-suite coverage command used locally.
- `WORKSTREAM_TEST_DATABASE_URL` is the authoritative child-process URL. The
  runner accepts the parent-only admin DSN only from
  `WORKSTREAM_TEST_ADMIN_DATABASE_URL`; requires scheme `postgresql+asyncpg`
  and host `localhost`, `127.0.0.1`, or `::1`; provisions only a full-match name
  `^workstream_test_[a-f0-9]{12}$`; and safely quotes validated identifiers while
  parameterizing catalog values.
- Ownership is recorded only after create succeeds. Collision/create failure
  never attaches to, terminates, or drops an existing database. Cleanup targets
  exact owned sessions/database after child success, failure, timeout, or
  interruption.
- After creation, the runner upgrades only its owned database to the repository
  Alembic head, queries `alembic_version`, requires exactly one version matching
  the repository head, records it, and only then launches the requested child.
  Migration failure triggers owned cleanup and never launches the child.
- Child env removes the admin DSN and nonlocal override, overwrites both test and
  runtime URLs with the derived target, propagates the exact child exit status,
  and redacts both credentialed admin/target URLs from errors and output.
- Before cleanup, the runner writes canonical credential-free metadata to its
  caller-provided temporary path. Metadata schema v1 contains exactly
  `schema_version`, strict `database_name`, catalog-observed `alembic_head`, and
  current 40-hex `tree_sha`. It contains no URL. Policy validation requires the
  metadata tree SHA to equal current `HEAD`, binding evidence to the same run.
- `test_coverage_contract.py` and `test_api_contract_e2e.py` are statically
  proven DB-free before their direct focused command; every DB-capable command
  runs through the provisioner.
- New harness tests prove real safety behavior: unsafe/nonlocal databases fail
  closed, owned databases are cleaned up after child success and failure,
  credentials stay redacted, application inventory cannot shrink, coverage
  exclusions and threshold regression are rejected, and existing CI gates
  cannot be removed or bypassed. Execution-only line hits are not accepted.
- API drills accept that strict local derived name; ordinary proof rejects the
  nonlocal write-risk override. Credentials and credentialed URLs never appear
  in output or evidence.
- Coverage JSON is checked against the complete `backend/app/**/*.py` inventory.
  The policy rejects omit/include/exclusion rules, application coverage pragmas,
  narrowed `--cov`, and missing modules.
- Baseline evidence is canonical sorted JSON with a trailing newline at
  `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/evidence/coverage-baseline.json`.
  Schema v1 requires typed keys: `schema_version`, `base_merge_sha`,
  `measured_tree_sha`, `covered_lines`, `num_statements`, `measured_percent`,
  `configured_floor`, `minimum_milestone`, `python_version`, `coverage_version`,
  `pytest_cov_version`, `database_name`, and `alembic_head`. Decimal values are
  six-place strings; SHAs are 40 lowercase hex; no URL or credential is stored.
- Base comparison reads that exact path with `git show <merge-base>:<path>`.
  Initialization is allowed only when the merge base lacks the path. The base
  merge SHA and measured harness-tree SHA are distinct and recorded.
- The policy compares the configured floor and evidence with the merge base and
  fails any decrease; unchanged denominators also require non-decreasing covered
  statements.
- The policy preserves the existing install, full Ruff, docstring, complete
  pytest, and API drill workflow gates and rejects bypass flags or test narrowing.
- `docs/operations_backend_testing.md` documents safe local provisioning and
  cleanup, env-only credentials, URL redaction, exact local/CI commands, ratchet
  updates, API drill use, and troubleshooting without the write-risk override.
- No production file changes.

## Required behavior-proof matrix

- Runner tests assert stable non-secret diagnostics for unsafe scheme/host/name,
  collisions, child env stripping/overwrites, exact exit propagation, and URL
  redaction. Real local catalog proof observes database absence/presence/absence,
  exact-session termination, concurrent unique invocations, and cleanup after
  success, nonzero exit, timeout, and interruption. Catalog proof also verifies
  pre-child migration to exactly one repository head and cleanup on migration
  failure.
- API guard tests preserve `workstream_test` and `test_workstream`; accept the
  strict derived name only on loopback hosts; reject case, suffix, quoting, and
  remote-host lookalikes; and prove ordinary runner execution strips the
  nonlocal override and errors contain no credentialed URL.
- Policy tests assert exit code plus stable diagnostic for every failure:
  missing app inventory, omit/include/exclude/pragma, missing/narrowed
  `--cov=app`, measured below configured/milestone, lower base floor/covered
  count, unexplained denominator change, invalid/reused initialization,
  missing/malformed evidence and removed/narrowed/bypassed coverage-related CI
  gates. The policy imports and invokes `changed_files`, `numstat`, and
  `diff_text` from the existing root `workstream_agent_gate.py` for allowed
  scope, binary/symlink/untracked detection, the implementation budget, deleted
  assertions, skip/xfail, selection narrowing, and coverage pragmas. It does not
  duplicate Git parsing or create another broad agent gate. Parameterized tests
  prove the default 500 cap passes at 500 and fails at 501, this chunk passes at
  700 and fails at 701, and supplying 700 cannot mutate the stored/default cap
  for later chunks. Manual test-delta review remains required for semantic weakening.
- Metadata tests reject missing/malformed/extra keys, unsafe database names,
  absent or mismatched Alembic heads, stale/non-HEAD tree SHAs, and any URL or
  credential material; successful initialization binds the validated metadata
  fields into baseline evidence.
- Each test names the behavior or invariant it protects. Parameterized fixtures
  are preferred; mocks may isolate subprocess/DB mechanics but may not replace
  the real catalog lifecycle proof.

## Contract amendment A1: genuine-proof line budget

Implementation lines are additions plus deletions outside `.agent-loop` against
the merge base. Discovery showed the original 500-line forecast undercounted
readable safety/error handling: the two scripts require 387 lines before tests.
Revised forecast: control scripts 390, genuine behavior tests 190, API/config/
workflow edits 45, runbook 55; total 680. Hard cap: 700. The added budget is
reserved for behavior proof and safety handling, not scope expansion. Stop and
split before exceeding 700. The new policy dynamically loads the existing root gate helpers
from their canonical path and remains limited to coverage config, inventory,
evidence, ratchet, coverage workflow integrity, allowed scope, and size/test
delta controls required by this chunk.

Generated raw coverage JSON lives in a shell-owned OS temporary directory. One
command creates it with `mktemp -d`, installs an EXIT trap, runs measurement and
policy while the file exists, then removes the directory. The policy never
deletes a caller path. Only summarized evidence is committed;
`backend/coverage.json` is never created.

`measured_tree_sha` is the commit containing every final non-`.agent-loop`
implementation/config/test/workflow/runbook change and the configured floor,
before the later evidence-only commit. The canonical second pass runs against
that exact clean commit. Evidence can therefore name the measured tree without
self-reference.

## Contract amendment A2: observed proof size

The first executable implementation reached 923 lines before the complete
ratchet and failure matrix was finished. The A1 estimate omitted the cost of
real concurrent catalog presence/interruption proof, strict evidence/config/
workflow negative cases, and the operator runbook. Compressing back to 700
would remove named behavior assertions or make the safety scripts materially
harder to review, contrary to D5 and the user's explicit behavior-first
direction. The revised forecast is 1,050 lines with a hard cap of 1,100 for
this chunk only. No production file, scope, exclusion, or later-chunk budget is
added. Implementation remains stopped until engineering/architecture/reuse,
QA/CI/test-delta, and security/product/docs reviewers approve this amendment;
rejection requires splitting the chunk before further implementation.

## Historical verification record

The combined contract is superseded and the following commands are
non-executable historical context. Active verification lives in the separate
01A and 01B chunk contracts.

```text
(cd backend && .venv/bin/python -m pip check)
(cd backend && .venv/bin/python -m ruff check tests scripts)
(cd backend && tmp_dir=$(mktemp -d) && trap 'rm -rf "$tmp_dir"' EXIT && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$tmp_dir/database.json" -- .venv/bin/python -m pytest -q --cov=app --cov-report=term-missing --cov-report=json:"$tmp_dir/coverage.json" --cov-fail-under=0 && .venv/bin/python scripts/coverage_policy.py --coverage-json "$tmp_dir/coverage.json" --database-metadata "$tmp_dir/database.json" --compute-floor)
# Commit all final non-evidence files and configured six-decimal floor here.
(cd backend && tmp_dir=$(mktemp -d) && trap 'rm -rf "$tmp_dir"' EXIT && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$tmp_dir/database.json" -- .venv/bin/python -m pytest -q --cov=app --cov-report=term-missing --cov-report=json:"$tmp_dir/coverage.json" && .venv/bin/python scripts/coverage_policy.py --coverage-json "$tmp_dir/coverage.json" --database-metadata "$tmp_dir/database.json" --base-ref origin/main --initialize --minimum-milestone=<six-decimal-baseline> --max-implementation-lines=700 --check-test-delta)
(cd backend && .venv/bin/python -m pytest -q tests/test_coverage_contract.py tests/test_api_contract_e2e.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python -m pytest -q tests/test_isolated_database_runner.py)
(cd backend && .venv/bin/python -m pip check)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Confirm the measurement includes all application code, database isolation is
real, the initial ratchet matches clean evidence, and no gate was weakened.

## Stop condition

Stop if reproducible measurement requires production changes, application
exclusions, suppression pragmas, or shared mutable database state.
After merge, update and merge initiative status/evidence plus global loop state,
queue, and review log; chunk 02 remains inactive until that memory completes and
the user gives a separate start signal.
