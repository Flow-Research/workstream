# Chunk Map

| Chunk | State | Purpose |
|---|---|---|
| `WS-AUTH-003-01` | proposed | Minimal public API, no-new-private-import gate, and no-new-test-structure-debt foundation |
| capability repairs | future, owned by touched feature chunks | Expose and migrate one exact AUTH capability while shrinking the ledger |
| `WS-AUTH-003-CLOSE` | future | Remove remaining untouched legacy violations and require an empty ledger |

The first capability repair is the preserved `WS-POL-003-03A` work after
`WS-AUTH-003-01` merges. Its contract must be amended with its exact AUTH API
surface and ledger delta before implementation resumes.
