# Chunk Map

| Chunk | State | Purpose |
|---|---|---|
| `WS-AUTH-003-01` | Merged PR #305 | Minimal public API, no-new-private-import gate, and no-new-test-structure-debt foundation |
| POL-03A capability repair | Merged PR #307 | First public AUTH consumer proof with no new private edge |
| capability repairs | future, owned by touched feature chunks | Expose and migrate one exact AUTH capability while shrinking the ledger |
| `WS-AUTH-003-CLOSE` | future | Remove remaining untouched legacy violations and require an empty ledger |

POL-03A proved the incremental repair pattern. Every later feature chunk must
name its exact AUTH public surface and ledger delta before implementation.
