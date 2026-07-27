# Chunk Map: WS-XINT-002 ART-AUTH End-to-End Contract

| Chunk | Purpose | Risk | Dependency |
|---|---|---|---|
| `WS-XINT-002-01` | Reconcile the entire ART catalogue, permissions, owners, migration parity, and fixed-service matrix while every new action stays planned. | L1 | approved plan |
| `WS-XINT-002-02` | Close the reusable PREP-to-ART operation interface: opaque prepared authority on durable mutation requests, no obsolete upload-session port, and no action activation. | L1 | 01 |
| `WS-XINT-002-03` | Activate verifier, scheduler scan, and put resolver services from merged ART recovery evidence. | L1 | 02 plus ART 02C/02D evidence |
| `WS-XINT-002-04` | Activate guide ingest, guide binding, and guide read in evidence-ordered substeps. | L1 | 02 plus ART 03A/03B evidence |
| `WS-XINT-002-05A` | Activate initial contributor bundle preparation and durable ready admission. | L1 | 02 plus ART 04A-C evidence |
| `WS-XINT-002-05B` | Activate fresh human Submission creation plus fixed artifact binding with exactly-once admission consumption. | L1 | 05A plus ART 05/TASK evidence |
| `WS-XINT-002-05C` | Activate checker-remediation submission preparation/creation against one final CheckerRun. | L1 | 05B plus checker remediation evidence |
| `WS-XINT-002-05D` | Activate human-review revision preparation/creation against exact revision obligations. | L1 | 05B plus REV revision-preparation evidence |
| `WS-XINT-002-06` | Activate pre/post-submit materialization and checker output/binding. | L1 | 02 plus ART 04B/06A/06B evidence |
| `WS-XINT-002-07` | Activate lease-scoped review packets and finding/response evidence binding. | L1 | 02 plus merged ART/REV manifests |
| `WS-XINT-002-08` | Prove complete catalogue, least privilege, revocation, replay, concurrency, audit, and live lifecycle conformance. | L1 | 03-07 including 05A-D |

Chunks 03-07 may be split only by the evidence boundaries named above. A split
cannot add catalogue values, permissions, identities, matrix rows, or a second
runtime protocol; such a discovery is contract drift and returns to planning.
Each activation chunk owns its exact feature resource contexts, non-forgeable
session/root-bound composer proof, lock order, stale-fact matrix, and crossed
race tests. Those facts must not be front-loaded into AUTH before the owning
feature behavior exists.
