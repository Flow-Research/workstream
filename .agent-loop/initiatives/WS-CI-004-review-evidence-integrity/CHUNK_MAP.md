# Chunk Map: WS-CI-004 Review Evidence Integrity

| Chunk | Goal | Risk | State |
|---|---|---:|---|
| `WS-CI-004-PLAN` | First-principles discovery, threat model, design, and bounded delivery contracts | L1 | Planned on merge; no implementation behavior |
| Proposed step 1 | Shared Reviewer Evidence Protocol and deterministic review-target command, reusing `scripts/git_delta.py` | L1 | No contract; not active |
| Proposed step 2 | Adopt the shared protocol across all nine reviewer agents and matching skills, with the shared evaluation harness | L1 | No contract; not active |
| Proposed step 3 | Add local exact-target session convergence and orchestration rules | L1 | No contract; not active |

This is sequencing guidance, not an implementation queue. Create one bounded
contract only when a human explicitly starts that step. One implementation
contract equals one pull request, and there is no automatic successor.
