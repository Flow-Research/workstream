# Chunk Contract: WS-ENG-007-00R3 — Merge-Bound Evidence Recovery

## Parent initiative

`WS-ENG-007` — Concurrent PR Review Reconciliation

## Goal

Restore signed reconciliation and explicit starts without allowing mutable
post-merge check reruns to rewrite the evidence accepted for an already merged
PR.

## Why this chunk exists

PRs #187–#189 are on protected `main`, but signed memory remains at PR #178.
The recovery path re-queries mutable check history, rejects later rerun shapes,
and exists only in the merge workflow. PR #189 also merged without completed
pre-merge `agent-gates` evidence. Consequently an ordinary explicit start cannot
reconcile the same trusted history and unrelated ENG-006 work is blocked.

## Risk class

L1 / P0 reliability repair.

## Start phase

Recovery implementation. This contract records the exact fail-closed repair
needed to restore the signed start mechanism that is itself unavailable.

## Allowed files

```text
.github/workflows/loop-memory.yml
.github/workflows/loop-memory-start.yml
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_update_post_merge_memory.py
scripts/test_check_loop_memory_state.py
scripts/test_agent_gates.py
docs/operations_post_merge_memory.md
.agent-loop/policies/loop-memory-recovery.json
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/**
.agent-loop/merge-intents/WS-ENG-007-00R3.json
```

## Not allowed

```text
application, API, database, product, auth, payment, or coverage changes
repository permissions, secrets, branch protection, or cancel authority changes
weakening required checks, signed starts, internal review, or human merge approval
any wildcard, reusable, reorderable, or persistent recovery exception
automatic successor starts
```

## Acceptance criteria

- [ ] For each protected name, classify every candidate against immutable
      `merged_at`; ignore only candidates started after the merge. Select the
      latest candidate started no later than the merge by normalized RFC3339
      instant and positive unique ID, and require it to have completed
      successfully no later than the merge. An older success cannot hide a
      newer eligible failure or incomplete run.
- [ ] Malformed timestamps or identities that prevent trustworthy boundary
      classification, incomplete pagination, forged app, wrong head, duplicate
      ID, non-successful selected evidence, and ambiguity fail closed.
- [ ] Check retrieval is completely paginated with deterministic deduplication,
      explicit page/item bounds, and rejection of total drift, overlap, or bound
      exhaustion. More than 100 later reruns cannot hide eligible evidence.
- [ ] Signed merge records persist selected run ID, protected name, head SHA,
      pinned app, normalized start/completion instants, conclusion, merge cutoff,
      and a canonical evidence digest; the independent checker validates them.
- [ ] CodeRabbit remains supplementary external evidence and is not converted
      into signed start or merge authority.
- [ ] Merge reconciliation and explicit-start reconciliation use one shared,
      deterministic recovery sequence and consume the recovery inventory before
      signing or publishing.
- [ ] A schema-v4 closed recovery certificate binds signed basis
      `73b457925b02301587b83d01ced0adb66319d134`, exact PR #187 / `PLAN` /
      `8928ba80…`, PR #188 / `00R1` / `c65633f8…`, PR #189 / `00R2` /
      `d3321698…`, and direct-next activation `00R3`. It requires exact adjacent
      order `[8928ba8…, c65633f…, d332169…, target]` and a four-entry bounded
      ephemeral transport. All entries are consumed before signing and none is
      serialized or reusable.
- [ ] Protected merge-bound evidence is required for PRs #187, #188, and the
      new `00R3` activation PR. Only exact historical PR #189 may carry the
      closed `historical-recovery-only` evidence mode: its exact merge/head/chunk,
      absence reason, and certificate digest are independently validated. That
      mode is impossible for `00R3` or any future merge.
- [ ] Policy v4 has exactly `schema_version`, `signed_basis`, `activation`, and
      three ordered `recovered_merges`; transport v3 has exactly four
      chronological unique identities. Policy/transport v1 and v2 bounds remain
      unchanged. Unknown keys, basis mismatch, collisions, 0–3/5 entries,
      reordering, wrong parents, and legacy-version widening reject.
- [ ] Once history is reconciled, distinct idle initiatives can start
      independently and a later rerun on an older PR cannot block them.
- [ ] Repeated reconciliation and repeated start dispatch remain idempotent or
      fail closed with a stable, actionable error.
- [ ] Both workflows call one shared reconciliation implementation in this
      order: plan, prepare recovery, update every merge with the same inventory,
      assert consumption, then sign/publish or apply the start. Failure publishes
      neither partial state nor authority event.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-007-01` with
      `next_requires_explicit_start: true`; ENG-006 and ENG-007 successors remain
      inactive after recovery.

## Verification commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
git diff --check origin/main...HEAD
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

- Is historical evidence frozen at the merge boundary without accepting a
  failing or untrusted pre-merge run?
- Can the explicit-start path reconcile exactly as safely as the merge path?
- Does this remove the global mutable-history lock without weakening the
  initiative-local signed-start rule?

## Stop conditions

Stop if the repair requires weakening protected checks, adding a new historical
PR exemption, changing GitHub authority, or allowing unsigned implementation.
