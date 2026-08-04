# WS-QUAL-001-03R Internal Review Evidence

## Reviewed revision

- Code SHA: `23235d506d9f16cb000ba9e9219e4f3e28ddbb79`
- Reviewed base SHA: `cda59fc32e3a60e1e2c337cae7ebeaa94b95e12b`
- Reconciled current-main SHA: `5b853d505b55b6465a472d25aa33caec4be18073`
- Reviewed at: `2026-08-04`
- Open reviewer sessions: none
- Valid findings addressed: yes

## Circuit-breaker decision

PASS with a documented size exception. The diff is large because 94 focused
cases are added to one checker-owned test module, but it crosses one production
boundary, changes no production code, and adds no workflow, migration, public
contract, dependency, skip, xfail, or coverage exclusion. Splitting the same
checker behavior across dependent PRs would add coordination cost without
making the underlying boundary smaller.

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Helpers and fakes remain reviewable and assert concrete service outcomes. |
| QA/test | PASS WITH LOW RISKS | None | Hosted exact-head Backend remains the authoritative acceptance proof. |
| test delta | PASS | None | Additive behavior tests; no weakening, skips, xfails, or exclusions. |
| CI integrity | PASS WITH LOW RISKS | None | No CI changes; coverage arithmetic is coherent and hosted proof remains required. |
| product/ops | PASS | None | Checker routing remains distinct from human product review decisions. |
| reuse/dedup | PASS | None | Added tests are fast boundary tests and do not duplicate the existing HTTP/PostgreSQL suffix. |

Security/auth, architecture, and docs review are not required for this
test-only chunk: it changes no production boundary, authorization behavior,
architecture, public contract, or contributor documentation.

## Findings reconciled

The first reuse pass attributed pre-existing broad API tests to this chunk by
using their post-insertion line numbers. Git history showed that
`test_chunk10_checker_trial_runs_sample_submissions_through_real_api` and the
other cited system tests already existed on `origin/main`; the 03R insertion
only shifted them downward. Re-review of the actual insertion hunk found no
duplicate system flow and withdrew the finding.

During review, ART PR #268 advanced `main`. It touched ART production, tests,
lane routing, and ART documentation but did not overlap the checker test or
QUAL initiative delta. The branch merged exact current main without conflict;
`git diff origin/main...HEAD` retains the reviewed 03R implementation. Main's
new exact hosted baseline is recorded below and the final reconciled head
receives focused reviewer confirmation before publication.

## Commands and evidence

- `cd backend && .venv/bin/ruff check tests/test_checkers.py` — pass.
- Focused new-test selection — 94 passed, 76 deselected in 37.76 seconds.
- `pytest --collect-only -q tests/test_checkers.py` — 170 tests collected.
- Narrow coverage comparison against current main — 168 uniquely covered
  statements: checker service 107, runner 45, compiler 16.
- `git diff --check origin/main...HEAD` — pass.
- Lightweight Agent Gates — 10 passed.
- Allowed-path review — checker tests and the QUAL initiative tree only.
- Test-delta scan — no skip, xfail, deleted assertion, coverage exclusion, or
  CI bypass.
- Full isolated `test_checkers.py` — the constrained local runner reached
  approximately 95 percent (about 163 tests) without a failure before its
  1,200-second bound. This is not recorded as a complete pass.

## Remaining risks

- Hosted Backend must pass every semantic lane and final fan-in on the exact PR
  head.
- Hosted fan-in must prove at least 21,605 / 23,938 covered statements (90.25
  percent). The local projection is 21,621 / 23,938 (90.320829 percent).
- Compare hosted wall and slowest-lane time with main run `30921410531`
  (727.166 seconds wall; 567.994 seconds slowest lane). An unexplained increase
  above 10 percent stops merge readiness.
