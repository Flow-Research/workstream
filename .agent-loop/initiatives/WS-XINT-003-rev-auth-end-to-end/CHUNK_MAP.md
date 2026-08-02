# Chunk Map: WS-XINT-003 REV-AUTH End-to-End Contract

| Chunk | Purpose | Risk | Dependency |
|---|---|---|---|
| `WS-XINT-003-01` | Reconcile policy ownership, complete REV catalogue, permissions, surfaces, resource families, and fixed-service matrix while actions stay planned. | L1 | approved plan |
| `WS-XINT-003-02A` | Cut policy persistence and Task/Submission/Checker locks from guide-version aliases to immutable policy-version identity; activate nothing. | L1 | 01 plus refreshed REV-03P/AUTH-12D2 |
| `WS-XINT-003-02B` | Activate the sole review/revision policy mutation service through AUTH PREP after immutable lineage exists. | L1 | merged 02A |
| `WS-XINT-003-03A` | Activate concealed reviewer current-work plus claim/release/preference with exact project grant, self-review denial, global lease limit, and atomic lease/packet-manifest freeze. | L1 | 02B plus hidden REV queue/lease behavior |
| `WS-XINT-003-03B` | Activate preference and lease expiry fixed services only. | L1 | 03A plus hidden timer behavior |
| `WS-XINT-003-04` | Activate human `review.context.read` and reviewer finding evidence while consuming XINT-002-07A's ART-only packet/materialization/binding capability. | L1 | 03B plus hidden REV packet/evidence manifests and XINT-002-07A |
| `WS-XINT-003-05` | Activate only bounded `review.chain.read`, consuming the active REV context and XINT-002 packet/materialization boundary. | L1 | 04 plus merged XINT-002-07A |
| `WS-XINT-003-06` | Activate `review.decision` only for the hidden atomic Review/FinalAcceptance/CON composition. | L1 | 05 plus REV decision and merged CON participant |
| `WS-XINT-003-07` | Activate human contributor response evidence, consuming XINT-002-05D shared revision submission and the already-merged XINT-002-07B ART response evaluator. | L1 | 06 plus hidden REV revision behavior, XINT-002-05D, and merged XINT-002-07B |
| `WS-XINT-003-08R` | Register four missing privileged recovery/lifecycle ActionIds as planned with complete catalogue/migration parity; activate nothing. | L1 | 07 plus exact hidden-feature registration manifests |
| `WS-XINT-003-08A` | Activate Project Manager and Operator queue/revision recovery commands with exact scope and reasons. | L1 | 08R plus hidden REV recovery behavior |
| `WS-XINT-003-08B` | Activate both identities for the single `review.reconcile.run` ActionId together, plus artifact-reference, projection, and lifecycle-control surfaces. | L1 | 08A plus hidden REV jobs/projection/control |
| `WS-XINT-003-09` | Prove end-to-end least privilege, revocation, replay, concurrency, atomicity, artifact isolation, and coherent route release. | L1 | 02A-08B |

Chunks 02A through 09 are planning skeletons, not implementation-ready contracts,
until refreshed on current main with exact allowed files and commands. Each row
maps to one PR unless its current-main contract is split into smaller
children before implementation. A split cannot add a new permission, action,
principal class, service identity, or authorization protocol without returning
to planning.
