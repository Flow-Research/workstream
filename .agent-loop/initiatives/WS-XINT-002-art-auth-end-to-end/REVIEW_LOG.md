# Review Log: WS-XINT-002

## Planning review

Architecture, security/auth, QA/test, product/ops, senior engineering, and CI
integrity initially returned blocking findings. The plan was repaired to split
submission activation, add checker remediation, require paired reviewer/service
authority, complete every chunk contract, and pass repository documentation
gates. All six tracks then passed with no blocking findings.

## PR #209 external review

CodeRabbit raised twelve actionable comments on the initial PR head
`95090be5`. All were accepted and repaired as recorded in
`reviews/WS-XINT-002-PLAN-external-review-response.md`. Focused internal
security/architecture re-review and exact-head hosted checks are required after
the repair commit.

Product/ops re-review found that CodeRabbit's 05C atomic-fact suggestion would
prematurely include `allow_review` in Submission creation. The repair instead
keeps `allow_review` in the later checker/routing spine for the new Submission.

## WS-XINT-002-03 internal review

Senior engineering, architecture, QA/test, security/auth, product/ops, CI
integrity, docs, and test-delta tracks passed after all valid findings were
fixed. Reuse/dedup passed with low residual risk. The final review record and
exact evidence are in `reviews/WS-XINT-002-03-internal-review.md`; no blocking
finding remains before exact-head external review.

## PR #212 external review

The first hosted Backend run exposed three stale test expectations after all
four semantic lanes executed. The tests were strengthened to prove exact
claim/terminal capability consumption, terminal-only authority drift, and the
accurate active custody-table header. The isolated four-test PostgreSQL rerun
and QA, test-delta, and CI-integrity re-reviews passed. Details are in
`reviews/WS-XINT-002-03-external-review-response.md`.
