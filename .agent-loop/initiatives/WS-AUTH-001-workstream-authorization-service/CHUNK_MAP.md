# Chunk Map: WS-AUTH-001 - Workstream Authorization Service

## Rule

Only one chunk may be active at a time. Do not start the next chunk until the
current chunk is implemented, verified, internally reviewed, externally
reviewed, merged by explicit human approval, followed by a memory update, and
stopped.

## Chunks

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-AUTH-001-PLAN` | Authorization Service Planning | L0 | Merged through PR #91 as `ad6d644` |
| `WS-AUTH-001-01` | Adopt Authorization Baseline And Repository Contracts | L1 | Merged through PR #93 as `772af1d` |
| `WS-AUTH-001-02` | Verified Issuer Token And JWKS Boundary | L1 | Merged through PR #107 as `060b780` |
| `WS-AUTH-001-03` | Legacy Actor Classification Preflight | L1 | Merged through PR #109 as `f06532e` |
| `WS-AUTH-001-04` | Request, Error, And API Control Foundation | L1 | Split before implementation into 04A and 04B |
| `WS-AUTH-001-04A` | Request And Error Context | L1 | Merged through PR #111 as `90c9a28` |
| `WS-AUTH-001-04B` | PostgreSQL Rate Controls | L1 | Merged through PR #113 as `05a63c8` |
| `WS-AUTH-001-05` | Authority Evidence And Idempotency Foundation | L1 | Split before implementation into 05A and 05B |
| `WS-AUTH-001-05A` | Shared Audit Ownership And Append-Only Authority Evidence | L1 | Merged through PR #115 as `8e1cde6` |
| `WS-AUTH-001-CAT` | Action And Resource Catalogue Reconciliation | L1 | Merged through PR #117 as `4c5d4fc` |
| `WS-AUTH-001-05B` | Authority Idempotency And Invalidation Foundation | L1 | Merged through PR #119 as `ad71c7e` |
| `WS-AUTH-001-06` | Canonical Actor Profile And Identity Link | L1 | Merged through PR #124 as `f599551` |
| `WS-AUTH-001-07` | Authorization Kernel And Permission Registry | L1 | Split before implementation after required L1 plan review |
| `WS-AUTH-001-07A` | Closed Permission And Action Catalogue | L1 | Merged through PR #126 as `e9d72a1` |
| `WS-AUTH-001-07B` | Deny-By-Default Kernel And Self-Action Cutover | L1 | Merged through PR #130 as `90eca12` |
| `WS-AUTH-001-08` | Bootstrap And Administrative Role Grants | L1 | Merged through PR #131 as `aa0fdcd` |
| `WS-AUTH-001-XINT` | Lifecycle Boundary Plan Reconciliation | L1 | Merged through PR #140 as `d541521` |
| `WS-AUTH-001-09` | Actor State, Identity Revocation, And Service Actors | L1 | Split before runtime implementation |
| `WS-AUTH-001-09A` | Fixed Service Identity Foundation | L1 | Merged through PR #132 as `299363a` |
| `WS-AUTH-001-09B` | Controlled Service Actor Provisioning | L1 | Merged through PR #143 as `053242b` |
| `WS-AUTH-001-09C` | Actor And Identity-Link Administration Reads | L1 | Active after explicit user start from signed 09B memory |
| `WS-AUTH-001-09D` | Actor And Identity-Link Lifecycle Mutations | L1 | Inactive until 09C merge/memory and explicit start |
| `WS-AUTH-001-09E` | Fixed Service Runtime Admission | L1 | Inactive until 09D merge/memory and explicit start |
| `WS-AUTH-001-ART-CUSTODY` | ART Activation Custody Transfer | L1 | Inactive until 09E merge/memory and explicit start |
| `WS-AUTH-001-REV-CUSTODY` | REV Activation Custody Transfer | L1 | Inactive until 09E merge/memory and explicit start |
| `WS-AUTH-001-PREP` | Prepared Mutation Authorization Protocol | L1 | Inactive until 09E merge/memory and explicit start |
| `WS-AUTH-001-10` | Project Qualification And Contributor Role Grants | L1 | Proposed |
| `WS-AUTH-001-11` | Project Identity, Guide, Source, And Visibility Cutover | L1 | Proposed |
| `WS-AUTH-001-12` | Project Policy And Setup Mutation Cutover | L1 | Proposed |
| `WS-AUTH-001-13` | Task Management And Assignment Cutover | L1 | Proposed |
| `WS-AUTH-001-14` | Submission, Checker, And Audit Visibility Cutover | L1 | Proposed |
| `WS-AUTH-001-15` | Remaining Internal Service Cutover And Obsolete Authority Removal | L1 | Proposed |
| `WS-AUTH-001-16` | Conformance, Observability, And Live API Proof | L1 | Proposed |

## Feature-gated registration and activation chunks

These identifiers are exact future gates, not executable chunk contracts or
automatic successors. AUTH materializes each contract only after its immutable
feature manifest exists, then requires a separate explicit start.

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-AUTH-001-REV-REG` | REV Lifecycle Action Registration | L1 | Blocked on complete REV typed manifests |
| `WS-AUTH-001-ART-REV-EVIDENCE-REG` | Review Evidence Binding Action Registration | L1 | Blocked on complete ART/REV dual-authority contract |
| `WS-AUTH-001-ART-02D-INTERNAL` | ART 02D Internal Action Activation | L1 | Feature-gated |
| `WS-AUTH-001-ART-02D-OPERATOR` | ART 02D Operator Read/Status And Independently Evaluated Retry Activation | L1 | Feature-gated |
| `WS-AUTH-001-ART-03` | ART 03 Guide Source Action Activation | L1 | Feature-gated |
| `WS-AUTH-001-ART-04A` | ART 04A Upload Action Activation | L1 | Feature-gated |
| `WS-AUTH-001-ART-04B` | ART 04B Pre-Submit Materialization Activation | L1 | Feature-gated |
| `WS-AUTH-001-ART-05` | ART 05 Submission Binding Activation | L1 | Feature-gated |
| `WS-AUTH-001-ART-06A` | ART 06A Post-Submit Materialization Activation | L1 | Feature-gated |
| `WS-AUTH-001-ART-06B` | ART 06B Checker Output Action Activation | L1 | Feature-gated |
| `WS-AUTH-001-REV-05` | REV 05 Queue Read Activation | L1 | Feature-gated |
| `WS-AUTH-001-REV-06` | REV 06 Claim Lease And Expiry Activation | L1 | Feature/service-gated |
| `WS-AUTH-001-REV-07` | REV 07 Context Chain And Finding Evidence Activation | L1 | Feature/ART-gated |
| `WS-AUTH-001-REV-08` | REV 08 Decision Activation | L1 | Feature/CON-gated |
| `WS-AUTH-001-REV-09A` | REV 09A Finding Response Evidence Activation | L1 | Feature/ART-gated |
| `WS-AUTH-001-REV-11` | REV 11 Recovery And Reconciliation Activation | L1 | Feature/service-gated |
| `WS-AUTH-001-REV-12` | REV 12 Artifact Reconciliation And Projection Activation | L1 | Feature/service-gated |
| `WS-AUTH-001-REV-LIFECYCLE` | REV Lifecycle Repair Action Activation | L1 | Blocked until REV-REG and four hidden manifests merge |
| `WS-AUTH-001-ART-REV-EVIDENCE` | Review Evidence Binding Action Activation | L1 | Blocked until registration and hidden ART/REV behavior merge |

## Dependency order

```text
WS-AUTH-001-PLAN
-> WS-AUTH-001-01
-> WS-AUTH-001-02
-> WS-AUTH-001-03
-> WS-AUTH-001-04A
-> WS-AUTH-001-04B
-> WS-AUTH-001-05A
-> WS-AUTH-001-CAT
-> WS-AUTH-001-05B
-> WS-AUTH-001-06
-> WS-AUTH-001-07A
-> WS-AUTH-001-07B
-> WS-AUTH-001-08
-> WS-AUTH-001-XINT
-> WS-AUTH-001-09A
-> WS-AUTH-001-09B
-> WS-AUTH-001-09C
-> WS-AUTH-001-09D
-> WS-AUTH-001-09E
-> WS-AUTH-001-ART-CUSTODY and WS-AUTH-001-REV-CUSTODY
-> WS-AUTH-001-PREP
-> WS-AUTH-001-10
-> WS-AUTH-001-11
-> WS-AUTH-001-12
-> WS-AUTH-001-13
-> WS-AUTH-001-14
-> WS-AUTH-001-15
-> all registration/activation chunks whose feature surfaces have merged
-> WS-AUTH-001-16
```

## Boundary notes

- Chunk 02 authenticates tokens but grants no product authority.
- Chunk 03 provides a supported classification gate before schema migration.
- Parent chunk 04 was split before implementation. Chunk 04A establishes
  request/correlation and additive error compatibility; chunk 04B later owns
  durable PostgreSQL rate controls and its migration.
- Parent chunk 05 was split before implementation. Chunk 05A owns shared audit
  schema/writer custody and append-only authority evidence; chunk 05B owns
  idempotency and typed invalidation orchestration.
- The docs-only catalogue reconciliation between 05A and 05B adopts a staged
  typed action/resource registry for future chunks without changing the merged
  permission/audit catalogue or starting runtime implementation.
- Chunk 06 establishes canonical actor resolution while preserving only the
  enumerated non-authoritative legacy workflow-eligibility consumers required
  for intermediate-release operability.
- Parent chunk 07 was split before runtime implementation. Chunk 07A owns the
  closed permission/action catalogue and action-aware audit parity; chunk 07B
  owns the minimal deny-by-default kernel and actor self-action cutover.
- PR #139 merged the WS-XINT boundary contract. `WS-AUTH-001-XINT` is the
  planning-only AUTH owner response; it changes no runtime.
- Chunks 08-10 establish local grant truth before product cutover. Parent chunk
  09 is split into 09A through 09E with no inserted dependency; 09E separately
  admits fixed services without entering human grant evaluation. ART/REV custody
  transfer follows 09E and changes only owner metadata and availability-neutral
  parity. PREP then establishes AUTH-first
  locking and caller-owned commit before sensitive product/review mutations.
- Chunks 11-15 migrate bounded complete product/system surfaces.
- Artifact upload, read, retention, release/delete, replication, integrity, and
  reconciliation remain mechanically owned by the artifact subsystem but must
  receive centralized AUTH decisions. Chunk 07A owns the permission/action
  registry, chunk 07B owns the central kernel, chunk 08 owns Operator grant
  definitions, chunk 09A owns the exact planned static matrix, and 09B owns
  controlled fixed service provisioning. AUTH-09E owns fixed service runtime
  admission. Each WS-ART feature chunk owns only
  hidden canonical resource facts, guards, surface declarations, decision calls,
  behavior, and tests. Dedicated AUTH custodians integrate evaluators and alone
  change availability after the matching ART behavior merges. AUTH-12, AUTH-14,
  and AUTH-15 are not alternate artifact activation paths. WS-ART-001-02D starts
  only after AUTH-09A through AUTH-09E and custody registration, then remains
  hidden until the internal and Operator AUTH activation checkpoints pass.
  Later ART and REV chunks use the same sequence. Exact mappings, registration
  counts, service-extension gates, and activation proof live in
  `ACTIVATION_CUSTODY.md`.
- Chunk 16 proves the complete initiative after every protected surface already
  merged has its matching AUTH activation and every unimplemented registered
  action still denies as planned. It does not backfill missing audit or
  idempotency evidence.
- `WS-POL-002-03` merged separately through PR #90 as `a7aa474`. This initiative
  does not own it; post-merge memory completed through PR #94. `WS-POL-002-04`
  remains inactive until the relevant project authorization cutover is complete
  and the user explicitly starts it.

## Stop condition

AUTH-03 post-merge memory merged through PR #110 as `1864867`. The user
explicitly started parent AUTH-04. Required plan review split it before runtime
implementation. AUTH-04A merged through PR #111 as `90c9a28`, and its
post-merge memory merged through PR #112 as `7749f54`. The user explicitly
started AUTH-04B. Its repaired contract passed at `b5dceb1`; bounded
implementation and all required internal review tracks passed, and PR #113
merged as `05a63c8` after Backend, Agent Gates, CodeRabbit, and explicit human
approval passed. AUTH-04B post-merge memory then merged through PR #114 as
`97cd0f5`, and the user explicitly started AUTH-05. Required plan review
rejected the combined contract before runtime edits and required 05A/05B.
The first 05A implementation review proved the original numeric ceiling
incompatible with readable typed/database privacy parity. Repaired 05A contract
review passed at `7cc6058`; the user subsequently replaced the line cap with
the semantic AUTH-05A boundary. Required reviews and checks passed, and explicit
human approval merged PR #115 as `8e1cde6` on 2026-07-14, followed by merged
post-merge memory. `WS-AUTH-001-CAT` then merged through PR #117 as `4c5d4fc`
after Backend, Agent Gates, CodeRabbit, and explicit human approval passed. The
CAT post-merge memory merged through PR #118 as `eba7e2b`; AUTH-05B then merged
through PR #119 as `ad71c7e`. AUTH-06 merged through PR #124 as `f599551`, its
signed automated memory completed, and the user explicitly started AUTH-07.
Required L1 review rejected the combined contract before runtime edits and
required 07A/07B. AUTH-07B merged through PR #130 as `90eca12`; AUTH-08 merged
through PR #131 as `aa0fdcd`. Parent AUTH-09 was split before implementation.
PR #140 merged the required XINT planning reconciliation as `d541521`. PR #132
then merged seven identities, eleven static matrix memberships, eight planned
actions, and migration `0023` as `299363a`; signed memory stopped. The user
explicitly started AUTH-09B. PR #143 merged it as `053242b`; signed memory
stopped, and the user explicitly started AUTH-09C. It must pass exact-head
review and checks, then stop for human merge. Do not start AUTH-09D or
POL-002-04 automatically.
