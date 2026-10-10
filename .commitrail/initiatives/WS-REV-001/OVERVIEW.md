# WS-REV-001 — Review and revision lifecycle

[REV-12A4A](WS-REV-001-12A4A.md) adds internal Operator-controlled lifecycle transitions and current-generation terminal replay. New acceptance effects require LIVE; 04E2-B supplies hidden source AUTH custody, while production routing remains unavailable. Conditional award facts stay atomic, while fulfillment admission, payment delivery and their root/cutoff machinery remain deferred until a successor manifest enables them.

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

Current upstream dependency: [ARCH-04E canonical `allow_review`](../WS-ARCH-001/planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md).
This is the pre-review admission fact, not REV activation or implementation
of review/revision behavior. The downstream owner contracts remain separate.

- Disposition: Planned
- Delivered prerequisite: [ART-07A1](../WS-ART-001/WS-ART-001-07A1.md) supplies
  metadata-only packet types. REV-03B packets, REV-04A Review storage, REV-04B
  FinalAcceptance storage, CON-03C contribution/award storage, REV-12A1 disabled
  fencing, hidden AUTH preparation, CON-07 hidden submitter participation and
  REV-04C hidden FinalAcceptance/TASK/CON composition are
  delivered. Mandatory persisted custody accompanies the first authorized atomic
  consequence at 04E2-B. No packet resolver or human runtime is live.

- Completed boundary: queue admission and ReviewLease persistence through 03A2,
  plus normalized immutable packets through 03B, Review sources through 04A
  and shared FinalAcceptance source storage through 04B.
- Intent: ensure the authorized reviewer evaluates the exact verified artifact
  under the locked policy version and produces attributable outcomes.
- Delivered upstream boundary: ARCH-04E1A provides immutable route-neutral TASK
  source storage, detached source facts and accepted-effects contracts. REV-04C
  supplies their hidden FinalAcceptance/TASK/CON participant and bounded stored-
  source verifier; no general routing publication writer/reader, handler,
  routing authority or current pointer exists.
- Delivered storage: [REV-03B](../WS-REV-001/WS-REV-001-03B.md) freezes exact
  lease packets with normalized live guide ingests; no resolver or byte authority.
  [REV-04A](../WS-REV-001/WS-REV-001-04A.md) adds complete immutable Review, findings, resolutions and completed request storage; no decision runtime.
- Next usable boundary: prove 04F
  remediation, 04E3 live composition and false-guide readiness, public intake
  and the first-layer drill. True handoff remains independent of REV/CON;
  live human review/revision and payment delivery stay deferred.
- Governing sources: `docs/spec_review_lifecycle.md`,
  `docs/engineering/review_authorization_action_custody.md`, code, migrations,
  and tests.
- Preserve: only `accept`, `needs_revision`, and `reject`; immutable attempt
  policy lineage; separation of duties; and atomic final acceptance effects.

REV-12A4A supplies scoped lifecycle transitions on the existing REV fence.
04E2-B supplies exact source AUTH custody and complete database/effect closure.
Production composition and false-guide activation remain separate work.

This is delivery priority, not a prerequisite of true human admission. Both
routing branches have delivered request reservation 04E1B-A → delivered AUTH preparation 04E2-A → delivered authorized outcomes 04E2-B → completion delivery 04E1B-B → live 04E3; true routing
can proceed after its own prerequisites without CON/shared acceptance or
scoped lifecycle activation. False routing adds those requirements. Human final
acceptance later uses the same authorized shared acceptance/CON operation.

## Delivered

- Hidden review queue/admission persistence, ReviewLease, and preference
  persistence are merged through 03A2. REV policy identities and mutations and
  the fail-closed AUTH PREP/read handoff are available.
- [REV-04A](WS-REV-001-04A.md) delivers immutable Review, finding, resolution and completed request storage. Submission responses remain with their future preparation owner.
- No live claim or canonical review decision is implied by this foundation.

[REV-04B](WS-REV-001-04B.md) stores exclusive Review/TASK source lineage without
AUTH receipts or a production writer. Before runtime use, harden this same table
with mandatory exact originating authority and refuse retained pre-authority rows.
Neither storage foundation grants acceptance authority.

## Remaining v0.1 sequence

### Acceptance-mode amendment — Planned

Use `human_review_required: bool = true` in the existing locked guide-bound
ReviewPolicy: after required post-submit checks pass, true requires human
review and false proceeds to authorized FinalAcceptance without reviewer
contribution. No mode enum or additional policy is needed. The
[canonical shared acceptance contract](../../../docs/spec_review_lifecycle.md#finalacceptance)
defines both triggers, exclusive provenance, constraints, authority and one
atomic operation. Do not build a separate workflow engine.

REV owns shared final-acceptance semantics for both paths. The automated path
must have explicit AUTH service authority and exact TASK/CHECKERS evidence,
without a fabricated Review, ReviewLease, human actor, or reviewer contribution.
CON validates stored source ancestry through the delivered source-neutral
submitter participant and complete frozen award-set owner. REV-04C supplies the
hidden source-neutral FinalAcceptance/TASK/CON participant, but no routing
handler, exact AUTH decision-event receipt, audit/outbox consequence or live
runtime composition.
The human branch below continues to use `allow_review`; it is not an automatic
acceptance signal.

The [versioned policy setting](../../changes/pre-review-plan-reconciliation.md#delivered-policy-setting-implementation)
is available for draft configuration. ARCH-04E2-B supplies mandatory routing
authority and atomic CON participation; completion delivery, remediation and
production readiness still precede enabling false. The automated branch must not depend on
live human queues, ReviewLeases or decision endpoints. Human lifecycle work
remains required for v0.1, but need not delay the first automated end-to-end
proof. No adjudication setting or behavior is included.

1. `03B` is complete: normalized reviewer packet persistence consumes the delivered
   [ART-07A1 exact membership contract](../WS-ART-001/WS-ART-001-07A1.md).
   REV-04A Review-source storage is also complete; neither step activates human review.
2. Continue hidden claim/revision behavior against canonical `allow_review`,
   copying the Submission policy version without a current-policy lookup.
3. TASK's early 04E1A source schema/detached facts and source-neutral accepted-
   effects types are delivered. After delivered REV-03B and REV-04A storage,
   REV-04B shared FinalAcceptance storage, REV-12A1 disabled fencing,
   ARCH-04E2-A exact source preparation, CON-07 hidden participation and REV-04C
   hidden FinalAcceptance/TASK/CON composition are delivered. 04E2-B now requires
   the actual routing AUTH event on the same strict input and supplies database
   complete-set closure and shared audit/outbox. Production readiness for the
   scoped lifecycle manifest remains a later gate. This foundation
   can precede human runtime: ARCH-04E uses it for false/pass acceptance without
   live queues, leases or decisions. REV-12A4A extends the same REV-12A1
   controller with scoped Operator transitions. Root/ordinal/cutoff custody is
   required before fulfillment admission, not before contribution acceptance.
   Human decision composition later adds Review/reviewer participation and
   invokes that same acceptance sequence on accept, not a second implementation.
4. Activate public claim/decision behavior only after exact AUTH/ART/CON gates.

## Preserved history

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).
These verbatim records preserve completed work and original proposals; where
pending sequencing conflicts, the current dependency contract above governs.
