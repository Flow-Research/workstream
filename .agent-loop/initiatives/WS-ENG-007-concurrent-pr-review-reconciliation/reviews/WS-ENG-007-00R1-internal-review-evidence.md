# Internal Review Evidence: WS-ENG-007-00R1

## Chunk

`WS-ENG-007-00R1` - Planning-Intake Tree Recovery

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: c620610e20061b9755c825ed2dc1f89ba80bef4a

Reviewed at: 2026-07-23T05:42:14Z

Reviewer run IDs: senior-engineering=/root/eng006_senior_arch_docs; QA/test=/root/eng006_qa_ci_tests; security/auth=/root/eng006_security_ops_reuse; product/ops=/root/eng006_security_ops_reuse; architecture=/root/eng006_senior_arch_docs; docs=/root/eng006_senior_arch_docs; CI-integrity=/root/eng006_qa_ci_tests; reuse/dedup=/root/eng006_security_ops_reuse; test-delta=/root/eng006_qa_ci_tests

The inherited `/root/eng006_*` values identify the available reviewer sessions.
Each session was explicitly reassigned to this exact WS-ENG-007 recovery head.

## Reviewer Results

| Reviewer track | Result | Blocking findings |
|---|---:|---|
| senior engineering | PASS AFTER FIXES | None |
| QA/test | PASS AFTER FIXES | None |
| security/auth | PASS AFTER FIXES | None |
| product/ops | PASS | None |
| architecture | PASS AFTER FIXES | None |
| CI integrity | PASS AFTER FIXES | None |
| docs | PASS AFTER FIXES | None |
| reuse/dedup | PASS | None |
| test delta | PASS AFTER FIXES | None |

## Valid Findings Addressed

- Replaced adjacent lexical prefix checking with an all-path ancestor check, so
  separating siblings and leaf-plus-directory descendants fail closed.
- Added exact PR #187 and full-SHA production recovery-policy pinning and an
  ENG-007 PLAN-to-00R1 two-merge consumption/replay integration.
- Added the recursive 19-entry versus 13-leaf regression, supported and hostile
  Git entry matrices, transition proof, PR inventory mismatches, and changed
  symlink/gitlink rejection.
- Added the operational stop statement: recovery starts neither successor and
  both require their own ordinary signed explicit start.
- Corrected the contract to require unchanged existing serialization and
  independent-checker suites instead of claiming new golden fixtures.

## Commands Run

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_agent_gates.py scripts/test_check_loop_memory_state.py
python3 scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

Results: 217 focused tests passed; 97 manual agent-gate tests passed; all other
commands passed.

## Remaining Risk

The recovery is intentionally adjacency-bound. Any merge to `main` before this
repair invalidates the certificate and requires a new reviewed recovery plan.

## Stop Condition

`WS-ENG-007-01` and `WS-ENG-006-01` remain stopped. Each requires a separate
ordinary explicit signed start on exact current `main` after recovery succeeds.
