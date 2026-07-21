# WS-ENG-005-01 Internal Review Evidence

Reviewed code SHA: `49afb7db1822091b4aa12b82d73fc22b4d95d428`

Reviewed against trusted main: `dd4a454b9ab8735a3c4aa8e85e7e64b1e7222b0a`

Reviewed at: `2026-07-21T15:19:52Z`

Reviewer run IDs: `parallel_senior_arch_docs`, `parallel_qa_ci_tests`,
`parallel_security_ops_reuse`

## Scope

Replace repository-global active-work serialization with exactly one active
planning or implementation chunk per initiative, preserving all signed start,
cancel, merge, ledger, projection, and review controls.

## Deterministic evidence

- Ruff — pass.
- Focused Python suite — 209 passed.
- Agent gate runner — 89 passed.
- Updater branch coverage — 90.22 percent; unchanged 90 percent floor passed.
- Checker branch coverage — 90.81 percent; unchanged 90 percent floor passed.
- Real signed-state drill — AUTH-10A remained active while exact ART-02C3
  started in a temporary rebuilt state; independent checker passed.
- Merge intent, stale wording, Markdown links, and diff integrity — pass.

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| Senior engineering | PASS | None | Only global-idle predicates are removed; initiative ownership remains simple. |
| QA/test | PASS | None | Three mixed-phase initiatives and both merge/cancel orders preserve unrelated activity. |
| Security/auth | PASS | None | Same-initiative, exact-main/tip, permission, replay, completion, selection, and cancel controls remain. |
| Product/ops | PASS | None | Signed projections clearly distinguish canonical events from chat/worktree claims. |
| Architecture | PASS | None | Existing initiative-keyed ledger is reused without a second scheduler or lock registry. |
| CI integrity | PASS | None | Workflows and thresholds are unchanged; both coverage gates pass. |
| Docs | PASS | None | Policy, skill, AGENTS, operations, and generated projection wording are consistent. |
| Reuse/dedup | PASS | None | Existing apply/replay/checker and rendering paths remain canonical. |
| Test delta | PASS | None | Tests add successful parallel close order and checker parity without weakening assertions. |

## Findings repaired

- Replaced misleading merge-only generated projection wording with signed
  merge/start/cancel wording in updater and independent checker.
- Added successful merge-before-cancel and cancel-before-merge proof with
  unrelated initiative preservation and independent checker agreement.

Open sub-agent sessions: none

Valid findings addressed: yes

Fresh GitHub checks, CodeRabbit when available, and explicit human approval of
the specific PR remain before merge.
