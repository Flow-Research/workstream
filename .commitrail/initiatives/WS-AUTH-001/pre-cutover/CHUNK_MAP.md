# Chunk Map: WS-AUTH-001 - Workstream Authorization Service

Review/revision activation custody is now planned canonically by
`../WS-XINT-003-rev-auth-end-to-end/ACTION_CUSTODY.md`. Historical AUTH-REV
labels are not alternate implementation paths.

The complete ART-facing catalogue and runtime dependency is now planned in
`../WS-XINT-002-art-auth-end-to-end/CHUNK_MAP.md`. The historical ART custody
entries in this file remain baseline identifiers only until that planning
amendment is approved and its first reconciliation chunk merges.

## Current use

This map preserves merged outcomes and dependency order. It is not an active
queue or authorization source. Distinct initiatives and non-overlapping chunks
may proceed concurrently; open pull requests show transient ownership.

## Chunks

`WS-ARCH-001/CHUNK_MAP.md` owns the ordered cross-module sequence
`WS-ARCH-001-CP01A -> CP01B -> CP01C -> CP02 -> CP03A -> CP03B -> CP04A -> CP04B -> CP05`; the AUTH entries below
project only AUTH-owned registration and activation responsibilities from that
sequence.

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-ARCH-001-CP01` | Combined registration planning parent | L1 | Planned split into CP01A/CP01B; non-executable |
| `WS-ARCH-001-CP01A` | Adapter-binding unavailable registration | L1 | Complete; excludes retirement, callback/fulfillment, identity, evaluator, and activation |
| `WS-ARCH-001-CP01B` | ContributionPolicy unavailable registration | L1 | Complete; excludes binding behavior, evaluator, and activation |
| `WS-ARCH-001-CP01C` | Adapter-binding fact correction | L1 | Complete; unavailable facts match binding identity and lifecycle generation |
| `WS-ARCH-001-CP03` | Adapter-binding activation parent | L1 | Split into CP03A/CP03B; non-executable |
| `WS-ARCH-001-CP03A` | Adapter target identity and owner eligibility prerequisite | L1 | Merged through PR #340; actions remain unavailable |
| `WS-ARCH-001-CP03B` | Exact Finance Authority adapter-binding activation | L1 | Complete; four exact hidden actions active only for covered human Finance Authority |
| `WS-ARCH-001-CP05` | Exact ContributionPolicy activation | L1 | Proposed after merged CP04A/CP04B hidden proof |
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
| `WS-AUTH-001-09C` | Actor And Identity-Link Administration Reads | L1 | Merged through PR #146 as `0ffdabf` |
| `WS-AUTH-001-09D` | Actor And Identity-Link Lifecycle Mutations | L1 | Split before runtime implementation into 09D-A and 09D-B |
| `WS-AUTH-001-09D-A` | Profile Lifecycle And Evidence Repair | L1 | Merged through PR #148 as `99ae4c9`; signed memory `cf8a3e8` passed |
| `WS-AUTH-001-09D-B` | Identity-Link Lifecycle And Race Closure | L1 | Merged through PR #152 as `93dd392`; signed memory `912a6254` passed |
| `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` | Contributor Fields And Canonical-Human Lineage | L1 | Merged through PR #153 as `8d5eb15b`; signed memory `66ab58d` passed and stopped |
| `WS-AUTH-001-09E` | Fixed Service Runtime Admission | L1 | Merged through PR #157 as `42a89b2d` on 2026-07-20 |
| `WS-AUTH-001-ART-CUSTODY` | ART Activation Custody Transfer | L1 | Merged through PR #158 as `be2a79a2`; historical 25-row transfer later reconciled by WS-XINT-002-01 to 22 planned ART actions |
| `WS-AUTH-001-REV-CUSTODY` | REV Activation Custody Transfer | L1 | Merged through PR #160 as `fe0e4492`; all 19 REV actions remain planned |
| `WS-AUTH-001-PREP` | Prepared Mutation Authorization Protocol | L1 | Merged through PR #162 as `c559d556`; no feature consumer or activation |
| `WS-AUTH-001-10` | Project Qualification And Contributor Role Grants | L1 | Planning split merged PR #168 |
| `WS-AUTH-001-10A` | Project Role Grant Data And Evidence Foundation | L1 | Merged PR #170; migration `0031` |
| `WS-AUTH-001-10B` | Project Role Grant Read Planning Parent | L1 | Planning split merged PR #173 |
| `WS-AUTH-001-10B1` | Durable Authorization Read Rate Control | L1 | Merged PR #175 |
| `WS-AUTH-001-10B2` | Privacy-Safe Project Role Grant Reads | L1 | Merged PR #178 |
| `WS-AUTH-001-10C` | Project Role Grant Mutations | L1 | Merged PR #194 |
| `WS-AUTH-001-11` | Project Read Cutover Planning Parent | L1 | Planning split merged PR #201 |
| `WS-AUTH-001-11A` | Project Read Catalogue And Projection Foundation | L1 | Merged in PR #208; migration `0035`, no active surface |
| `WS-AUTH-001-11B` | Project Identity And Actor Context Cutover | L1 | Merged in PR #214 as `033654ac` |
| `WS-AUTH-001-11C1` | Project Setup Diagnostic Read Cutover | L1 | Merged in PR #216 as `2965a9f9` |
| `WS-AUTH-001-11C2` | Effective Policy And Active Guide Read Cutover | L1 | Merged in PR #221 as `3fc323d7` |
| `WS-AUTH-001-12` | Project Mutation Cutover Planning Parent | L1 | Split before runtime implementation after failed L1 review |
| `WS-AUTH-001-12A` | Project Mutation Catalogue And PREP Foundation | L1 | Merged as PR #226 with AUTH `0041`; zero activation |
| `WS-AUTH-001-12B` | Fixed Project Setup Service Foundation | L1 | Merged through PR #227; identity/matrix registration only, zero activation |
| `WS-AUTH-001-12B2` | Unified Setup Ledger Activation | L1 | Proposed after complete POL-04A2 and AUTH-12J; before POL-04B live cutover |
| `WS-AUTH-001-12C` | Project Creation Cutover | L1 | Merged through PR #229 |
| `WS-AUTH-001-12D` | Draft Guide And Source Metadata Cutover | L1 | Merged through PR #232 |
| `WS-AUTH-001-12D2` | Review And Revision Policy Mutation Separation | L1 | Superseded by merged XINT-003-02A/02B; economic policy remains CON-owned |
| `WS-AUTH-001-12E` | Guide Sufficiency Mutation Cutover | L1 | Merged through PR #263 |
| `WS-AUTH-001-12F` | Submission Artifact Policy Planning Parent | L1 | Split after failed L1 pre-start review; zero activation |
| `WS-AUTH-001-12F1` | Submission Policy Authority Foundation | L1 | Merged through PR #286; zero activation |
| `WS-AUTH-001-12F2` | Manual Submission Policy Drafts | L1 | Merged through PR #292 as `81f281bd` |
| `WS-AUTH-001-12F3` | Transitional Fixed-Service Policy Derivation | L1 | Merged through PR #295 as `99c0aaf0`; superseded at POL-04B live cutover |
| `WS-AUTH-001-12I` | Unified Compilation Request/Execute Activation | L1 | Merged through PR #312 as `98eae13e`; POL-03B is the next consumer |
| `WS-AUTH-001-12J` | Compilation Projection Authorization | L1 | Complete; exact request-local fixed-service projection adapters are available for later POL wiring |
| `WS-AUTH-001-12F4` | Unified Pre-Submit Approval Activation | L1 | Proposed after hidden POL-05A; before POL-05B |
| `WS-AUTH-001-12G` | Unified Post-Submit Projection Activation | L1 | Proposed after hidden POL-06A; zero model calls |
| `WS-AUTH-001-12H` | Unified Guide Activation Cutover | L1 | Proposed after POL-06B/07, corrected AUTH-12B2, CP05 active behavior, CP06 validation, and CP07 ProjectGuide binding; CP08, ARCH-03A/03B/03C, and CP09 are downstream |
| `WS-AUTH-001-13` | Task Management And Assignment Cutover | L1 | Proposed |
| `WS-AUTH-001-14` | Historical Submission, Checker, And Audit Visibility Cutover | L1 | Planned retirement as superseded/non-executable; split across WS-ARCH-001-03C/04D/04E/04F and later REV/public cutover |
| `WS-AUTH-001-15` | Remaining Internal Service Cutover And Obsolete Authority Removal | L1 | Proposed |
| `WS-AUTH-001-16` | Conformance, Observability, And Live API Proof | L1 | Proposed |

## Feature-gated registration and activation chunks

These identifiers are exact future gates, not executable chunk contracts or
automatic successors. AUTH materializes each contract only after its immutable
feature manifest exists and then uses the ordinary bounded contribution loop.

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| Historical alias `WS-AUTH-001-REV-REG` | Superseded by `WS-XINT-003-02C` unavailable registration | L1 | Not executable; use canonical XINT-003 custody |
| `WS-AUTH-001-ART-02D-INTERNAL` | ART 02D Internal Action Activation | L1 | Feature-gated |
| `WS-AUTH-001-ART-02D-OPERATOR` | ART 02D Operator Read/Status And Independently Evaluated Retry Activation | L1 | Feature-gated |
| `WS-AUTH-001-ART-03` | ART 03 Guide Source Action Activation | L1 | Feature-gated |
| `WS-XINT-002-06A` | Pre-Submit Materialization Activation | L1 | Merged through PR #293; ART-04C1 is its next ART consumer |
| `WS-XINT-002-05A` | Historical Submission Bundle Preparation Activation | L1 | Superseded/non-executable; replacement WS-ARCH-001-02G requires 02A-02F |
| `WS-XINT-002-05B` | Historical Submission Binding Activation | L1 | Superseded/non-executable; replacement WS-ARCH-001-02H is merged |
| `WS-XINT-002-06B` | Historical Post-Submit Materialization And Checker Output Activation | L1 | Superseded/non-executable; WS-ARCH-001 PLAN2/04A-04E owns the current split |
| `WS-AUTH-001-REV-05` | REV 05 Queue Read Activation | L1 | Feature-gated |
| `WS-AUTH-001-REV-06` | REV 06 Claim Lease And Expiry Activation | L1 | Feature/service-gated |
| `WS-AUTH-001-REV-07` | REV 07 Context Chain And Finding Evidence Activation | L1 | Feature/ART-gated |
| `WS-AUTH-001-REV-08` | REV 08 Decision Activation | L1 | Feature/CON-gated |
| `WS-AUTH-001-REV-09A` | REV 09A Finding Response Evidence Activation | L1 | Feature/ART-gated |
| `WS-AUTH-001-REV-11` | REV 11 Recovery And Reconciliation Activation | L1 | Feature/service-gated |
| `WS-AUTH-001-REV-12` | REV 12 Artifact Reconciliation And Projection Activation | L1 | Feature/service-gated |
| Historical alias `WS-AUTH-001-REV-LIFECYCLE` | Superseded by `WS-XINT-003-08A` and `WS-XINT-003-08B` activation | L1 | Not executable; use canonical XINT-003 custody |
| `WS-XINT-002-07A` (runtime owner `WS-XINT-002-07`) | Review Packet Materialization Activation Only | L1 | Feature-gated on exact REV lease/version and ART packet behavior |
| `WS-XINT-002-07B` (runtime owner `WS-XINT-002-07`) | Reserved future review-evidence binding | L1 | Not approved for v0.1 |

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
-> WS-AUTH-001-09D-A
-> WS-AUTH-001-09D-B
-> WS-AUTH-001-CONTRIBUTOR-FOUNDATION
-> WS-AUTH-001-09E
-> WS-AUTH-001-ART-CUSTODY and WS-AUTH-001-REV-CUSTODY
-> WS-AUTH-001-PREP
-> WS-AUTH-001-10
-> WS-AUTH-001-10A
-> WS-AUTH-001-10B
-> WS-AUTH-001-10B1
-> WS-AUTH-001-10B2
-> WS-AUTH-001-10C
-> WS-AUTH-001-11
-> WS-AUTH-001-11A
-> WS-AUTH-001-11B
-> WS-AUTH-001-11C1
-> WS-AUTH-001-11C2
-> WS-AUTH-001-12
-> WS-AUTH-001-12A
-> WS-AUTH-001-12B
-> WS-AUTH-001-12C
-> WS-AUTH-001-12D
-> XINT-003-02A/02B (supersedes WS-AUTH-001-12D2)
-> WS-AUTH-001-12E
-> WS-AUTH-001-12F
-> WS-AUTH-001-12F1
-> WS-AUTH-001-12F2
-> WS-AUTH-001-12F3
-> WS-POL-003-01 -> 02 -> 03A
-> WS-AUTH-001-12I -> WS-POL-003-03B -> 04A -> WS-POL-003-04A3
-> WS-POL-003-04A2 + WS-AUTH-001-12J -> WS-AUTH-001-12B2
-> WS-POL-003-04B -> 05A
-> WS-AUTH-001-12F4 -> WS-POL-003-05B -> 06A
-> WS-AUTH-001-12G -> WS-POL-003-06B -> 07
-> WS-AUTH-001-12H
-> WS-ARCH-001-03A/03B -> WS-ARCH-001-03C (AUTH-13 task readiness)
-> WS-ARCH-001-04A-04E canonical post-submit `allow_review`
-> WS-POL-003-08 cleanup (not a prerequisite for WS-ARCH-001-03A)
-> WS-ARCH-001-04F checker remediation and later REV/public-cutover gates
-> historical WS-AUTH-001-14 remains superseded/non-executable
-> WS-AUTH-001-15
-> all registration/activation chunks whose feature surfaces have merged
-> WS-AUTH-001-16
```

## Boundary notes

- Chunk 02 authenticates tokens but grants no product authority.
- `WS-POL-003` owns unified guide compilation and product orchestration. AUTH
  owns only catalogue/evaluator/PREP activation and evidence. Hidden behavior
  precedes each AUTH activation; live cutover follows it.
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
  09 is split into 09A through 09E. The separately reviewed contributor
  foundation follows 09D-B so REV can consume canonical human attribution
  without waiting for the full AUTH-13/14 cutovers. It changes no authority or
  lifecycle behavior. 09E separately admits fixed services without entering
  human grant evaluation. ART/REV custody
  transfer follows 09E and changes only owner metadata and availability-neutral
  parity. PREP then establishes AUTH-first
  locking and caller-owned commit before sensitive product/review mutations.
- Parent chunk 11 is planning-only and splits the hard project-read cutover
  into 11A catalogue/evidence, 11B identity/context, 11C1 setup diagnostics,
  and 11C2 effective policy/guide reads. 11A activates no surface. Runtime
  children 11B, 11C1, and 11C2 each make local grants the sole authority for
  their complete surface family; no compatibility path remains.
- Parent 12 is planning-only. Its ten ordered children separately establish
  mutation catalogue/PREP contracts, fixed setup-service authority, project
  creation, draft guide/source metadata, separately authorized guide-bound
  review/revision policies, sufficiency, submission-artifact policy,
  post-submit checker policy, final setup-service runtime cutover, and terminal
  guide activation. Chunks
  13-15 then migrate their bounded complete product/system surfaces.
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
- `WS-POL-002-03` merged separately through PR #90 as `a7aa474`. Future guide
  inference belongs to WS-POL-003; any remaining POL-002 executor work requires
  a fresh bounded contract against current `main`.

## Current boundary

AUTH-12I and AUTH-12J are complete, as are their hidden POL-03B/04A/04A3
consumers. POL-04A2 may proceed independently and is the remaining prerequisite
of AUTH-12B2. No static row in this map starts work automatically.
