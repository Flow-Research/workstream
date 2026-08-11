# Chunk Map: WS-POL-002 - Post-Submit Checker Foundation

## Current use

This map records historical outcomes. It is not an active queue. Future work
must use the current WS-POL-003 and checker boundaries.

## Chunks

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-POL-002-01` | Post-Submit Compiler Contract | L1 | Merged |
| `WS-POL-002-02` | Post-Submit Derivation Agent And Resumable Setup Integration | L1 | Merged |
| `WS-POL-002-03` | Server-Owned Policy Approval And Visibility APIs | L1 | Merged through PR #90 as `a7aa474` |
| `WS-POL-002-04` | Locked Runtime Execution And Routing Hardening | L1 | Superseded as written; executor-only replacement requires a fresh current-main contract |
| `WS-POL-002-05` | Unified Post-Submit Live Proof | L1 | Superseded by WS-POL-003 unified compilation and later end-to-end proof |

## Dependency Order

```text
WS-POL-002-01
-> WS-POL-002-02
-> WS-POL-002-03
-> WS-POL-002-04
-> WS-POL-002-05
```

## Remaining boundary

Any remaining executor concern may re-enter only through a new bounded contract
against current `main`; this historical map does not start it.
