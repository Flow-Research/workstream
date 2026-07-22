# DISCOVERY: WS-ENG-002

- `.github/workflows/loop-memory-start.yml` applies the `loop-memory-start` environment after GitHub authenticates the dispatcher.
- `scripts/update_post_merge_memory.py::collect_authority_event` fetches both run evidence and environment approvals and requires a different reviewer.
- `scripts/check_loop_memory_state.py` independently enforces the historical two-person event envelope.
- `scripts/test_update_post_merge_memory.py` fixes the two-person approval behavior in unit tests.
- `scripts/test_check_loop_memory_state.py` fixes the environment gate in workflow structure tests.
- `.agent-loop/policies/repository-engineering-policy.md` describes the redundant reviewer as canonical policy.
- The workflow already binds events to first-attempt `workflow_dispatch`, `main`, exact expected SHA, actor, successor, prior signed state, and one serialized state branch.
