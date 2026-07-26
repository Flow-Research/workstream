# External Review Response: WS-ENG-007-00R6

## Comments addressed

- CodeRabbit reported that review evidence should bind `609be24d`. That SHA was
  the obsolete pre-PR-201 recovery revision named by the stale PR description.
  All nine internal tracks reran against final recovery code SHA
  `f3eab24ecac32f959933369c1b5342bc901c7153`; the evidence-only publication
  commit is `1917b6f825e1f96376e939f7bbba4c6f275fa58d`. The PR description is updated
  from the current trust bundle.
- CodeRabbit proposed limiting schema v6 to PR #197 alone. That would be
  incorrect because protected main contains signed AUTH-11 PR #201 immediately
  after PR #197. Recovery cannot skip that first-parent commit. Schema v6
  accepts exactly two recovered records, and the production certificate pins
  them to PR #197 then PR #201. Runtime plan equality, first-parent adjacency,
  merge-bound checks, uniqueness, consumption, replay, reorder, and extra-merge
  tests prevent broader authority.

## Comments deferred

None.

## Human decisions needed

None. Both findings were based on stale PR context rather than a valid code or
policy defect.

## Commands rerun

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py docs/operations_post_merge_memory.md .agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation
python3 scripts/check_stale_workstream_wording.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
git diff --check
```

## Remaining risks

PR #202 must remain the direct-next main merge. Any intervening main merge
invalidates the exact certificate and requires another reviewed reconciliation.
