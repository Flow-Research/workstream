# Chunk Map: WS-XINT-002 ART-AUTH End-to-End Contract

| Chunk | Purpose | Risk | Dependency/status |
|---|---|---|---|
| `01` | Reconcile ART catalogue, permissions, owners, migration parity, and fixed matrix. | L1 | Merged |
| `02` | Close reusable opaque PREP-to-ART operation interface. | L1 | Merged |
| `03` | Activate verifier, scheduler scan, and put resolver. | L1 | Merged |
| `04A` | Activate Project Manager guide ingest. | L1 | Merged/active |
| `04B` | Activate fixed-service guide binding and read. | L1 | Merged/active in PR #245 (`6babf81b`) |
| `06A` | Activate only pre-submit checker-input materialization. | L1 | Merged ART-04B3/AUTH-12F2 evidence; must precede ART-04C1 and 05A |
| `05A` | Activate initial contributor preparation and durable ready admission. | L1 | 06A plus ART-04A1-04C2 evidence |
| `05B` | Activate fresh human Submission creation plus fixed binding/consumption. | L1 | 05A plus ART-05A/TASK evidence |
| `05C` | Activate checker-remediation submission context. | L1 | 05B plus checker remediation evidence |
| `05D` | Activate human-review revision context. | L1 | 05B plus REV revision-obligation evidence |
| `06B` | Activate post-submit materialization and checker output write/binding. | L1 | ART-06A/06B evidence |
| `07A` | Activate lease-scoped reviewer packet materialization only. | L1 | ART-07A plus REV lease/packet evidence |
| `07B` | Reserved review-evidence binding gate; keep unavailable absent new approved REV intent. | L1 | Future approved REV evidence-upload contract, if any |
| `08` | Prove complete catalogue, least privilege, revocation, replay, concurrency, audit, and lifecycle conformance. | L1 | All activated v0.1 waves |

The split 06 ordering is mandatory: contributor preparation cannot activate
while its fixed pre-submit materializer still denies. Review packet authority
does not imply reviewer evidence upload or generic artifact download.

Each activation chunk owns exact feature resource contexts, session/root-bound
composer proof, lock order, stale-fact matrix, and crossed-race tests. A chunk
cannot add catalogue values, permissions, identities, matrix rows, or another
runtime protocol; that discovery returns to planning.
