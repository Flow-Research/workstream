# Chunk Map

| Chunk | Purpose | Dependency | State |
|---|---|---|---|
| `WS-DB-001-01` | Replace the development migration chain with one exact v0.1 baseline and prove end-to-end parity | Planning approval and frozen source head | Merged PR #317 |

The implementation is intentionally one atomic PR. Splitting deletion from
baseline installation would leave either two schema paths or no installable
schema. Review evidence may be committed in the same PR, but no later product
work begins until the baseline PR merges.
