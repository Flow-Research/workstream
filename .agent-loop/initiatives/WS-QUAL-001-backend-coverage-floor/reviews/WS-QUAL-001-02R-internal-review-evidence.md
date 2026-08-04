# WS-QUAL-001-02R Internal Review Evidence

## Reviewed revision

- Code SHA: `f32ebc6c0c2cf8411ca0373127b0fefd523156f8`
- Base SHA: `b47a7e64f7d75cda8a0681d1aff3bf0c4a5be4aa`
- Reviewed at: `2026-08-04T09:02:29Z`
- Open reviewer sessions: none
- Valid findings addressed: yes

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Large test module and fake fidelity are future maintainability risks. |
| QA/test | PASS WITH LOW RISKS | None | Exact-head hosted coverage remains the final acceptance proof. |
| test delta | PASS | None | Additive tests; no skips, xfails, deleted assertions, or exclusions. |
| CI integrity | PASS WITH LOW RISKS | None | No CI changes; hosted fan-in and runtime evidence remain required. |
| product/ops | PASS | None | Project setup provenance and lifecycle semantics are preserved. |
| reuse/dedup | PASS | None | No blocking duplicate helper or parallel convention. |

Security/auth, architecture, and docs review are not required for this
test-only chunk: it changes no production boundary, authorization behavior,
architecture, public contract, or contributor documentation.

## Findings addressed

- The first review found the branch behind `main`. Current `main` was merged;
  the resulting delta is only `backend/tests/test_projects.py`.
- The first QA pass used PLAN2's older baseline. The refreshed authoritative
  hosted baseline is Backend run `30891776021` on `b47a7e64`: 20,782 covered of
  23,455 statements. The exact 89.55-percent threshold is 21,004 statements.
- Added-test coverage union supplies 222 previously missing statements:
  project service 194, project repository 15, and project setup queue 13.
  The projected exact-denominator result is 21,004 / 23,455, or 89.550203
  percent. Hosted exact-head fan-in must confirm it.

## Commands and evidence

- `cd backend && .venv/bin/ruff check tests/test_projects.py` — pass.
- Focused new-test review run — 59 passed, 322 deselected; reviewer-observed
  times ranged from 60.45 to 90.22 seconds on the constrained local machine.
- `git diff --check origin/main...HEAD` — pass.
- Allowed path check — only `backend/tests/test_projects.py` before this
  evidence record was added.
- Test-delta scan — no skip, xfail, assertion deletion, or coverage exclusion.
- Full isolated `test_projects.py` run — no failure observed, but the bounded
  local runner timed out at 1,200 seconds at 40 percent completion. This machine
  is not accepted as runtime evidence; hosted Backend is mandatory.

## Remaining risks

- Hosted Backend must prove the exact final coverage and complete test result.
- Compare hosted wall and slowest-lane time with main run `30891776021`
  (718.586 seconds wall; 546.201 seconds slowest lane). An unexplained increase
  above 10 percent stops merge readiness for review.
