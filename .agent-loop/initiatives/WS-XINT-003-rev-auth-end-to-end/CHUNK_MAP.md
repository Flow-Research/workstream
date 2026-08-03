# Chunk Map: WS-XINT-003 REV-AUTH End-to-End Contract

| Chunk | Purpose | Risk | Dependency |
|---|---|---|---|
| `WS-XINT-003-01` | Reconcile policy ownership, complete REV catalogue, permissions, surfaces, resource families, and fixed-service matrix while actions stay planned. | L1 | approved plan |
| `WS-XINT-003-02A` | Cut policy persistence and Task/Submission/Checker locks from guide-version aliases to immutable policy-version identity; activate nothing. | L1 | 01 plus refreshed REV-03P/AUTH-12D2 |
| `WS-XINT-003-02B` | Activate the sole review/revision policy mutation service through AUTH PREP after immutable lineage exists. | L1 | merged 02A |
| `WS-XINT-003-02C` | Complete the unavailable REV AUTH catalogue, four missing actions, exact fixed-service identities, static matrices, and database parity once; activate nothing. | L1 | merged 02B |
| `WS-XINT-003-02D` | Publish the complete fail-closed REV PREP integration contract and typed action/resource manifest for REV to implement against; activate nothing and implement no REV lifecycle behavior. | L1 | merged 02C |
| `WS-XINT-003-03A` | Activate only concealed `review.queue.read`; queue visibility grants no claim, packet, artifact, or decision authority. | L1 | 02D plus merged REV-05A/05B admission and current-work view |
| `WS-XINT-003-03B` | Activate only `review.claim` with exact grant, self-review denial, global lease limit, policy freeze, and packet-manifest binding. | L1 | 03A plus merged REV-03B/06A, CON-06, and exact ART packet proof |
| `WS-XINT-003-03C` | Activate only owning-reviewer `review.release` and offered-reviewer `review.decline_preference`. | L1 | 03B plus merged REV-06B |
| `WS-XINT-003-03D` | Activate preference and lease expiry fixed services only. | L1 | 03C plus merged REV-06C and exact fixed-service admission |
| `WS-XINT-003-04` | Activate lease-bounded `review.context.read` and `review.chain.read` while consuming XINT-002-07A packet materialization; no evidence upload. | L1 | 03D plus merged REV-07A and XINT-002-07A |
| `WS-XINT-003-05` | Historical separate chain-read placeholder folded into 04 because both consume the same REV-07A lease/context boundary. | L1 | superseded |
| `WS-XINT-003-06` | Activate `review.decision` only for the first hidden canonical Review/FinalAcceptance/CON atomic composition. | L1 | 04 plus merged REV-10, CON-03C/07, audit and outbox proof |
| `WS-XINT-003-07` | Extend already-owned XINT-002 preparation/Submission actions with the closed human-review revision context; no response-artifact upload. | L1 | 06 plus merged REV-09A1-09B and XINT-002-05D |
| `WS-XINT-003-08R` | Historical registration placeholder superseded by front-loaded 02C. Never execute independently. | L1 | superseded |
| `WS-XINT-003-08A` | Activate recovery commands only in current-main children aligned to exact merged REV-11A-D behavior; do not bundle unrelated principals or commands. | L1 | 02C/02D plus exact REV-11A-D child |
| `WS-XINT-003-08B` | Activate service reconciliation, artifact-reference, projection, and lifecycle-control actions only in current-main children aligned to exact REV-11C/12P2/12A4 behavior. | L1 | 08A plus exact matching REV child and external owner proof |
| `WS-XINT-003-09` | Prove end-to-end least privilege, revocation, replay, concurrency, atomicity, artifact isolation, and activation fences; REV-13C alone releases product routes. | L1 | 02A-08B plus REV-13A/B |

Future chunks are planning skeletons, not implementation-ready contracts until
refreshed on current main with exact allowed files and commands. Each row
maps to one PR unless its current-main contract is split into smaller
children before implementation. A split cannot add a new permission, action,
principal class, service identity, or authorization protocol without returning
to planning.

After 02D merges, REV may implement its full lifecycle without waiting for an
action to become active. Later activation chunks wait for REV evidence; they do
not own or implement REV lifecycle behavior.

No reviewer, contributor, Project Manager recovery, Operator, or service route
is product-exposed by an AUTH activation. Earlier actions support hidden
integrated proof behind the REV lifecycle fence; `WS-REV-001-13C` is the sole
product-router release.
