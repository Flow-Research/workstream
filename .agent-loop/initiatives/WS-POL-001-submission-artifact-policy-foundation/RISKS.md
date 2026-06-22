# Risks: WS-POL-001 - Submission Artifact Policy Foundation

| Risk | Impact | Mitigation |
|---|---|---|
| Big-bang lifecycle rewrite | High | Split policy, generation, submission runtime, post-submit split, and revision proof into separate chunks. |
| Default policy can be weakened | High | Validate effective policy rejects any project policy that removes or downgrades defaults. |
| Naming drift | High | Human review field names before migrations. |
| Worker-facing internal route leakage | Medium | Keep `task_setup_blocked` and `checker_retry` internal; expose `needs_revision` only when worker action is needed. |
| Backward compatibility drift | Medium | Keep transitional fields explicit until replacement is proven. |
| Insufficient real API proof | High | Require Postgres-backed API tests and real API drill before closing the initiative. |
