# STATUS: WS-ENG-001

## Current

- `WS-ENG-001-01`: merged through PR #23 on 2026-06-20; complete
- `WS-ENG-001-02`: merged through PR #122 as `fc89fb6`; complete
- `WS-ENG-001-03`: corrective schema-v2 contract for initiative-local next gates
- Current gate: canonical completion is recorded only by signed post-merge state
- Product runtime: unchanged

## Last Update

The first live generated state proved signing, protected-main freshness, and
workflow isolation, but exposed that schema v1 allowed `WS-ENG-001-02` to name
`WS-AUTH-001-06` as a global next chunk. The corrective chunk makes successor
authority initiative-local, rejects schema v1 without compatibility, and
rebootstraps generated state at schema v2. No artifact, authorization, or other
Workstream product runtime is active in this engineering chunk.

## Next Required Event

Do not select a product chunk from this authored file. Read verified signed
post-merge state, then require a separate explicit user start.
