# Chunk Map: WS-REV-001 Review And Revision Lifecycle

## Rule

One executable chunk maps to one PR. Merged parent IDs remain non-executable
split records. A proposed child is not executable until its own current-main
contract is authored, internally reviewed, explicitly started, and every owner
gate is proven by exact chunk ID, merged PR/SHA, migration head where relevant,
typed symbol/manifest, and tests.

## Current sequence

| Chunk | Title | Risk | Gate | Status |
|---|---|---:|---|---|
| `WS-REV-001-PLAN` | Review And Revision Lifecycle Planning | L1 | None | Merged PR #128 |
| `WS-REV-001-01` | Canonical Contract Adoption And Dependency Conformance | L1 | PLAN | Merged PR #145 |
| `WS-REV-001-02` | Locked Review Policy And Task Lifecycle Alignment | L1 | 01 | Merged PR #147; non-executable split record |
| `WS-REV-001-PLAN2` | REV-02A Runtime Readiness Plan Refresh | L1 | 02; planning-only human start | Active planning/specification chunk; no runtime |
| `WS-REV-001-02A` | Project Guide Activation Sequence And Publication Locking | L1 | Exact merged AUTH contributor foundation; refreshed SHA/head; separate human start | Runtime blocked |
| `WS-REV-001-02B` | Locked Review Policy And Dormant Task Lifecycle Compatibility | L1 | 02A; approved duration defaults; separate start | Proposed |
| `WS-REV-001-02C` | Submission Attribution, Context, And Immutable Lineage | L1 | 02B; merged AUTH canonical contributor constraints; separate start | Proposed |
| `WS-REV-001-03` | Review Queue And Lease Persistence | L1 | 02C | Non-executable split record |
| `WS-REV-001-03A` | Queue And Lease Base Persistence | L1 | 02C; merged `WS-CON-001-03B`; contract review | Proposed; no contract yet |
| `WS-REV-001-03B` | Normalized Review Packet Manifest Persistence | L1 | 03A; exact ART packet-membership owner chunk merged | Proposed; owner chunk unscheduled |
| `WS-REV-001-04` | Review Chain Persistence | L1 | 03B | Non-executable split record |
| `WS-REV-001-04A` | Immutable Review Chain And Decision Request Persistence | L1 | 03B; current actor constraints | Proposed; no contract yet |
| `WS-REV-001-04B` | Final Acceptance, Task Linkage, Audit, And Outbox Persistence | L1 | 04A; merged `WS-CON-001-02A` and `02C` | Proposed; no contract yet |
| `WS-REV-001-05` | Checker Routing And Queue Views | L1 | 04B | Non-executable split record |
| `WS-REV-001-05A` | Atomic Checker Admission Participant | L1 | 04B; merged ART 05/06A/06B exact admission facts | Proposed; no contract yet |
| `WS-REV-001-05B` | Server-Selected Reviewer And Admin Queue Reads | L1 | 05A; exact AUTH read contracts | Proposed; no contract yet |
| `WS-REV-001-06` | Claims, Preference, And Timers | L1 | 05B | Non-executable split record |
| `WS-REV-001-06A` | Atomic Claim, Lease, Packet, And Reviewer Policy Freeze | L1 | 05B; merged 03B persistence contract; merged `WS-CON-001-06`; AUTH PREP/custody/service contracts | Proposed; consumes 03B and owns no packet schema/migration |
| `WS-REV-001-06B` | Owned Release, Decline, And Preference Transitions | L1 | 06A; exact AUTH mutation contracts | Proposed; no contract yet |
| `WS-REV-001-06C` | Preference And Lease Expiry With Lazy Recovery | L1 | 06B; provisioned/admitted exact service identities | Proposed; no contract yet |
| `WS-REV-001-07` | Review Context And Finding Evidence | L1 | 06C | Non-executable split record |
| `WS-REV-001-07A` | Lease-Bounded Packet And Review Chain Context | L1 | 06C; exact ART packet-read owner chunk | Proposed; owner chunk unscheduled |
| `WS-REV-001-07B` | Reviewer Finding Evidence Candidate And Finalize | L1 | 07A; exact ART review-evidence owner chunk and AUTH binding contracts | Proposed; owner chunk unscheduled |
| `WS-REV-001-08` | Pure Decision, Final Acceptance, And Task-Effect Contract | L1 | 07B; typed participant contracts | Proposed; executable contract after repair, no canonical write |
| `WS-REV-001-02A2` | Prepared Superseded Guide Reactivation | L1 | 08; merged AUTH-PREP/custody; AUTH-12 contract amendment; `project.guide.activate` remains unavailable | Proposed hidden behavior; manifest gates AUTH-12 evaluator/cutover/activation |
| `WS-REV-001-09A` | Revision Context Preparation And Resubmission | L1 | 08 | Non-executable split record |
| `WS-REV-001-09A1` | Review-Rooted Revision Preparation Persistence | L1 | 02A2; approved human round/deadline semantics; migration/head refresh | Proposed; no contract yet |
| `WS-REV-001-09A2` | Revision Preparation Participant, Resolver, And Task Context | L1 | 09A1 | Proposed; task-owned flush-only participant, no transaction composition |
| `WS-REV-001-09A3` | Human Revision Response Evidence Finalize | L1 | 09A2; ART evidence port and exact AUTH action | Proposed; owner chunk unscheduled |
| `WS-REV-001-09A4` | Hidden Human Prepared N+1 And Checker Source Compatibility | L1 | 09A3; merged AUTH-14 contract amendment only; ART digest contract | Proposed; adds preparation binding/source XOR while retaining 02C checker source; AUTH-14 owns public request acknowledgement, authorization cutover, and activation |
| `WS-REV-001-09A5` | Hidden Replacement Assignment Preparation Transfer | L1 | 09A4; merged AUTH-13 contract amendment only | Proposed; AUTH-13 later owns public command/cutover/activation |
| `WS-REV-001-09B` | Finding Replay, Resolution, And Preferred Return Routing | L1 | 09A5 | Proposed |
| `WS-REV-001-10` | Canonical Review, Final Acceptance, And CON Atomic Integration | L1 | 09B; merged `WS-CON-001-03C` and `07`; stabilized digest owner chunk | Proposed; first canonical decision commit |
| `WS-REV-001-11` | Administrative Recovery And Reconciliation | L1 | 10 | Non-executable split record |
| `WS-REV-001-11A` | Privileged Queue And Lease Commands | L1 | 10; exact AUTH command contracts | Proposed; no contract yet |
| `WS-REV-001-11B` | Revision Repair And Obligation Closure | L1 | 11A; registered additive actions | Proposed; no contract yet |
| `WS-REV-001-11C` | Reconciliation Persistence, Historical Admission Scan, And Service Jobs | L1 | 11B; exact service identities/admission | Proposed; owns batched resumable audited scan/classification |
| `WS-REV-001-11D` | Legacy Closure And ART Recovery Delegation | L1 | 11C; ART Operator recovery port | Proposed; no contract yet |
| `WS-REV-001-12` | Projection And Observability | L1 | 11D | Non-executable split record |
| `WS-REV-001-12P1` | Deterministic Review Projection Handler | L1 | 11D; merged CON outbox dispatcher/handler registry | Proposed; no contract yet |
| `WS-REV-001-12P2` | Artifact Reference Reconciliation And Projection Rebuild Jobs | L1 | 12P1; exact services/actions/ART projection port | Proposed; no contract yet |
| `WS-REV-001-12P3` | Notifications, Admin Reads, Metrics, And Drain Observation | L1 | 12P2 | Proposed; no contract yet |
| `WS-REV-001-12A` | Joint Lifecycle Release Control | L1 | 12P3 | Non-executable split record; preserves canonical parent ID |
| `WS-REV-001-12A1` | Lifecycle Controller Persistence And Typed Ports | L1 | 12P3; exact core CON readiness manifest | Proposed; no contract yet |
| `WS-REV-001-12A2` | REV, Task, And Checker Mutation Fence Composition | L1 | 12A1 | Proposed; no contract yet |
| `WS-REV-001-12A3` | CON Writer, Dispatcher, Callback, Cutoff, And Drain Fences | L1 | 12A2; CON 03D/08A/08B/10B/11 hooks | Proposed; no contract yet |
| `WS-REV-001-12A4` | Operator Transition, Drain, And Crash Recovery | L1 | 12A3; exact AUTH Operator contract | Proposed; no contract yet |
| `WS-REV-001-13` | Coherent Product Release And Proof | L1 | 12A4 | Non-executable split record |
| `WS-REV-001-13A` | Exact Dependency Preflight, Manifests, And Drill Harness | L1 | 12A4; every owner gate exact and merged | Proposed; no contract yet |
| `WS-REV-001-13B` | Pre-Release Documentation And Generated Artifact Preparation | L1 | 13A; hidden behavior proof | Proposed; no contract yet |
| `WS-REV-001-13C` | Product Router Registration And Final HTTP Proof | L1 | 13B; exact AUTH activations; ART 07; CON 11 | Proposed; sole product release |

## Same-initiative order

```text
PLAN -> 01 -> 02(parent) -> PLAN2 -> 02A -> 02B -> 02C
-> 03(parent) -> 03A -> 03B
-> 04(parent) -> 04A -> 04B
-> 05(parent) -> 05A -> 05B
-> 06(parent) -> 06A -> 06B -> 06C
-> 07(parent) -> 07A -> 07B
-> 08 -> 02A2
-> 09A(parent) -> 09A1 -> 09A2 -> 09A3 -> 09A4 -> 09A5 -> 09B
-> 10
-> 11(parent) -> 11A -> 11B -> 11C -> 11D
-> 12(parent) -> 12P1 -> 12P2 -> 12P3
-> 12A(parent) -> 12A1 -> 12A2 -> 12A3 -> 12A4
-> 13(parent) -> 13A -> 13B -> 13C
```

Non-executable parents do not consume a PR after this planning refresh. Their
first child is the successor of the preceding executable chunk.

## Owner-gate rule

Phrases such as "AUTH contributor foundation", "ART owner amendment", or
"CON participant" describe required ownership but are not executable gates.
Before a child starts, replace each phrase in its new contract with:

```text
owner chunk ID + merged PR + merge SHA + migration head (if schema)
+ typed symbol/manifest + exact focused and regression test evidence
```

Known merged/planned CON IDs may be named, but proposed status remains blocked.
The contributor clean cut and ART packet-read/review-evidence/digest work do not
yet have trusted-main owner chunk IDs. REV neither invents those IDs nor edits
owner plans.

## Parent split records

Existing parent contract files for 03, 04, 05, 06, 07, 09A, 11, 12, former
12A release control, and 13 are non-executable historical planning records.
They must not be used as implementation authorization. New child contracts are
authored only from the then-current main when each child receives a human start.

## Reviewers

Every executable chunk requires senior engineering, QA/test, security/auth, and
product/ops. Architecture and reuse/dedup apply throughout. Schema/routes/jobs/
active behavior add docs and test-delta. Workflows, scripts, dependencies, test
configuration, or coverage changes add CI integrity.

## Stop condition

Complete and merge only `WS-REV-001-PLAN2`, then stop. Its schema-v2 merge
intent names `WS-REV-001-02A` and requires a separate explicit start after the
exact AUTH runtime foundation merges. Do not begin 02A or any later child from
this planning PR.
