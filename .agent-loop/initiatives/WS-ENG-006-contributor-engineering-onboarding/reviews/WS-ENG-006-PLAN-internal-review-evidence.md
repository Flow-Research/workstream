# Internal Review Evidence

## Chunk

`WS-ENG-006-00`

This review also covers the reviewed specification and chunk contract for
`WS-ENG-006-01`; it does not authorize that implementation to start.

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 7c7d5ec2b8264a5c8f4a689195071157263f4b1f

Reviewed at: 2026-07-22T10:20:00Z

Reviewer run IDs: eng006_senior_arch_docs, eng006_qa_ci_tests, eng006_security_ops_reuse

After the reviewed SHA, only evidence and status files changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Durable replay and bounded lifecycle reviewed. |
| QA/test | PASS AFTER FIXES | None | All 95 Agent Gate tests passed. |
| security/auth | PASS AFTER FIXES | None | Unsigned planning boundary and recovery containment reviewed. |
| product/ops | PASS | None | Product lifecycle and contributor authorization are unchanged. |
| architecture | PASS AFTER FIXES | None | One reducer/signer/state path remains canonical. |
| CI integrity | PASS AFTER FIXES | None | Existing gates and thresholds are not weakened. |
| docs | PASS AFTER FIXES | None | Policy, AGENTS, memory README, and runbook agree. |
| reuse/dedup | PASS | None | Existing schema-v2 recovery and reducers are reused. |
| test delta | PASS AFTER FIXES | None | Negative, replay, squash, and rebase cases were added. |

## Valid Findings Addressed

- Added independent checker support for the planning-intake record.
- Bound the reviewed PR delta to the first-parent-to-merge delta instead of
  comparing whole trees, so unrelated trusted-main advancement is supported.
- Required exact successful `agent-gates` and `test` check runs from the GitHub
  Actions app; CodeRabbit remains supplementary external evidence.
- Closed the planning path grammar, including hidden paths, foreign paths,
  malformed slugs, noncanonical chunk names, and nested `AGENTS.md`.
- Made the independent checker recompute the durable signed-main delta, modes,
  blobs, tree identities, paths, and digest.
- Added clean replay proof for squash and rebase shapes after deleting refs,
  expiring reflogs, pruning Git objects, and proving the original head is gone.
- Fixed CodeRabbit findings so malformed tree responses fail closed and the
  historical PR reference renders as ordinary runbook prose.
- Added independent path mutations and restored checker coverage to 90.08%
  without changing the 90% threshold.
- Bound the exact missed PR #176 PLAN3 merge followed by `WS-ENG-006-00`,
  authenticated the activation checks, and consumed both recovery identities
  before signing, with CLI reload, collision, replay, and leakage checks.

## Commands Run

```bash
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p pytest_cov.plugin -q --cov=scripts.update_post_merge_memory --cov-branch --cov-report=term-missing --cov-fail-under=90 scripts/test_agent_gates.py scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 -m py_compile scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py scripts/test_agent_gates.py
git diff --check origin/main...HEAD
```

## Remaining Risks

- The recovery certificate is intentionally exceptional, but it is bound to
  exact PR #176 followed by one ENG-006 activation target; both identities are
  consumed before state signing and cannot authorize later work.
- Fresh GitHub checks remain pending after the final evidence-only commit.
