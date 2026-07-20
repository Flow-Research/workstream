# WS-ENG-001-04B External Review Response

PR: https://github.com/Flow-Research/workstream/pull/165

## Comments addressed

- CodeRabbit minor: recovery guidance now limits `loop-memory-replay` to merge
  workflow failures; failed explicit events require a fresh protected dispatch.
- CodeRabbit nitpick, elevated by internal security review: cutover is explicit,
  resolves the policy from the exact immutable cutover merge, fails closed on a
  missing or invalid historical blob, and cannot use mutable current-main bytes.
- Workflow regression tests require the exact repository-root and literal 04B
  cutover arguments in the production update command and reject interpolation.

## Comments deferred

None.

## Human decisions needed

The user retains merge authority for PR #165. No architecture, product, or
security exception is requested.

## Commands rerun

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_agent_gates.py` — 134 passed.
- `python3 -m ruff check scripts/update_post_merge_memory.py scripts/test_update_post_merge_memory.py scripts/test_agent_gates.py` — passed.
- Markdown links, stale wording, internal review evidence, merge intent, and diff
  integrity — passed before publication; final evidence-only head is rechecked.
- All nine internal reviewer tracks — pass at `da9b2291`.

## Remaining risks

Backend shard duration remains imbalanced (12m48s, 3m02s, 3m07s, 8m34s) and is
follow-up CI-efficiency work, not a correctness exception for this chunk.
