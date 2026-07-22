# WS-ENG-004-01R1 Internal Review Evidence

Reviewed code SHA: `d845fcca55a025b477d2ec3036373dfcdc7b3737`

Reviewed against trusted main: `dda60ed0cb97d9de4a375df4147f31172cb3839b`

Reviewed at: `2026-07-21T14:01:02Z`

Reviewer run IDs: `recovery_senior_arch_docs`, `recovery_qa_ci_tests`,
`recovery_security_ops_reuse`

## Scope

Authenticate signed semantic state independently of renderer-version equality,
regenerate all projections in a fresh root, preserve strict publication
validation, and bind exact two-merge recovery for PR #169 plus this repair.

## Deterministic evidence

- Ruff — pass.
- Focused Python suite — 207 passed.
- Agent gate regression runner — 89 passed.
- Updater branch coverage — 90.07 percent; unchanged 90 percent floor passed.
- Checker branch coverage — 90.18 percent; unchanged 90 percent floor passed.
- Real signed automation-tip replay — authenticated `e89e42e5`, reconciled
  PR #169, consumed recovery inventory, and passed independent state checking.
- Merge-intent validation, stale wording, Markdown links, and diff integrity — pass.

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| Senior engineering | PASS | None | Migration tolerance is isolated and the fresh rebuild is deterministic. |
| QA/test | PASS | None | Regression and hostile cases preserve strict rejection outside rebuild. |
| Security/auth | PASS | None | State, ledger, manifest, tree, digests, and Ed25519 signature remain mandatory. |
| Product/ops | PASS | None | The repaired chronology identifies 01 as merged and 01R1 as the sole active repair. |
| Architecture | PASS | None | Authentication, migration, rendering, validation, and recovery remain separate boundaries. |
| CI integrity | PASS | None | No workflow or threshold changed; both 90 percent coverage gates pass. |
| Docs | PASS | None | Contract, status, chunk map, logs, and external response are consistent. |
| Reuse/dedup | PASS | None | Existing semantic, projection, manifest, signature, and latest-state helpers are reused. |
| Test delta | PASS | None | One meaningful renderer-drift regression was added; no test was removed or weakened. |

## Findings repaired

- Corrected stale lifecycle memory that still called merged chunk 01 active and
  awaiting publication.
- Reused the existing latest-initiative map per the valid PR #169 CodeRabbit
  efficiency comment.

Open sub-agent sessions: none

Valid findings addressed: yes

Fresh GitHub checks, CodeRabbit, and explicit human approval of the repair PR
remain before merge.
