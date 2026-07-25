# Chunk Contract: WS-ENG-007-00R6 — ART PLAN2 Signed-Memory Recovery

## Parent initiative

`WS-ENG-007` — Concurrent PR Review Reconciliation

## Goal

Reconcile exact merged planning chunk `WS-ART-001-PLAN2` and this activation
chunk into signed loop memory so ordinary writer-directed starts can resume.

## Why this chunk exists

PR #197 merged without the required signed planning start. Loop-memory replay
correctly fails closed at that merge and therefore cannot reach later protected
main or apply any new explicit start.

## Risk class

L1 / P0 signed-memory recovery.

## Start phase

Recovery implementation. Signed state cannot start this chunk until the exact
unrecorded predecessor is reconciled.

## Allowed files

```text
.agent-loop/policies/loop-memory-recovery.json
.agent-loop/REVIEW_LOG.md
scripts/test_agent_gates.py
docs/operations_post_merge_memory.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/**
.agent-loop/merge-intents/WS-ENG-007-00R6.json
```

## Not allowed

```text
workflow, updater, checker, permission, CI, test, or coverage behavior changes
application, API, database, auth, artifact, payment, or product changes
wildcard, persistent, reordered, reusable, or post-signing exemptions
automatic ART, CI, AUTH, ENG, or other successor starts
reinterpretation of PR #197 as implementation authority
```

## Acceptance criteria

- [ ] Schema-v5 recovery binds signed basis `bba4ba5f…` and names only PR #197 /
      `WS-ART-001-PLAN2` / `03a05eeb…` as the recovered predecessor.
- [ ] Activation names only `WS-ENG-007-00R6`; the target identity comes from
      trusted GitHub merge evidence and must be direct-next on first-parent main.
- [ ] Both merges carry successful merge-bound `agent-gates` and `test`
      provenance; mutable reruns and CodeRabbit are not recovery authority.
- [ ] Both temporary exemptions are consumed before signing and cannot persist,
      replay, reorder, broaden, or authorize a third merge.
- [ ] ART PLAN2 reconciles to stopped state with `WS-ART-001-03A` requiring an
      explicit start; recovery starts no implementation or planning chunk.
- [ ] Exactly one merge intent stops ENG-007 at its existing `01` gate.

## Verification commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py docs/operations_post_merge_memory.md .agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation
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

Confirm the certificate is exact, first-parent adjacent, merge-evidence-bound,
fully consumed, and incapable of starting ART PLAN2 successors or unrelated
work.

## Stop conditions

Stop if recovery requires an intervening merge, wildcard authority, missing
protected checks, persisted exemption, automatic successor start, or changes
outside the allowed files.
