# Internal Review Evidence: WS-ENG-007-00R3

## Chunk

`WS-ENG-007-00R3` — Merge-Bound Evidence Recovery

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 4a3eee7fdd80970675ae2574542073b8a92e1ef9

Reviewed at: 2026-07-23T10:30:00Z

The `/root/eng006_*` sessions were inherited from the ENG-006 reviewer pool and
explicitly reassigned to this WS-ENG-007-00R3 review. Every track is rebound to
the exact reviewed implementation SHA below; the session name grants no
cross-initiative authority.

Reviewer run IDs: senior-engineering=/root/eng006_senior_arch_docs; QA/test=/root/eng006_qa_ci_tests; security/auth=/root/eng006_security_ops_reuse; product/ops=/root/eng006_security_ops_reuse; architecture=/root/eng006_senior_arch_docs; docs=/root/eng006_senior_arch_docs; CI-integrity=/root/eng006_qa_ci_tests; reuse/dedup=/root/eng006_security_ops_reuse; test-delta=/root/eng006_qa_ci_tests

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Merge cutoff and recovery architecture accepted. |
| QA/test | PASS AFTER FIXES | None | CodeRabbit is supplementary; proof matrix accepted. |
| security/auth | PASS AFTER FIXES | None | Exact one-use authority and replay boundaries accepted. |
| product/ops | PASS | None | No product lifecycle behavior changed. |
| architecture | PASS AFTER FIXES | None | One shared reconciliation reducer. |
| CI integrity | PASS AFTER FIXES | None | No CI, coverage, or required-check weakening. |
| docs | PASS AFTER FIXES | None | Runbook and durable artifacts aligned. |
| reuse/dedup | PASS AFTER FIXES | None | Workflow duplication removed. |
| test delta | PASS AFTER FIXES | None | Cutoff, pagination, checker, certificate, and reducer tests added. |

## Valid Findings Addressed

- Filtered classifiable post-merge reruns before validating eligible protected
  evidence, and removed the redundant mutable planning-intake validator.
- Removed CodeRabbit from planning and recovery authority while retaining it as
  diagnostic external evidence.
- Persisted and independently validated exact protected-run provenance with a
  strict merge cutoff and canonical RFC3339 timestamps.
- Bound PR #189's sole recovery-only mode to its exact PR, merge, head, chunk,
  signed basis, activation, policy schema, reason, and certificate digest.
- Added bounded complete pagination with stable totals and global ID overlap
  rejection.
- Replaced duplicated YAML reducers with one atomic `reconcile` command shared
  by merge and explicit-start workflows.
- Added cutoff poisoning, pagination drift, mandatory-cutover, strict timestamp,
  certificate mutation, and shared-reducer tests.

## Commands Run

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
python3 -m py_compile scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py
```

Final exact-head verification passed 278 updater-gate tests at 90.10 percent
branch coverage and the independent checker at 90.41 percent. Agent Gates
passed all 98 standalone scenarios. All reviewer tracks reapproved exact head
`4a3eee7fdd80970675ae2574542073b8a92e1ef9` after the CodeRabbit repairs.

## Remaining Risks

The schema-v4 bridge is intentionally exact. Any intervening protected-main
merge before this chunk invalidates adjacency and requires a freshly reviewed
certificate rather than reinterpretation.

## Stop Condition

No successor is active. ENG-006 documentation work and ENG-007-01 each require
their ordinary explicit signed start after successful reconciliation.
