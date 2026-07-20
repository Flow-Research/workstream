# Chunk Map: WS-CON-001 Contribution Record And Compensation Boundary

## Rule

One chunk maps to one reviewable PR. No runtime chunk starts until its exact
AUTH, REV, outbox, migration, and human gates are satisfied on trusted `main`.
AUTH owns activation custody; feature ownership never supplies a second
availability writer. Optional evidence chunks are not part of the core order.

## Chunks

| Chunk | Title | Risk | Gate | Status |
|---|---|---:|---|---|
| `WS-CON-001-PLAN` | Contribution And Compensation Planning | L0 | None | Complete; unpublished |
| `WS-CON-001-PLAN2` | Final Acceptance Reconciliation | L0 | Human FinalAcceptance/no-adjudication direction | Complete; unpublished |
| `WS-CON-001-PLAN3` | AUTH/REV Current-Main Reconciliation | L0/L1 | Merged AUTH PR #140 plus AUTH-09A and REV PR #128 at `0302bcf` | Complete; unpublished |
| `WS-CON-001-01` | Canonical Contract Adoption And Architecture Decision | L0/L1 | Reconciled plan and human decisions approved | Complete; merged in PR #144 |
| `WS-CON-001-02A` | Shared Transactional Outbox Persistence | L1 | 01 merged at `e118e33`; trusted head refreshed through contributor-foundation PR #153 and ART-02C1 PR #154 at `44f2467c`; explicitly started by human | Reconciled as `0029` after ART `0028`; bounded proof, exact-SHA review, and GitHub full-suite pending |
| `WS-CON-001-02B` | Shared Outbox Dispatcher And Recovery | L1 | 02A; AUTH registers `outbox.dispatch`, approved `workstream.outbox.dispatcher` ServiceIdentity/static row, AUTH-09E admission, prepared protocol; dispatcher remains disabled until AUTH activation | Proposed |
| `WS-CON-001-02C` | Shared Lifecycle Audit Participant | L1 | 02B; current AuditEvent contract refreshed | Proposed |
| `WS-CON-001-03A` | Project Compensation Adapter-Binding Persistence | L1 | 02C; migration head refreshed | Proposed |
| `WS-CON-001-03B` | Contribution Policy Persistence | L1 | 03A; legacy-data rule; must precede REV-03 ReviewLease FK | Proposed |
| `WS-CON-001-03C` | Contribution And Award Persistence | L1 | 03B; merged REV-04B runtime FinalAcceptance/Review/ReviewLease FK targets | Proposed |
| `WS-CON-001-03D` | Delivery, Receipt, And Status Persistence | L1 | 03C; immutable fulfillment root ordinal/generation contract | Proposed |
| `WS-CON-001-04A` | Hidden Adapter-Binding Service | L1 | 03A; planned AUTH binding actions/contexts/prepared protocol; callback ServiceIdentity/action/static row approved but inactive | Proposed |
| `WS-CON-001-04B` | Hidden Contribution-Policy Service | L1 | 03B, 04A; binding activation merged; planned `contribution.policy.*` actions/contexts/prepared protocol | Proposed |
| `WS-CON-001-05A` | Legacy Economic Terms Cutover And Task Freeze | L1 | 04B; exact Submission/TaskAssignment lineage; AUTH-10 exact submitter grants and AUTH-PREP merged; task.claim PermissionId exists but ActionId remains absent; stable task-owned claim seam; legacy rule | Proposed |
| `WS-CON-001-05B` | Legacy Economic Schema Removal | L1 | 05A; zero-consumer scan; removal migration approval | Proposed |
| `WS-CON-001-06` | Review-Lease Contribution-Policy Freeze Capability | L1 | REV lease schema; 05B; AUTH-PREP; planned review.claim typed contract; exact reviewer grant facts stable | Proposed |
| `WS-CON-001-07` | Atomic Contribution/Award Decision Participant | L1 | 03C-D, 05A, 06; AUTH-PREP and complete REV custody transfer; REV-04 FinalAcceptance plus REV-09B locked lineage; shared audit/outbox; planned review.decision typed contract; two ordered operation-specific inputs | Proposed |
| `WS-CON-001-08A` | Outbound Compensation Delivery Handler | L1 | 07, 02B; exact delivery ServiceIdentity/ActionId/static row registered but planned; AUTH-09E typed context/prepared protocol; ADR 0014 adapter foundation; lifecycle-fence port | Proposed |
| `WS-CON-001-08R` | Bound-Service Callback Rate Control | L1 | 08A; shared API-control contract | Proposed |
| `WS-CON-001-08B` | Inbound Fulfillment Callback | L1 | 08R; exact callback ServiceIdentity/ActionId/static row, AUTH-09E context, prepared protocol, and callback-fence port | Proposed |
| `WS-CON-001-09A` | Optional Contribution Evidence Projection Write | L1 | Separate human approval; refreshed ART/AUTH contract and chunk review | Deferred optional |
| `WS-CON-001-09B` | Optional Authorized Contribution Evidence Read | L1 | 09A plus separate approval; refreshed disclosure contract | Deferred optional |
| `WS-CON-001-10A` | Contribution And Award Product Reads | L1 | 08B; D11 award-role outcome; planned contribution/award read actions and typed contexts | Proposed |
| `WS-CON-001-10B` | Operations Requests, Reads, And Fulfillment Drain Observation | L1 | 10A; D11 complete; operations request/read actions/contexts/prepared protocol; outbox observation port | Proposed |
| `WS-CON-001-10C` | Reconciliation And Projection Executors | L1 | 10B; exact executor identities/actions/static rows; AUTH-09E; hidden behavior then AUTH activation | Proposed |
| `WS-CON-001-11` | Hidden Release Readiness And Dependency Manifest | L1 | 10C; merged REV-10 decision integration; exact AUTH evaluator/action/service manifest; every obligation-writer/dispatch/callback hook; monotonic root ordinal; same-session cutoff/drain port | Proposed |

## Core dependency order

```text
PLAN -> PLAN2 -> PLAN3 -> 01 -> 02A -> 02B -> 02C -> 03A -> 03B -> 03C -> 03D
-> 04A -> 04B -> 05A -> 05B -> 06 -> 07 -> 08A -> 08R -> 08B
-> 10A -> 10B -> 10C -> 11
```

Optional successor, not a branch in the core release:

```text
separate human approval -> refreshed ART/AUTH handoff -> 09A -> 09B
```

## Cross-initiative gates

```text
AUTH registration -> CON hidden behavior -> AUTH activation -> later consumer/release
```

- AUTH-09A through 09D-B are merged; AUTH-09B activates only the human
  administrative provisioning route, AUTH-09C activates only actor/profile
  administrative reads, AUTH-09D-A activates only actor-profile lifecycle, and
  AUTH-09D-B activates only identity-link revoke/reactivate. None grants
  service execution. The contributor foundation is merged; AUTH-09E must still precede protected
  fixed-service execution. New CON
  ServiceIdentity/static-row additions require separate reviewed AUTH contracts
  before provisioning; no existing ART identity or provisioning result may be
  reused as CON authority.
- The outbox dispatcher owns only claim/invoke/finalize under
  `outbox.dispatch`. Each protected handler has independent approved authority.
- Task claim requires AUTH-PREP and one exact active same-project submitter
  grant. CON-05A first lands the hidden freeze participant; task-owned claim
  composition consumes it after task/assignment locks; `WS-AUTH-001-13` then
  enumerates/registers the exact ActionId, integrates its evaluator, and
  activates. Registration/activation before that freeze proof is prohibited.
- Review claim requires one exact active same-project reviewer grant. CON-06
  supplies only the freeze port; REV supplies hidden claim composition; AUTH
  activates review.claim after both merge.
- Review decision requires the reviewer grant and no-self-review/lifecycle
  guards. CON-07 starts only after the TaskAssignment submitter freeze and REV
  ReviewLease reviewer freeze plus accept-only FinalAcceptance persistence and
  locked decision-lineage contract are merged with non-null policy-version
  lineage. CON-07 then supplies the flush-only participant with no ART/evidence
  work; REV consumes that participant in hidden decision composition, stages
  shared audit/outbox, and owns the single commit. AUTH activates
  `review.decision` only after that hidden REV composition merges.
- CON-07 creates contributions and applicable awards in the Review transaction.
  Reviewer work is sourced from Review; submitter work is sourced only from
  REV-owned FinalAcceptance. REV stages shared audit/outbox rows, owns the
  single commit, and supplies stabilized artifact-hash lineage; no ART call is
  made.
- Merged REV PR #128 plus PLAN2 PR #150 are planning authority, not runtime
  readiness. CON-03B precedes REV-03A; CON-02A/02C precede REV-04B; REV-04B
  precedes CON-03C; CON-06 precedes REV-06A; REV-09B plus CON-03C/07 precede
  REV-10; the CON-02B dispatcher/handler registry precedes REV-12P1; CON's
  03D/08A/08B/10B/11 hooks precede REV-12A3; and CON-11 precedes REV-13C.
- CON-08A/B and 10C cannot reuse outbox dispatcher authority for delivery,
  callback, reconciliation, or rebuild execution.
- CON-10A owns core PostgreSQL contribution/award reads directly; it does not
  wait for optional evidence reads.
- CON-11 has no ART or evidence-projection prerequisite. It hands mandatory
  obligation-writer, dispatch, callback, maximum-ordinal, and drain-observation
  seams to REV-12A1/12A3's single shared lifecycle controller and registers no
  route.
- AUTH PR #140's complete ART and REV activation-custody transfer contracts are
  consumed by reference to AUTH/WS-XINT handoffs. The runtime transfers remain
  upstream gates; WS-CON does not define partial subsets.

## Chunk boundaries

- 01 owns current specification/ADR adoption and scanner-safe active wording;
  it does not edit archival inputs.
- 02A owns persistence/append; 02B owns generic dispatcher mechanics only; 02C
  owns the shared caller-transaction audit participant.
- 03A uses `ProjectCompensationAdapterBinding`; 03B owns ContributionPolicy,
  versions, rules, and award definitions; 03C/D own contribution/award and
  downstream fulfillment records respectively. 03C references but never owns
  REV's FinalAcceptance.
- 04A/04B add hidden binding and policy services while AUTH actions remain
  planned.
- 05A removes semantic consumers and freezes task assignments; 05B removes dead
  physical schema.
- 06 exposes only a CON policy-freeze capability; REV owns ReviewLease schema
  and wiring.
- 07 exposes only the flush-only decision participant; REV owns Review,
  FinalAcceptance, shared audit/outbox staging, and the single commit. No
  evidence projection is staged.
- 08A is a feature handler with its own protected execution boundary; 08R owns
  rate-control scope; 08B owns callback authentication/composition.
- 09A/09B are deferred optional projection chunks and must be re-reviewed if
  activated later.
- 10A owns core PostgreSQL product reads; 10B owns bounded operations requests
  and typed drain observation; 10C owns independently authorized executors.
- 11 proves hidden readiness and blocks runtime requests on missing provisioned
  service rows while leaving application startup and provisioning available.

## Required reviewer tracks

Every chunk: senior engineering, QA/test, security/auth, product/ops,
architecture, docs, and reuse/dedup. Runtime/test chunks add test-delta. Add CI
integrity for workflows, scripts, dependencies, test configuration, or coverage.

## Stop condition

Planning ends after required plan review and human discussion. Do not start 01,
09A, or any runtime chunk automatically.
