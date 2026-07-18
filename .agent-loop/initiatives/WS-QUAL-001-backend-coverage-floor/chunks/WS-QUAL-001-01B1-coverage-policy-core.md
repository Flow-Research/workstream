# Chunk Contract: WS-QUAL-001-01B1 Coverage Policy Core

Status: blocked on 2026-07-12 at 496/500 lines after two failed
semantic-integrity repair cycles. A smaller reviewed split and explicit user
approval are required before implementation resumes.

Superseded by proposed `WS-QUAL-001-01B1A` and `WS-QUAL-001-01B1B`; retain this
contract as circuit-breaker history and do not resume it.

## Goal, Risk, And Budget

Build a read-only, pure-function coverage policy core and behavior tests without
changing the configured floor, CI, committed evidence, or application coverage.

- Risk: L1 test-policy integrity; SLA P1
- Implementation cap: 500 lines outside `.agent-loop`
- Allowed: `backend/scripts/coverage_policy.py`,
  `backend/tests/test_coverage_contract.py`, `docs/operations_backend_testing.md`,
  and WS-QUAL/global memory/reviews
- Forbidden: pyproject/workflow/evidence changes, `backend/app/**`,
  runner/API drills, migrations, schemas, product/auth behavior, unrelated
  tests, skips/xfail, weakened assertions, exclusions, or coverage pragmas

## Acceptance Criteria

- Read-only `--compute-floor` validates complete `app/**/*.py` inventory and
  truncates exact statement coverage to six places with stable exit/diagnostic.
- Pure parsers validate the intended pytest-cov pin/config contract, evidence
  schema/canonical form, strict runner metadata, version/decimal/SHA fields,
  and credential exclusion using temporary fixtures only; no evidence is
  written and current config is unchanged.
- Semantic integrity helpers reuse root `changed_files`, `numstat`, and
  `diff_text`; filter `.agent-loop` only from the implementation numerator;
  detect executable skip/xfail, application pragmas, deleted assertions, scope,
  and size without treating inert negative-fixture strings as violations.
- Parameterized tests cover success and malformed coverage/config/evidence/
  metadata, inventory loss, exclusions, arithmetic boundaries, unsafe names,
  secrets, scope overflow, assertion deletion, and syntax-aware weakening.
- No test executes uncovered application code merely to increase percentage.
- The runbook documents `--compute-floor` as read-only and preparatory: it uses
  temporary non-secret coverage input, does not configure or enforce a floor,
  does not write evidence, and is not the CI policy.

## Allocation And Circuit Breaker

Forecast: policy core 255 lines, parameterized behavior tests 210, runbook 20,
other approved edits 15; hard total 500. Run the circuit breaker after parser,
semantic-delta, and negative tests are complete and before runbook/final polish.
Stop and split again at more than 465 lines before the remaining documented
work, rather than compressing assertions or fail-closed logic.

## Verification And Review

```text
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && .venv/bin/python -m pytest -q tests/test_coverage_contract.py)
(cd backend && .venv/bin/python -m pip check)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta. Human focus:
parser fail-closed behavior, semantic weakening detection, root-helper reuse,
and no premature config/CI/evidence mutation.

Stop above 500 lines or on any need to weaken proof. Do not start 01B2.
