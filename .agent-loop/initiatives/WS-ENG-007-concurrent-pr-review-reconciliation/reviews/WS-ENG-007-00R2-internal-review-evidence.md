# Internal Review Evidence: WS-ENG-007-00R2

## Chunk

`WS-ENG-007-00R2` - Canonical Check Evidence Recovery

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: bb3f03b3b9026a7eb3a9adb40e657e07c4eafac3

Reviewed at: 2026-07-23T07:05:13Z

Reviewer run IDs: senior-engineering=/root/eng006_senior_arch_docs; QA/test=/root/eng006_qa_ci_tests; security/auth=/root/eng006_security_ops_reuse; product/ops=/root/eng006_security_ops_reuse; architecture=/root/eng006_senior_arch_docs; docs=/root/eng006_senior_arch_docs; CI-integrity=/root/eng006_qa_ci_tests; reuse/dedup=/root/eng006_security_ops_reuse; test-delta=/root/eng006_qa_ci_tests

The inherited session names identify the available reviewer pool. Every session
was explicitly assigned to this exact WS-ENG-007-00R2 revision.

## Reviewer Results

| Reviewer | Result | Blocking findings |
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

- Changed rerun recency from completion time to parsed invocation start plus
  strict positive check-run ID, preventing delayed older success from hiding a
  newer failure.
- Validated every protected candidate, closed conclusion values, and enforced
  check-run ID uniqueness across both protected names.
- Required exact protected provenance for PR #187, PR #188, and the activation
  target.
- Closed policy schema v3 to at most two recovered merges with independent
  chunk, PR, and SHA uniqueness and exact first-parent order.
- Exercised the actual serialized recovery-file boundary and corrected its
  bound from two to three entries.
- Preserved recovery transport schema v1 at its historical two-entry maximum;
  introduced schema v2 requiring exactly three entries.
- Added full prepare-to-file-to-three-updates-to-consumption CLI coverage,
  over-bound/partial/unknown rejection, deterministic fresh-state comparison,
  and replay protection.

## Commands Run

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_agent_gates.py scripts/test_check_loop_memory_state.py
python3 scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

Results: 231 focused tests and 98 manual gate tests passed. All other commands
passed. Live PR #187 and PR #188 protected-check responses also validated under
the canonical selector.

## Remaining Risk

Recovery remains first-parent adjacency-bound. Any intervening `main` merge
invalidates the certificate and requires a fresh reviewed plan.

## Stop Condition

Neither successor is active. `WS-ENG-007-01` and `WS-ENG-006-01` each require
their own explicit signed start after successful reconciliation.
