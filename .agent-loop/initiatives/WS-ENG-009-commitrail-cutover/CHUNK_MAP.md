# WS-ENG-009 Chunk Map

| Chunk | Purpose | Durable disposition | Dependency |
|---|---|---|---|
| `WS-ENG-009-01` | Atomically commission Commitrail and remove `.agent-loop` from the working tree | Planned | Human approval of this plan |
| `WS-ENG-009-02` | Run one real Workstream bounded change as a blind Commitrail stress test and record demonstrated method defects | Planned | Atomic Commitrail cutover merged |

One chunk equals one pull request. No additional migration chunk should be
invented unless discovery proves the atomic cutover is not independently
reviewable.
