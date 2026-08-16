# Chunk Map: WS-CI-004 Review Evidence Integrity

| Chunk | Goal | Risk | State |
|---|---|---:|---|
| `WS-CI-004-PLAN` | First-principles discovery, threat model, design, and bounded delivery contracts | L1 | Planned; no implementation behavior |
| `WS-CI-004-01` | Shared Reviewer Evidence Protocol and deterministic review-target command, reusing `scripts/git_delta.py` | L1 | Complete through PR #341 |
| `WS-CI-004-02` | Adopt the shared protocol across all nine reviewer agents and matching skills, with the shared evaluation harness | L1 | Complete through PR #342 |
| `WS-CI-004-03` | Close final-head approval and durable merged-state gaps exposed by PR #340 | L1 | Complete |
| `WS-CI-004-04` | Require explicit impact-cone and adversarial proof in exact-head reviews | L1 | Complete |

This is sequencing guidance, not an implementation queue. Create one bounded
contract only when a human explicitly starts that step. One implementation
contract equals one pull request, and there is no automatic successor.
