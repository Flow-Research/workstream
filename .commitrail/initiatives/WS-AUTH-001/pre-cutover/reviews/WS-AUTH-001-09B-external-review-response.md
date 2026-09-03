# WS-AUTH-001-09B External Review Response

PR: `#143`

CodeRabbit run: `8d818456-089e-4353-87ed-5ca64d53b881`

Reviewed CodeRabbit repair SHA: `52d4d076c151bed3f47428b573c014e131096f4a`

Reviewed coverage repair SHA: `127615fde8f1b5583acf9dbbb3c606db514a455d`

Final reviewed lifecycle SHA: `3a4d042213a555df7f479408ffafc43911296528`

## Actionable Findings

| Finding | Disposition | Repair and proof |
|---|---|---|
| Locked authorization queries may return stale identity-map rows | Accepted | Added `populate_existing=True` to locked caller and eligible-human profile/link queries. A real independent-session PostgreSQL test proves cached active rows refresh to suspended/revoked and cached inactive rows refresh to active. |
| Provisioning accepts subject whitespace rejected by the verifier | Accepted | Reject leading/trailing whitespace without normalizing accepted bytes. The route test proves stable non-echoing 422 behavior, and contract/spec/operations wording agrees. |
| Replay accepts deactivated profiles and revoked links | Accepted | Replay now returns the existing bounded unavailable failure for either inactive state. Focused cases preserve all mismatch and missing-state proof. |
| CI does not enforce AUTH-09B's 90 percent subsystem floors | Accepted and strengthened | Added separate exact actor, authorization, and verifier `coverage report --fail-under=90` steps after full-suite coverage and before isolated E2E. Agent Gates pin names, commands, scope, threshold, uniqueness, and ordering. |

## Backend Failure

The first PR Backend run failed one exact audit-parity assertion because its
static active ActionId set omitted the deliberately activated
`actor.service.provision`. The other 1,240 tests passed and the run measured
84.87 percent global coverage. `test_audit.py` now includes exactly that one
active action, and the 09B contract explicitly allows the touched test. The
focused parity test passes.

## Coverage Gate Failure

The replacement Backend run passed all 1,242 tests at 84.92 percent global
coverage. The new authorization subsystem gate then correctly failed at 1,600
statements, 164 misses, and 89.75 percent. Two non-isolated behavior tests now
prove successful definition-read authorization, exact typed resource binding,
caller touch, route-owned commit, rollback, and stable retryable 503 mapping.
They execute nine previously missed statements, projecting 155 misses and
90.31 percent on the unchanged denominator. No production code, include scope,
threshold, skip, or exclusion changed; replacement CI remains authoritative.

## Pre-Merge Warnings

The PR description warning is addressed by the full trust-bundle sections in
the updated PR body. The generic CodeRabbit docstring percentage is not used to
add narration-only docstrings: GitHub Backend's repository-configured
`docstr-coverage --config .docstr.yaml` step passed before the full-suite test
failure, and Ruff reports no docstring issue.

## Validation

- Ruff and compileall: pass.
- Agent Gates: 80 passed.
- Isolated stale-row and replay tests: two passed.
- Isolated provisioning concurrency/privacy test: one passed.
- API/OpenAPI tests: 16 passed.
- Exact active-action audit parity test: one passed.
- Complete isolated PostgreSQL authorization file: 85 passed.
- New focused route behavior tests: two passed directly and under targeted
  coverage.
- Stale Workstream, authorization, and artifact scans: pass.
- Markdown links, merge intent, internal-review evidence, and diff integrity:
  pass before publication.

## Review Result

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test-delta tracks pass the exact repair and
final lifecycle state at `3a4d042`. No service admission, grant, assignment,
ART/REV/CON action activation, compatibility path, or AUTH-09C start was
introduced.

Replacement GitHub Backend, Agent Gates, and CodeRabbit checks remain required.
