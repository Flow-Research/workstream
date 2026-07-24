# Chunk Map: WS-ENG-008 — Repository-Native SDLC Assurance

| Order | Chunk | Purpose | Risk | Dependency | State |
|---:|---|---|---:|---|---|
| 1 | `WS-ENG-008-01` | Enforce versioned machine-checkable chunk scope | L1 | Planning merge and signed start | Proposed |
| 2 | `WS-ENG-008-02` | Add read-only scheduled signed-state drift audit | L1 | 01 | Proposed |
| 3 | `WS-ENG-008-03` | Add risk-routed adversarial proof records | L1 | 01 | Proposed |
| 4 | `WS-ENG-008-04` | Add bounded loop-memory property invariants | L1 | 01–03 | Proposed |
| 5 | `WS-ENG-008-05` | Add bounded authorization property invariants | L1 | 04 and canonical AUTH reconciliation | Proposed |
| 6 | `WS-ENG-008-06` | Run a non-blocking changed-module mutation pilot | L1 | 01, 04–05, canonical CI/QUALITY reconciliation | Proposed |
| 7 | `WS-ENG-008-07` | Migrate root review history to a lossless indexed archive | L1 | Active root-log writers reconciled | Proposed |

Only `WS-ENG-008-01` is named by the planning merge intent. Every later chunk
must be named by its predecessor's reviewed merge intent and receive a separate
signed start. No chunk starts automatically.

