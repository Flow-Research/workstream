# Chunk Map: WS-QUAL-002 Behavior Ownership Catalogue

| Chunk | Purpose | Dependency | Risk | State |
|---|---|---|---|---|
| `WS-QUAL-002-01` | Catalogue schema, inventory, generator, validation foundation | none | L1 | proposed |
| `WS-QUAL-002-02` | Coverage-context candidate evidence and runtime calibration | 01 | L1 | pending |
| `WS-QUAL-002-03A` | AUTH, actors, API controls, audit ownership | 01, 02 | L1 | pending |
| `WS-QUAL-002-03B` | Artifacts, storage, extraction, external adapters ownership | 01, 02 | L1 | pending |
| `WS-QUAL-002-03C` | Projects, tasks, checkers, reviews, contribution ownership | 01, 02 | L1 | pending |
| `WS-QUAL-002-03D` | Core, DB, async execution, scripts, remaining shared ownership | 01, 02 | L1 | pending |
| `WS-QUAL-002-04` | Completeness/staleness gate and contributor preparation command | 03A-D | L1 | pending |
| `WS-QUAL-002-05` | Catalogue-first mutation cutover and AUTH workflow proof | 04 | L1 | pending |

Population chunks `03A` through `03D` may run concurrently in separate
branches after `01` and `02` merge. Their scopes come exclusively from the
machine-readable target partition committed by `01`; each target belongs to
exactly one population chunk.
