# Internal Review Evidence: WS-ENG-007-00R5

## Chunk

`WS-ENG-007-00R5` — R4 Activation Recovery

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 10159497b3f3ca3464cbbbfd10f16945ade1879a

Reviewed at: 2026-07-23T11:58:47Z

The `/root/eng006_*` sessions were explicitly reassigned to this R5 recovery
review. Every track is bound to the reviewed SHA above; session names grant no
cross-initiative authority.

Reviewer run IDs: senior-engineering=/root/eng006_senior_arch_docs; QA/test=/root/eng006_qa_ci_tests; security/auth=/root/eng006_security_ops_reuse; product/ops=/root/eng006_security_ops_reuse; architecture=/root/eng006_senior_arch_docs; docs=/root/eng006_senior_arch_docs; CI-integrity=/root/eng006_qa_ci_tests; reuse/dedup=/root/eng006_security_ops_reuse; test-delta=/root/eng006_qa_ci_tests

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Exact schema-v5 bridge and signed-basis binding accepted. |
| QA/test | PASS AFTER FIXES | None | Mutable schema-v3 authority rejected; exact functional proof added. |
| security/auth | PASS AFTER FIXES | None | Merge-bound evidence, consumption, and replay boundaries accepted. |
| product/ops | PASS | None | No product behavior or automatic successor start. |
| architecture | PASS AFTER FIXES | None | Minimal closed extension of the existing recovery reducer. |
| CI integrity | PASS | None | 297 tests; updater 90.46 percent and checker 90.40 percent. |
| docs | PASS AFTER FIXES | None | R1–R4 history and R5 live gate are consistent. |
| reuse/dedup | PASS | None | No parallel workflow or recovery implementation. |
| test delta | PASS AFTER FIXES | None | Exact R4→R5, wrong basis, consumption, replay, and CodeRabbit cases. |

## Valid Findings Addressed

- Rejected schema v3 because it re-queried mutable post-merge checks and made
  CodeRabbit part of recovery authority.
- Added schema v5 with an exact signed basis, exactly one recovered predecessor,
  and persisted merge-bound `agent-gates` plus `test` evidence.
- Added functional proof that CodeRabbit may be absent, mutable check validation
  is never called, exemptions are consumed, replay is inert, and a wrong basis
  fails closed.
- Corrected authored lifecycle docs so reconciled R1–R3 history, merged R4, and
  active R5 recovery do not conflict.

## Commands Run

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p pytest_cov.plugin -q --cov=scripts.update_post_merge_memory --cov-branch --cov-report=term --cov-fail-under=90 --cov-precision=2 scripts/test_agent_gates.py scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p pytest_cov.plugin -q --cov=scripts.check_loop_memory_state --cov-branch --cov-report=term --cov-fail-under=90 --cov-precision=2 scripts/test_agent_gates.py scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
git diff --check
```

## Remaining Risks

Any intervening `main` merge breaks exact adjacency and must fail closed. After
R5 merges, the post-merge workflow—not this PR—must prove full consumption and
publish signed state before ENG-006 can start.

## Stop Condition

ENG-006 and `WS-ENG-007-01` are not active. R5 recovery is active and stops at
`WS-ENG-007-01`, which still requires a separate explicit start.
