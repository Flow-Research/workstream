# Chunk Contract: WS-ENG-007-00R2 — Canonical Check Evidence Recovery

## Goal

Make signed merge reconciliation stable under legitimate GitHub Actions reruns
and reconcile the exact PR #187 → PR #188 → 00R2 backlog once.

## Why this chunk exists

PR #188 fixed recursive tree parity, but run `29984940789` failed because PR
#187 has two successful trusted `agent-gates` check runs. Cardinality is mutable
GitHub history and is not a valid ambiguity signal. Signed state remains at
`73b457925b02301587b83d01ced0adb66319d134`.

## Start phase

`implementation`

## Risk

L1 / P0 policy, audit, CI-evidence, and signed-memory recovery

## Authorization boundary

This otherwise-unstartable repair uses a reviewed exact schema-v3 recovery
certificate. It grants no workflow, repository, secret, merge, or continuing
start authority.

## Allowed files

```text
scripts/update_post_merge_memory.py
scripts/test_update_post_merge_memory.py
scripts/test_agent_gates.py
scripts/test_check_loop_memory_state.py
.agent-loop/policies/loop-memory-recovery.json
docs/operations_post_merge_memory.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/CHUNK_MAP.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/STATUS.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/RISKS.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/DECISIONS.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/chunks/WS-ENG-007-00R2-canonical-check-recovery.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-00R2-internal-review-evidence.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-00R2-pr-trust-bundle.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-00R2-external-review-response.md
.agent-loop/merge-intents/WS-ENG-007-00R2.json
```

## Not allowed

- Workflow, required-check name, branch-protection, coverage, dependency,
  signing-key, secret, permission, product, backend, or frontend changes.
- Treating CodeRabbit status as implementation-start authority.
- Accepting a foreign app, wrong head, incomplete or malformed check run.
- Letting an older success override a later failure.
- Persistent, wildcard, reorderable, cross-repository, or reusable recovery.
- Starting `WS-ENG-007-01` or `WS-ENG-006-01` in this chunk.

## Acceptance criteria

- [ ] Every same-name candidate is validated before selection. Any poisoned
      candidate fails whether older or newer than a valid success and under
      every input permutation. Completed trusted candidates are ordered by
      parsed `started_at` instant then positive check-run ID; the unique latest
      invocation determines success. Completion order never defines recency.
- [ ] Zero matches, incomplete API response, foreign app, wrong head, missing or
      malformed ID/timestamps, any non-completed run, non-success latest
      conclusion, or a canonical identity collision fails closed. Timestamp
      parsing is timezone-aware RFC3339 normalized to instants; naive/non-string
      values fail. IDs require `type(id) is int` and `id > 0`; booleans,
      byte-identical duplicate IDs, and conflicting ID reuse fail.
- [ ] Tests cover one success, two successes, failure→success, success→failure,
      an older-started success completing after a newer-started failure,
      queued/in-progress evidence, cancelled/timed_out/skipped conclusions,
      foreign app with the protected name, wrong head, offset-equivalent and
      identical timestamps resolved by ID, duplicate ID rejection, malformed
      timestamps, API truncation, and evidence order permutation. Poisoned
      candidates appear both older and newer than a valid success. Later failure
      is tested independently for `agent-gates` and `test`.
- [ ] The real PR #187 shape—two successful trusted `agent-gates` plus one
      successful trusted `test`—passes deterministically and is permutation
      invariant.
- [ ] Schema v3 permits only `schema_version`, ordered `recovered_merges`, and
      `activation`; the list contains one or two entries, is identity-unique and SHA-unique,
      and every entry binds initiative, chunk, positive PR number, and merge SHA.
      Tests reject unknown/missing keys at every level, empty/three-entry lists,
      duplicate identity or SHA under changed counterparts, bool/invalid PR,
      malformed SHA, activation collision, and policy/Git order mismatch.
- [ ] Production policy binds exactly PR #187 merge
      `8928ba80eeaf31e609dbdeda7d2cc22e9ea482c8` / `WS-ENG-007-PLAN`, then PR #188
      merge `c65633f8f0991dbefe7b0635e053aab0df8f9af8` /
      `WS-ENG-007-00R1`, then activation `WS-ENG-007-00R2`.
- [ ] Recovery requires the exact adjacent first-parent plan
      `[8928ba80…, c65633f8…, target]`, validates every recovered identity and
      required-check aggregate, validates exact protected-check provenance on
      every recovered and target reviewed head, consumes all three exemptions
      before signing, serializes none,
      and rejects missing, extra, reordered, repeated, intervening, wrong-parent,
      wrong-identity, check-failure, partial-consumption, and replay cases.
- [ ] Applying the exact authenticated plan to two fresh copies of the same
      starting state produces byte-identical complete generated closed trees,
      including signing input. Replay from completed state proves no exemption
      reinjection and no publication change.
- [ ] Final state records 00R2 stopped with `WS-ENG-007-01` as explicit-start
      successor; both `WS-ENG-007-01` and `WS-ENG-006-01` remain inactive.
- [ ] Existing tree, planning grammar, merge attribution, lifecycle, signing,
      checker, and recovery regression suites remain blocking and unchanged in
      authority semantics.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-007-01` as the same-
      initiative explicit-start successor.

## Verification commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_agent_gates.py scripts/test_check_loop_memory_state.py
python3 scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
PR_HEAD_SHA="$(git rev-parse HEAD)" python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
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

Confirm latest-run semantics match GitHub rerun behavior, later failures cannot
be hidden, and schema-v3 authority is exact, ordered, consumed, and non-reusable.

## Stop condition

Stop after this PR. Do not start either successor until the user merges this
specific PR and signed automation proves the exact recovered state.
