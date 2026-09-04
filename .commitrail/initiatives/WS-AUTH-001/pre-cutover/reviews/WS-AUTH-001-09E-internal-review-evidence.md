# WS-AUTH-001-09E Internal Review Evidence

Reviewed code SHA: `d5162ce717993d69bd6c4879f743bf6e24a4825d`

Reviewed implementation SHA: `881ac7fc`

Reviewed integrated implementation SHA: `98376fd13aca199980c2b2d8a0b703eb12a367ce`

Reviewed against trusted main: `8d5eb15b384fd75787ce98a099400a1d335d2560`

Integrated implementation reviewed against trusted main: `44f2467c`

Final closeout reviewed against trusted main:
`3b1d63796c086f53fc2b0aeefe096387b82485ec`

Latest closeout reviewed against trusted main:
`cb9d5f9f9c311e644ed20a988c69843d3618a6b0`

Reviewed at: `2026-07-20T04:43:38Z`

Reviewer run IDs: `review_senior`, `review_qa`, `review_security`,
`review_product_ops`, `review_architecture`, `review_ci`, `review_docs`,
`review_reuse`, `review_test_delta`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- Fresh isolated PostgreSQL focused evidence passed 312 tests in 2,626.88
  seconds after two repaired expectation failures were rerun successfully.
- Ten direct repair tests pass for inactive observation suppression and real
  lock-time lifecycle, identity, matrix, and availability drift denial.
- Four isolated PostgreSQL ART admission tests pass after the trusted-main
  integration repair, proving exact human and checker-service context
  composition while preserving locked identity validation.
- The real isolated HTTP API contract drill passed, including unprovisioned,
  provisioned, suspended, reactivated, revoked-link, and repaired-link service
  states.
- Ruff, 90.3 percent repository docstring coverage, both stale scanners,
  Markdown links, diff integrity, and all 88 agent gates pass.
- No workflow, dependency manifest, Alembic revision, migration allocation,
  skip, xfail, test deletion, coverage exclusion, or threshold reduction was
  introduced. Migration `0028` remains owned by the independent ART work.
- GitHub Backend is the mandatory hosted proof for the unchanged 78 percent
  repository-wide floor and the persistent 90 percent actor and authorization
  subsystem reports. The intentionally stopped local full run is not claimed
  as evidence.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Inactive subjects no longer stage observations; maintainability is sound. |
| QA/test | PASS AFTER FIXES | none | Real revalidation proves lifecycle, identity, matrix, and availability drift denial. |
| security/auth | PASS | none | Exact identity resolution, fail-closed dispatch, rollback, and evidence privacy hold. |
| product/ops | PASS | none | No feature action, human workflow, payment, review, or reputation behavior activates. |
| architecture | PASS | none | Typed AUTH boundaries and the reusable actor lock seam remain closed. |
| CI integrity | PASS | none | Hosted full coverage retains every existing threshold and failure gate. |
| docs | PASS AFTER FIXES | none | Operations now describe present central AUTH admission and legacy rejection. |
| reuse/dedup | PASS | none | Existing lookup, lock, matrix, timestamp, and evidence paths are reused. |
| test delta | PASS | none | No weakened, removed, skipped, or xfailed test; integration proof complements mocks. |

## Findings Resolved

Valid findings addressed: yes

Open sub-agent sessions: none

Candidate `65ee8887` staged service observations before lifecycle denial and
tested drift through an overly shallow callback. Repaired candidate `881ac7fc`
gates observations on active rows, fails malformed locked reconstruction
closed, and directly proves lifecycle, identity, matrix, and availability
drift. Documentation candidate `d859af3d` removes one stale pre-09E operations
sentence and corrects the dependency docstring. All required tracks pass with
no remaining blocking finding. Trusted main then advanced through ART PR #154.
Security review rejected merge candidate `d2d974eb` because ART admission still
checked the former concrete `AuthorizationContext`; integrated candidate
`98376fd1` repairs that boundary with exact membership in the two closed
concrete context types and passes all nine tracks after the stale timing docs
were corrected. Current main then advanced through CON PR #155. Merge head
`4fd3537a` inherits CON's shared outbox and `0029_shared_transactional_outbox`
unchanged, has no conflict-resolution delta, and passes all nine integration
tracks; AUTH still adds no outbox coupling or migration.
CodeRabbit then identified unclear specification wording and an unguarded
post-lock human actor-kind reconstruction. Repair `d5162ce7` clarifies the
wording and returns bounded `permission_not_granted` before context
reconstruction or grant lookup when the locked profile is no longer human.
Ruff and 11 focused tests pass, and all nine exact-SHA repair tracks report no
remaining finding.

## Remaining Risk And Gate

GitHub Backend, Agent Gates, external review, and explicit human review remain.
No feature action is active. ART owns migration `0028`; this chunk adds no
migration, and its same-initiative successor still requires a separate explicit
start after this PR and signed memory, subject to its own contract prerequisites.
