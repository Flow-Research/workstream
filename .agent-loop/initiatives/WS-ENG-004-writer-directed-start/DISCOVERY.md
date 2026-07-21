# Discovery: Writer-Directed Workstream Start

## Current behavior

- `.github/workflows/loop-memory-start.yml` binds events to exact current
  `main`, collects GitHub authority evidence, signs generated output, and uses a
  separate `loop-memory-start` environment only for cancellation.
- `scripts/update_post_merge_memory.py::apply_authority_event` rejects a start
  unless it equals the basis `gate.next_chunk_id`.
- `WS-CI-001` is stopped with `next_chunk_id: null` although the reviewed draft
  contract `WS-CI-001-02-safe-routing-cache-timing.md` exists on trusted main.
- No planning or implementation chunk is active in signed state after PR #168.
- The merge workflow already supports exact, ephemeral, self-consuming recovery
  authorization, but its schema is closed around the historical two-merge
  recovery for PR #166.

## Relevant files

- `.github/workflows/loop-memory-start.yml`
- `.github/workflows/loop-memory.yml`
- `scripts/update_post_merge_memory.py`
- `scripts/check_loop_memory_state.py`
- `scripts/test_update_post_merge_memory.py`
- `scripts/test_check_loop_memory_state.py`
- `scripts/test_agent_gates.py`
- `.agent-loop/policies/loop-memory-start-authorities.json`
- `.agent-loop/policies/loop-memory-recovery.json`
- `docs/operations_post_merge_memory.md`

## Existing tests and gaps

Existing tests cover exact successor start, writer allowlisting, exact-main and
prior-tip binding, approval evidence for cancellation, signed-state rendering,
and historical recovery consumption. They do not cover writer selection of a
unique reviewed contract when the prior successor is null, global active-work
exclusion for cross-initiative selection, or one-merge self-bootstrap recovery.

## Dependencies and integrations

GitHub workflow dispatch, GitHub Actions run/approval APIs, protected `main`, the
generated automation branch, repository signing secret, and pinned Actions.

## Risks

Failing open on contract discovery, confusing chat with signed evidence,
permitting parallel active chunks, recovery persistence, and weakening cancel.

## Unknowns resolved

No new secret or GitHub environment is required. Exact workflow-dispatch
evidence, current GitHub repository permission, and the trusted-main closed
permission policy form the start authority.

## Conventions to preserve

Generated automation state is never hand edited; state is exact-main bound,
signed, independently checked, deterministically rendered, and published only
after complete validation.
