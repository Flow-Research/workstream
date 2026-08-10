# Chunk Map: WS-XINT-002 ART-AUTH End-to-End Contract

| Chunk | Purpose | Risk | Dependency/status |
|---|---|---|---|
| `01` | Reconcile ART catalogue, permissions, owners, migration parity, and fixed matrix. | L1 | Merged |
| `02` | Close reusable opaque PREP-to-ART operation interface. | L1 | Merged |
| `03` | Activate verifier, scheduler scan, and put resolver. | L1 | Merged |
| `04A` | Activate Project Manager guide ingest. | L1 | Merged/active |
| `04B` | Activate fixed-service guide binding and read. | L1 | Merged/active in PR #245 (`6babf81b`) |
| `06A` | Activate only pre-submit checker-input materialization. | L1 | Merged through PR #293; precedes ART-04C1 and 05A |
| `05A` | Activate initial contributor preparation only over hidden ART ready-admission behavior. | L1 | Non-executable pending WS-ARCH-001-02 split public-API contract |
| `05B` | Activate TASK-owned Submission creation with ART-owned binding/consumption. | L1 | Non-executable pending WS-ARCH-001-02 split public-API contracts |
| `05C` | Activate checker-remediation submission context. | L1 | Non-executable pending 05B plus WS-ARCH-001 checker capability contract |
| `05D` | Activate human-review revision context. | L1 | Non-executable pending 05B plus WS-ARCH-001 review capability contract |
| `06B` | Activate post-submit materialization and checker output write/binding. | L1 | Non-executable pending POL/ART evidence plus WS-ARCH-001 checker capability contract |
| `07A` | Activate lease-scoped reviewer packet materialization only. | L1 | Non-executable pending ART/REV evidence plus WS-ARCH-001 review capability contract |
| `07B` | Reserved review-evidence binding gate; keep unavailable absent new approved REV intent. | L1 | Future approved REV evidence-upload contract, if any |
| `08` | Prove complete catalogue, least privilege, revocation, replay, concurrency, audit, and lifecycle conformance. | L1 | Non-executable until all activated waves use public module APIs |

The split 06 ordering is mandatory: contributor preparation cannot activate
while its fixed pre-submit materializer still denies. Review packet authority
does not imply reviewer evidence upload or generic artifact download.

Each activation chunk owns exact feature resource contexts, session/root-bound
composer proof, lock order, stale-fact matrix, and crossed-race tests. A chunk
cannot add catalogue values, permissions, identities, matrix rows, or another
runtime protocol; that discovery returns to planning.

Every unmerged activation file from 05A onward is coordination evidence only
until its named WS-ARCH replacement contract defines exact public APIs,
ownership-correct internal files, composition wiring, and private-edge removal.
They authorize no implementation in their present form. The superseded 06 and
07 combined records and reserved 07B remain historical/non-executable.
