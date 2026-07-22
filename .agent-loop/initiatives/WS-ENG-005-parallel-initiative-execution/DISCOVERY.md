# Discovery: Parallel Initiative Execution

## Current behavior

- `apply_authority_event` builds `latest = _latest_by_initiative(records)` and
  rejects a start if any active value exists anywhere.
- `_validate_authority_transition` repeats the global rejection during ledger
  validation, then separately rejects an active basis in the target initiative.
- `check_loop_memory_state.py::_authority_transition_failures` independently
  repeats both rules.
- State rendering already derives all active planning and implementation chunks
  from the latest record for every initiative.
- Merge admission in `apply_merge_record` resolves only the merging initiative's
  active lifecycle, while preserving other initiative records in the ledger.
- Cancellation already binds the requested chunk to its initiative basis.

## Relevant files and symbols

- `scripts/update_post_merge_memory.py`
  - `_latest_by_initiative`
  - `_validate_authority_transition`
  - `apply_authority_event`
  - `apply_merge_record`
  - `render_state`, `render_work_queue`, `render_initiative_state`
- `scripts/check_loop_memory_state.py`
  - `_authority_transition_failures`
  - generated projections and manifest validation
- `scripts/test_update_post_merge_memory.py`
- `scripts/test_check_loop_memory_state.py`
- `scripts/test_agent_gates.py`
- `.github/workflows/loop-memory-start.yml`
- `AGENTS.md`, `.agents/skills/memory-update/SKILL.md`
- `.agent-loop/policies/repository-engineering-policy.md`
- `docs/operations_post_merge_memory.md`

## Existing tests and gaps

Existing tests prove global rejection and must be replaced with cross-initiative
acceptance plus same-initiative rejection. Gaps include two concurrent active
projections, merge/cancel ordering, queue rendering, stale/replay behavior under
parallel activity, and independent checker parity.

## Dependencies and integrations

The explicit-event workflow serializes publications with the shared
`workstream-loop-memory` concurrency group. GitHub protected `main` serializes
merges. Separate worktrees and isolated databases remain execution concerns,
not signed start authority.

## Risks discovered

- A global active-state check exists in three trust layers; partial removal
  would cause updater/checker disagreement or replay failure.
- The latest global `STATE.json` represents the latest event, while the ledger
  and queue are the source for all initiative activity. Operators must inspect
  the generated queue rather than infer global activity from the tail alone.
- Cross-initiative file overlap is not machine-readable from current contracts.
  Merge conflicts and semantic drift remain review-time risks.
- The old rule blocks a signed start for this repair while AUTH-10A is active.
  A one-target exact self-consuming recovery is required for bootstrap.

## Unknowns resolved

No schema migration, new secret, workflow permission, environment approval, or
worktree registry is needed. Existing per-initiative ledger projections are the
canonical concurrency model.

## Conventions to preserve

Signed automation state is generated only; start dispatches use exact current
main; cancellation remains separately approved; merge intent names only a
same-initiative successor; failed dispatches are inspected before fresh retry.
