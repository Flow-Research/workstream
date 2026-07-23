# Chunk Contract: WS-ENG-007-00R5 — R4 Activation Recovery

## Parent initiative

`WS-ENG-007` — Concurrent PR Review Reconciliation

## Goal

Reconcile exact merged recovery chunk `WS-ENG-007-00R4` and this activation
chunk into signed loop memory so ordinary cross-initiative starts can resume.

## Why this chunk exists

PR #191 fixed cross-initiative authority projection composition, but its own
merge had no signed start because the mechanism being repaired was unavailable.
The post-merge workflow therefore rejected PR #191 before exercising the fix.

## Risk class

L1 / P0 signed-memory recovery.

## Start phase

Recovery implementation. Signed state cannot start this chunk until the exact
unrecorded predecessor is reconciled.

## Allowed files

```text
.agent-loop/policies/loop-memory-recovery.json
scripts/test_update_post_merge_memory.py
scripts/test_agent_gates.py
scripts/update_post_merge_memory.py
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/**
.agent-loop/merge-intents/WS-ENG-007-00R5.json
```

## Not allowed

```text
workflow, generator, checker, permission, authority, CI, or coverage changes
application, API, database, auth, payment, or product changes
wildcard, persistent, reordered, or reusable exemptions
automatic successor starts
```

## Acceptance criteria

- [ ] Schema-v5 recovery binds signed basis `a3eecadc…` and names exact merged
      PR #191 / `WS-ENG-007-00R4` /
      `9bf16d478f669d48172810c83cdf6a7d2b8992ed` as its sole predecessor.
- [ ] Activation names only `WS-ENG-007-00R5`; the target merge identity is
      collected from GitHub and must match it exactly.
- [ ] Planned history must be exactly `[9bf16d4…, target]`, first-parent adjacent
      from current signed `a3eecadc…` through the target.
- [ ] Both merges must carry successful merge-bound `agent-gates` and `test`
      provenance. CodeRabbit remains supplementary and mutable reruns cannot
      rewrite or block accepted evidence.
- [ ] Both exemptions are consumed before signing and cannot persist or replay.
- [ ] Exactly one merge intent stops at `WS-ENG-007-01` and requires a separate
      explicit start.
- [ ] ENG-006 remains idle until a fresh signed start after successful recovery.

## Verification commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Confirm the certificate is exact, adjacent, check-bound, consumed, and unable to
authorize any chunk other than `00R4` plus this activation.

## Stop conditions

Stop if recovery requires a wildcard exemption, missing required checks,
non-adjacent history, persisted authority, or an automatic successor start.
