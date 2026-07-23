# Internal Review Evidence: WS-ENG-007-00R4

## Chunk

`WS-ENG-007-00R4` — Cross-Initiative Authority Projection Repair

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 145c1f92f13ad3467ce89fac6895828ef9d01f24

Reviewed at: 2026-07-23T10:50:17Z

The `/root/eng006_*` sessions were inherited from the ENG-006 reviewer pool and
explicitly reassigned to this WS-ENG-007-00R4 review. Every track is rebound to
the exact reviewed implementation SHA above; session names grant no
cross-initiative authority.

Reviewer run IDs: senior-engineering=/root/eng006_senior_arch_docs; QA/test=/root/eng006_qa_ci_tests; security/auth=/root/eng006_security_ops_reuse; product/ops=/root/eng006_security_ops_reuse; architecture=/root/eng006_senior_arch_docs; docs=/root/eng006_senior_arch_docs; CI-integrity=/root/eng006_qa_ci_tests; reuse/dedup=/root/eng006_security_ops_reuse; test-delta=/root/eng006_qa_ci_tests

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Authority lifecycle and global evidence remain separate and ledger-bound. |
| QA/test | PASS AFTER FIXES | None | Exact cross-initiative regression and malformed-basis cases pass. |
| security/auth | PASS | None | Start authority, permissions, and signed-basis binding are unchanged. |
| product/ops | PASS | None | Per-initiative concurrency remains isolated; no product lifecycle change. |
| architecture | PASS AFTER FIXES | None | Removed invalid synthetic record composition without adding a parallel path. |
| CI integrity | PASS AFTER FIXES | None | 289 tests pass and literal updater branch coverage is 90.18 percent. |
| docs | PASS | None | Contract, chunk map, and status describe the bounded recovery. |
| reuse/dedup | PASS | None | Existing transition validators remain the single ledger-binding path. |
| test delta | PASS AFTER FIXES | None | Additive adversarial tests; no skips, removals, or weakened assertions. |

## Valid Findings Addressed

- Prevented the independent checker from crashing on non-object authority
  metadata and restored explicit source scalar, timestamp, PR, metadata, and
  intent-path validation.
- Added an independent checker regression for an older idle initiative starting
  after a different initiative's protected merge became global state.
- Added six updater mutation cases for malformed authority source and completed
  metadata.
- Raised exact updater branch coverage from 89.96 percent to 90.18 percent
  without rounding, threshold changes, exclusions, or test weakening.

## Commands Run

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p pytest_cov -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py --cov=scripts.update_post_merge_memory --cov-branch --cov-report=term --cov-fail-under=90 --cov-precision=2
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
git diff --check
```

The combined gate passed 289 tests. Exact updater branch coverage is 90.18
percent against a literal 90.00 percent blocking floor.

## Remaining Risks

The current failed start run remains unsigned and inert. After this recovery
merges and generated memory succeeds, ENG-006 still requires a fresh explicit
start against exact current `main`; nothing starts automatically.

## Stop Condition

No successor is active. `WS-ENG-007-01` and `WS-ENG-006-01` each retain their
own explicit signed start gate.
