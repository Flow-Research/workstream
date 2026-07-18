# Chunk Map: WS-REV-001 Review And Revision Lifecycle

## Rule

One chunk maps to one PR. No runtime chunk starts until its AUTH, ART, and CON
gates are satisfied on current trusted `main` and the user gives a separate
explicit start signal.

## Chunks

| Chunk | Title | Risk | Gate | Status |
|---|---|---:|---|---|
| `WS-REV-001-PLAN` | Review And Revision Lifecycle Planning | L1 | None | Merged through PR #128 at trusted main `0302bcf854a565d429e232ad6b076a1931ea74e4` |
| `WS-REV-001-01` | Canonical Contract Adoption And Dependency Conformance | L1 | Plan approval; current-main refresh; merged WS-XINT-001 handoffs, AUTH PR #140 planning contracts, AUTH-09A/09B foundations, and CON-01 canonical contract adoption | Merged through PR #145 at trusted main `b2b9016d5fee33ddca40882c97620a178d8e52f0` |
| `WS-REV-001-02` | Locked Review Policy And Task Lifecycle Alignment | L1 | Parent explicitly started; required L1 plan review | Split before runtime; non-executable parent |
| `WS-REV-001-02A` | Project Guide Activation Sequence And Publication Locking | L1 | AUTH-09D-A and the subsequent AUTH-owned contributor-field foundation merged; exact dependency SHA/head refresh; separate human start | Planning prepared; runtime blocked |
| `WS-REV-001-02B` | Locked Review Policy And Dormant Task Lifecycle Compatibility | L1 | 02A merged; approved preference/lease duration defaults; separate human start | Proposed |
| `WS-REV-001-02C` | Submission Attribution, Context, And Immutable Lineage | L1 | 02B merged; exact AUTH contributor/human-lineage constraints present; separate human start | Proposed |
| `WS-REV-001-03` | Review Queue And Lease Persistence | L1 | 02C merged; WS-CON ContributionPolicyVersion persistence merged | Proposed |
| `WS-REV-001-04` | Immutable Review, Final Acceptance, Findings, And Replay Persistence | L1 | 03 merged; shared transactional-outbox persistence and caller-transaction lifecycle-audit participant merged at exact refreshed SHAs | Proposed |
| `WS-REV-001-05` | Checker Admission, Preferred Routing, And Queue Views | L1 | 04; ART v2 submission/checker cutover; AUTH-10 reviewer grants and AUTH-11 project visibility; registered actions remain planned; hidden manifest later gates `WS-AUTH-001-REV-05` | Proposed |
| `WS-REV-001-06` | Atomic Claims, Release, Preference, And Timers | L1 | 05; merged `WS-AUTH-001-REV-CUSTODY` and `WS-AUTH-001-PREP`; merged AUTH-09A foundation and AUTH-09B provisioning capability plus exact expiry identity extensions/provisioning and AUTH-09E admission from the merged REV-01 manifest; WS-CON ReviewLease ContributionPolicyVersion freeze participant; hidden manifest later gates `WS-AUTH-001-REV-06` | Proposed |
| `WS-REV-001-07` | Artifact-Backed Review Context And Finding Evidence | L1 | 06; merged PREP consumer contract; approved and merged ART-owner amendment for v2 packet-read; separately approved `WS-ART-001-REV-EVIDENCE` candidate/finalize capability; `WS-AUTH-001-ART-REV-EVIDENCE-REG` plus exact binding service row; hidden manifests later gate `WS-AUTH-001-REV-07` and `WS-AUTH-001-ART-REV-EVIDENCE` | Proposed |
| `WS-REV-001-08` | Decision, Final Acceptance, And Task-Effect Contract | L1 | 07; merged PREP consumer contract; Review persistence and the accept-only FinalAcceptance write remain disabled until 10; complete hidden REV+CON composition later gates `WS-AUTH-001-REV-08` | Proposed |
| `WS-REV-001-09A` | Revision Context Preparation And Resubmission | L1 | 08; ADR 0010 adopted; retired compensation-context field removal merged; schema-only contributor-field foundation; PREP; registered planned `submission.create`; hidden manifest later gates `WS-AUTH-001-REV-09A` and amended AUTH-13/14 product cutovers | Proposed |
| `WS-REV-001-09B` | Finding Replay, Resolution, And Return Routing | L1 | 09A | Proposed |
| `WS-REV-001-10` | Final Acceptance, WS-CON Atomic Integration, And Hidden Composition | L1 | 09B; PREP; approved and merged ART/task-owner `Submission.artifact_hash` amendment; merged CON FinalAcceptance-sourced lineage schema and two-operation flush-only contribution/award participant; no mandatory contribution-evidence projection; completion later gates `WS-AUTH-001-REV-08` | Proposed |
| `WS-REV-001-11` | Admin Overrides, Reviewer-Revocation Recovery, And Reconciliation | L1 | 10; AUTH invalidation; `WS-AUTH-001-REV-REG` registered/planned from the merged REV-01 manifest; PREP; merged AUTH-09A foundation and AUTH-09B capability plus exact invalidation/reconciliation identity extensions/provisioning and AUTH-09E admission from that manifest; ART Operator recovery port; hidden manifest later gates `WS-AUTH-001-REV-11` | Proposed |
| `WS-REV-001-12` | Snapshot Projection, Notifications, And Observability | L1 | 11; ART projection port; outbox foundation; PREP; merged AUTH-09A foundation and AUTH-09B capability plus exact artifact-reference/projection identity extensions/provisioning and AUTH-09E admission from the merged REV-01 manifest; hidden manifest later gates `WS-AUTH-001-REV-12` | Proposed |
| `WS-REV-001-12A` | Joint Lifecycle Release-Control Foundation | L1 | 12 review drain-observation port; exact core WS-CON hidden-readiness manifest; `WS-AUTH-001-REV-REG`; PREP; CON obligation-writer, dispatch, and callback fence hooks plus fulfillment/outbox drain-cutoff and observation port; complete additive manifests later gate `WS-AUTH-001-REV-LIFECYCLE` | Proposed |
| `WS-REV-001-13` | Coherent Public Release, Live API Drill, And Release Proof | L1 | 12A; amended full AUTH-13/14 product cutovers; AUTH-14 `submission.create` active with prepared-revision proof; `WS-AUTH-001-REV-CUSTODY`; exact `WS-AUTH-001-REV-05/06/07/08/09A/11/12`, `WS-AUTH-001-REV-LIFECYCLE`, and ART evidence actions active after hidden behavior; ART/CON/outbox live readiness | Proposed |

## Dependency order

```text
PLAN -> 01 -> 02(parent split) -> 02A -> 02B -> 02C -> 03 -> 04 -> 05 -> 06 -> 07 -> 08 -> 09A -> 09B -> 10 -> 11 -> 12 -> 12A -> 13
```

External initiative gates are inserted without changing same-initiative
successor order:

```text
WS-REV-001-01 active contract and immutable registration/service manifests
  -> WS-AUTH-001-REV-REG availability-neutral four-action registration
  -> separately reviewed AUTH identity-specific extension contracts
  -> corresponding REV mutation/service chunks may consume registered actions
     and exact identities while every action remains unavailable

AUTH-09D-A plus AUTH canonical human and the subsequent AUTH-owned
schema-only contributor-field foundation
  + merged AUTH-08 transaction/error/timestamp invariants
  + ART v2 stable contracts
  -> WS-REV-001-02A -> WS-REV-001-02B -> WS-REV-001-02C

WS-REV-001-02C
  -> WS-CON exact attribution consumption and retired compensation-context field removal

WS-REV-001-02C + merged WS-CON ContributionPolicyVersion persistence
  -> WS-REV-001-03

WS-REV-001-03 + merged CON-owned shared transactional-outbox persistence
  -> WS-REV-001-04

merged CON-owned caller-transaction shared lifecycle-audit participant
  -> WS-REV-001-04

WS-REV-001-04 stable Review, FinalAcceptance, ReviewLease, and Submission schemas
  + merged ART submission/checker cutover with server-derived stabilized
    Submission.artifact_hash
  -> WS-CON exact FinalAcceptance-sourced contribution/award lineage persistence

WS-CON retired compensation-context field removal
  -> WS-REV-001-09A

WS-REV-001-09A hidden prepared revision/replacement behavior
  -> amended AUTH-13/14 full product cutovers
  -> AUTH-14 submission.create activation after exact evaluator proof

WS-REV-001-09B + WS-CON exact lineage schema + flush-only contribution/award participant
  -> WS-REV-001-10

WS-CON exact core hidden-readiness manifest + WS-REV-001-12
  -> WS-REV-001-12A hidden joint release-control foundation
  -> AUTH activates each exact action through its named REV gate after hidden behavior
  -> WS-REV-001-13 sole joint product release
```

The merged ART plan does not yet schedule `WS-ART-001-REV-EVIDENCE`. REV-07 is
therefore explicitly blocked until ART owns, approves, and merges that chunk;
REV planning does not create or start it on ART's behalf.

## Chunk boundaries

- 01 changes contracts and active documentation, not runtime behavior.
- 02 is a non-executable split record. 02A-02C and 03-04 land bounded
  persistence and constraints, including immutable FinalAcceptance, without
  public review mutations.
- 05-07 build routing, leases, and evidence consumption behind an unavailable
  production composition boundary; registration remains availability-neutral.
- 08 freezes decision inputs, validation, task effects, and the
  FinalAcceptance consequence of `accept`. It cannot commit a canonical Review
  or an accept-path FinalAcceptance until the CON participant is installed.
- 09A prepares controlled revision context and immutable resubmission input.
- 09B completes finding replay, resolution, and preferred-return semantics.
- 10 creates the first transaction capable of committing every canonical Review
  and, for `accept`, the additional FinalAcceptance record. It proves WS-CON
  atomicity in hidden composition.
- 11-12 complete operations, recovery, projection, and observability.
- 12A lands hidden persisted release control and mandatory cross-domain fences.
- 13 performs fail-closed preflight, exposes the already-AUTH-active coherent
  public API set,
  proves the whole lifecycle, and closes generated/user/operator docs.

## Required reviewer tracks

Every chunk: senior engineering, QA/test, security/auth, and product/ops.

Add architecture and reuse/dedup to 01-13, including split children 02A-02C.
Add docs to PLAN and every chunk that changes schema, routes, runtime jobs,
configuration, or active behavior. Add test-delta to every runtime chunk. Add
CI integrity whenever a
workflow, script, dependency, or coverage gate changes.

## Stop condition

Parent 02 planning may be reviewed and merged without runtime. Stop after its
automated memory names 02A. Do not start 02A until AUTH-09D-A and the subsequent
AUTH contributor foundation merge and the user provides a separate explicit
start. The duration defaults gate 02B, not 02A.
