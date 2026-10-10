# WS-AUTH-001 — Workstream authorization service

[REV-12A4A](../WS-REV-001/WS-REV-001-12A4A.md) adds internal Operator-controlled lifecycle transitions and current-generation terminal replay. New acceptance effects require LIVE; 04E2-B supplies hidden source AUTH custody, while production routing remains unavailable. Conditional award facts stay atomic, while fulfillment admission, payment delivery and their root/cutoff machinery remain deferred until a successor manifest enables them.

Delivery priority follows the [first complete contributor milestone](../WS-ARCH-001/planning/PLAN.md#first-complete-contributor-milestone): contribute only prerequisites of that public backend path; live human review/revision and external integrations remain later work.

[ARCH-04E2-B](../WS-ARCH-001/WS-ARCH-001-04E2B.md) delivers the hidden authorized outcome operation.
It consumes canonical fixed-router AUTH and retains the actual immutable decision
with exact Submission, materialization and checker receipts. Locked true moves
TASK to `review_pending` without REV/CON. Locked false uses the shared acceptance
participant to atomically stage FinalAcceptance, TASK/assignment completion,
submitter contribution, applicable awards and audit/outbox evidence. Database
closure rejects incomplete outcomes; fresh-authorized replay returns the stored
complete tuple. No Review or reviewer contribution is fabricated.

B8 supplies hidden completion delivery with commit-before-ACK. Next: 04F remediation, 04E3 production
composition, public intake and the first-layer drill. False-guide activation,
live human review/revision and payment delivery remain unavailable. Internally
valid false-policy fixtures establish the hidden operation, not public readiness.

Latest completed activation: [AUTH-18 public manager activation](WS-AUTH-001-18.md),
using [AUTH-12H complete-guide authority](WS-AUTH-001-12H.md),
following [AUTH-12G post-policy authority](WS-AUTH-001-12G.md).
Current remaining [plan](planning/PLAN.md) and [activation map](planning/CHUNK_MAP.md).

Historical pre-cutover work records: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Delivered prerequisite: [ART-07A1](../WS-ART-001/WS-ART-001-07A1.md) supplies
  metadata-only packet types. REV-03B packets, REV-04A Review storage, REV-04B
  FinalAcceptance storage, CON-03C contribution/award storage, REV-12A1 disabled
  fencing, hidden AUTH preparation, CON-07 hidden submitter participation and
  REV-04C hidden FinalAcceptance/TASK/CON composition are
  delivered. Mandatory persisted custody accompanies the first authorized atomic
  consequence at 04E2-B. No packet resolver or human runtime is live.

- Intent: provide deny-default, project-scoped authority with canonical human
  and service identities and attributable audit evidence.
- Current boundary: hidden projections and atomic setup finalization have exact
  request-local authority through AUTH-12J and AUTH-12B2; the five
  ContributionPolicy actions have exact Finance Authority through CP05 and public
  administration through CP05A.
- Completed proposal boundary: AUTH-12F4 exact-project manager read, correction
  and pre-submit approval authority over hidden POL-05A behavior.
- Completed post-policy boundary: AUTH-12G fixed setup derivation and exact-project
  manager read, approval and correction authority over POL-06A.
- Public post-policy composition: POL-06B delivered using existing AUTH-12G.
- Completed activation boundary: AUTH-12H exact-project manager authority for
  CP07 complete-guide activation/binding, with live-authority replay.
- Delivered dependent boundary: ARCH-04E1A immutable route-neutral source facts
  and accepted-effects contracts follow
  [ARCH-04D2](../WS-ARCH-001/WS-ARCH-001-04D2.md) exact input, execute and
  finalize authority. REV-04C supplies the hidden effects participant, and ARCH-04E2-B supplies
  the authorized outcome operation. No production routing handler is registered. Output-file authority remains unavailable for the zero-output
  catalogue. [AUTH-18](../WS-AUTH-001/WS-AUTH-001-18.md) delivers
  public manager activation context and exact guide activation.
  [CP05A](../WS-ARCH-001/WS-ARCH-001-CP05A.md) delivers public Finance
  ContributionPolicy administration and recovery of a draft selector, a published
  selector, or both. ARCH-03C3 through ARCH-03C7 deliver public task readiness,
  queues, detail/requirements, locked context and audit history.
  Completed foundations:
  [ARCH-03C2](../WS-ARCH-001/WS-ARCH-001-03C2.md) supplies atomic publication and
  registered assignment delivery with enforced prefork topology. ARCH-03C1 supplies exact fixed-service
  reconciliation authority and decision-bound release receipts. ARCH-03B9 supplies the
  hidden exact-assignment operation and transaction fence. AUTH-OUTBOX-02 delivers
  shared live dispatcher authority, phase audit custody and Celery recovery after
  CON-02B delivery mechanics. This follows
  completed ARCH-03B8 hidden task audit evidence and ARCH-03B7 requirements projections and ARCH-03B6 locked-context projections and ARCH-03B5 current work context and ARCH-03B4 hidden contributor/management task detail, ARCH-03B3 hidden management/operational queues and ARCH-03B2 contributor-ready queue facts, ARCH-03B1 detached metadata and CP08 lineage
  and minimal writers and ARCH-03A internal guide context. POL-07B internal phase composition is delivered.
  The dispatcher registers only exact assignment invalidation. Automatic checker
  routing still requires completion delivery and production registration.
- Delivered routing preparation: [ARCH-04E2-A](../WS-ARCH-001/WS-ARCH-001-04E2A.md)
  adds the strict exact routing resource, request matcher, digest dispatch and
  fixed-router adapter through canonical PREP. ARCH-04E2-B consumes that
  preparation only inside the complete authorized outcome transaction.
- Delivered storage: [REV-03B](../WS-REV-001/WS-REV-001-03B.md) freezes exact
  lease packets with normalized live guide ingests; no resolver or byte authority.
  [REV-04A](../WS-REV-001/WS-REV-001-04A.md) adds complete immutable Review, findings, resolutions and completed request storage; no decision runtime.
- Next usable boundary: prove 04F
  remediation, 04E3 live composition and false-guide readiness, public intake
  and the first-layer drill. True handoff remains independent of REV/CON;
  live human review/revision and payment delivery stay deferred.
- Governing source: `docs/spec_authorization_service.md`, authorization code,
  migrations, and tests.
- Preserve: Flow token verification only, no Workstream login/session system,
  exact action/permission catalogues, prepared mutation protocol, and
  fail-closed action availability.

REV-12A4A supplies scoped lifecycle transitions on the existing REV fence.
04E2-B supplies exact source AUTH custody and complete database/effect closure.
Production composition and false-guide activation remain separate work.

This is delivery priority, not a prerequisite of true human admission. Both
routing branches have delivered request reservation 04E1B-A → delivered AUTH preparation 04E2-A → delivered authorized outcomes 04E2-B → completion delivery 04E1B-B → live 04E3; true routing
can proceed after its own prerequisites without CON/shared acceptance or
scoped lifecycle activation. False routing adds those requirements. Human final
acceptance later uses the same authorized shared acceptance/CON operation.

## Delivered

- Flow-token verification, canonical actors/identity links, request and rate
  controls, audit/idempotency, project grants, bootstrap administration,
  fixed-service admission, controlled provisioning, and project read/mutation
  authorization are merged.
- Project-guide compilation request, recovery, fixed setup execution, and
  exact deterministic-projection authority are merged through `12J`; hidden
  POL projection ports exist through POL-04A3.
- AUTH-12B2 activates only fixed setup-service finalization of exact locked
  facts, with current lifecycle checks, immutable receipt binding, and exact
  historical replay. POL-04B composes its explicit adapter in the live Celery worker; default and
  public mutation ports remain unavailable.

## Remaining v0.1 sequence

Follow the [current cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).
Hidden owner behavior precedes exact AUTH authority; neither guide activation
nor policy selection is authorized by the sufficiency action.

POL-06B exposes completed POL-06A operations with AUTH-12G authority.
POL-04B/05A/05B and AUTH-12F4 supply live unified setup and public
manager proposal review, pre-submit approval and manual correction dispatch.

1. CP07 complete-guide activation/binding and AUTH-12H live authority are delivered.
   ARCH-03A supplies complete internal guide facts before CP08 lineage and minimal writers.
2. ARCH-03B/03C replace broad AUTH-13 and ARCH-04D2 replaces AUTH-14/XINT-06B.
   AUTH-OUTBOX-01/02 bracket hidden CON-02B dispatch; ARCH-04E2 activates only
   the proven TASK routing handler before ARCH-04E3 live composition.
   TASK queue/read exposure is complete through ARCH-03C7. AUTH-18 public
   manager guide activation/context is delivered; ARCH-03D hidden intake, hidden exact post-submit materialization and ARCH-04B2 output custody are delivered; ARCH-04C hidden execution is delivered; ARCH-04D1 canonical material custody is delivered; ARCH-04D2 exact input/execution/finalization authority, ARCH-04E1A source-only facts/types and ARCH-04E2-A hidden strict preparation are delivered. 04E2-B authorized outcomes are delivered; B8 completion delivery is implemented; remediation and live 04E3 remain. Shared acceptance foundations additionally gate false routing, not true admission.
   Remaining work must use its exact owner, not the superseded broad designs.
