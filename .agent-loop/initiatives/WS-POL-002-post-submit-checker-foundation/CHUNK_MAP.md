# Chunk Map: WS-POL-002 - Post-Submit Checker Foundation

## Rule

Only one chunk may be active at a time. Do not start the next chunk until the
current chunk is implemented, verified, internally reviewed, externally
reviewed, merged by explicit human approval, and followed by a memory update.

## Chunks

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-POL-002-01` | Post-Submit Compiler Contract | L1 | Merged |
| `WS-POL-002-02` | Post-Submit Derivation Agent And Resumable Setup Integration | L1 | Merged |
| `WS-POL-002-03` | Server-Owned Policy Approval And Visibility APIs | L1 | Merged through PR #90 as `a7aa474` |
| `WS-POL-002-04` | Locked Runtime Execution And Routing Hardening | L1 | Inactive pending auth proof and explicit start |
| `WS-POL-002-05` | Terminal Benchmark Post-Submit Live API Proof | L1 | Proposed |

## Dependency Order

```text
WS-POL-002-01
-> WS-POL-002-02
-> WS-POL-002-03
-> WS-POL-002-04
-> WS-POL-002-05
```

## Stop Condition

After each implementation chunk is reviewed, externally checked, and merged by
explicit human approval, perform the memory update before starting the next
chunk.

`WS-POL-002-03` merged through PR #90 as `a7aa474` on 2026-07-11. Do not start
`WS-POL-002-04` automatically; post-merge memory is complete through PR #94,
but authorization proof and a separate explicit user start are still required.
