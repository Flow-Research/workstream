# WS-ARCH-001 — Modular monolith boundaries

[REV-12A4A](../WS-REV-001/WS-REV-001-12A4A.md) adds internal Operator-controlled lifecycle transitions and current-generation terminal replay. New acceptance effects require LIVE; 04E2-B supplies hidden source AUTH custody, while production routing remains unavailable. Conditional award facts stay atomic, while fulfillment admission, payment delivery and their root/cutoff machinery remain deferred until a successor manifest enables them.

[ARCH-04E1B-B5](WS-ARCH-001-04E1BB5.md) delivers shared bounded evaluation content and rejects unrepresentable ZIP input before durable admission. ARCH-04E1B-B6 reuses this projection in atomic Submission/dispatch creation with exact AUTH receipts and select-only replay. B7 delivers hidden request delivery with exact invocation fencing; 04E2-B supplies complete authorized outcomes; B8 supplies hidden completion delivery; remediation is next. Production registration remains unavailable.

Delivery priority: [first complete contributor milestone](planning/PLAN.md#first-complete-contributor-milestone). Use its four remaining outcome groups and end-to-end exit proof when selecting the next bounded change; live human review/revision and external integration are later work.

[ARCH-04E1B-B4](WS-ARCH-001-04E1BB4.md) binds Submission summary and attestation to the packet retained by intake, including database custody. B6 now commits the initial reservation and request event with exact receipts and fresh-authorized replay. B7 supplies hidden request delivery; 04E2-B supplies complete authorized outcomes; B8 supplies hidden completion delivery; remediation is next.

[ARCH-04E1B-B3](WS-ARCH-001-04E1BB3.md) retains the inspected ZIP manifest in immutable ART evidence and returns verified file metadata on admission consumption. ARCH-04E1B-B6 commits that content, exact authority, generation-one reservation and shared request event with each new Submission. No delivery handler or routing authority is activated.

[ARCH-04E1B-B2](WS-ARCH-001-04E1BB2.md) supplies exact source preparation through
TASK, CHECKERS and historical PROJECTS policy facts. It stages only the existing
routing request; proposed source facts have no fabricated creation timestamp.
04E2-B now publishes the authorized source and complete outcome. B8 supplies hidden completion delivery; production activation remains required. False composition must acquire its REV lifecycle
fence before TASK and revalidate policy under TASK custody; true admission
remains independent of that fence.

[ARCH-04E2-B](WS-ARCH-001-04E2B.md) delivers the hidden authorized outcome operation.
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

Current remaining design: [acyclic dependency and ownership contract through
allow_review](planning/PLAN.md#current-dependency-contract).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
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

- Completed boundary: through 02H, [CP05](WS-ARCH-001-CP05.md), [CP06](WS-ARCH-001-CP06.md), [CP07](WS-ARCH-001-CP07.md), [ARCH-03A](WS-ARCH-001-03A.md), and
  [ARCH-04A consolidation](WS-ARCH-001-04A.md) canonical post-submit contracts/conformance.
- Intent: keep product modules behind explicit ports and composition roots.
- Current boundary: one CHECKERS catalogue, compiler/parser and implementation
  per checker ID serve active policy consumers; hidden post-submit execution has
  exact fixed-service authority. ARCH-04E1A adds immutable route-neutral TASK
  source storage, detached facts and source-neutral accepted-effects types.
  Production request/completion delivery and routing remain unregistered; hidden
  request delivery and authorized outcomes are implemented.
- Delivered storage boundary: hidden [ARCH-04B2 checker-output custody](WS-ARCH-001-04B2.md), following hidden input materialization (ARCH-04B). Typed store, byte-free recovery and flush-only verified binding exist; the CHECKERS zero-slot reservation reader is implemented; output write/bind authority remains unavailable.
- Delivered source boundary: [ARCH-04E1A routing-source facts](WS-ARCH-001-04E1A.md)
  follow [ARCH-04D2](WS-ARCH-001-04D2.md) exact input, execute and finalize
  authority. The source table has no routing handler, current pointer or routing
  authority. REV-04C supplies the hidden acceptance-effects participant. 04E2-B proves hidden false outcomes against exact seeded policy lineage; public
  false-guide activation still rejects the unsupported production path.
- Delivered preparation boundary: [ARCH-04E2-A](WS-ARCH-001-04E2A.md) binds
  the reserved request, exact source and branch consequence through canonical
  AUTH/PREP. True binds only TASK `evaluation_pending -> review_pending`; false
  binds exact `TaskAcceptedEffectsRequest` for future shared FinalAcceptance.
  04E2-B now consumes that preparation in the complete authorized outcome.
- Delivered storage: [REV-03B](../WS-REV-001/WS-REV-001-03B.md) freezes exact
  lease packets with normalized live guide ingests; no resolver or byte authority.
  [REV-04A](../WS-REV-001/WS-REV-001-04A.md) adds complete immutable Review, findings, resolutions and completed request storage; no decision runtime.
  [REV-04B](../WS-REV-001/WS-REV-001-04B.md) adds shared FinalAcceptance source
  storage, without AUTH receipt custody or a production writer.
- Next usable boundary: prove 04F
  remediation, 04E3 live composition and false-guide readiness, public intake
  and the first-layer drill. True handoff remains independent of REV/CON;
  live human review/revision and payment delivery stay deferred.
- Governing sources: `docs/architecture_lockdown.md`, accepted ADRs, code, and
  architecture tests.
- Preserve: no concrete-adapter imports in product services and no duplicate
  factory or authorization paths.

REV-12A4A supplies scoped lifecycle transitions on the existing REV fence.
04E2-B supplies exact source AUTH custody and complete database/effect closure.
Production composition and false-guide activation remain separate work.

This is delivery priority, not a prerequisite of true human admission. Both
routing branches have delivered request reservation 04E1B-A → delivered AUTH preparation 04E2-A → delivered authorized outcomes 04E2-B → completion delivery 04E1B-B → live 04E3; true routing
can proceed after its own prerequisites without CON/shared acceptance or
scoped lifecycle activation. False routing adds those requirements. Human final
acceptance later uses the same authorized shared acceptance/CON operation.

ARCH-04E1B-B1 delivers TASK-before-CHECKERS reservation/current-read custody
and ordered review admission INSERTs, including intermediate admission waits,
terminal read-only replay and both mechanical race controls. The
delivered B6 atomic Submission/dispatch and B8 completion delivery reuse
04E2-B outcomes; remediation is next and
no handler or action is activated by this prerequisite.

## Delivered and remaining

- Canonical module registry, frozen general/AUTH edge ledgers, CI enforcement,
  owner-facing TASK/PROJECT/CHECKER/ART APIs, hidden atomic Submission
  composition, and exact contributor/binding activation are merged through
  02H; the public route remains unchanged.
- Internal adapter-binding behavior and authority, public ContributionPolicy
  administration and exact Finance Authority are complete.
  CP06 exact selected-policy validation, CP07 complete-guide activation,
  [AUTH-12H live authority](../WS-AUTH-001/WS-AUTH-001-12H.md) and
  [AUTH-18 public manager activation](../WS-AUTH-001/WS-AUTH-001-18.md) are complete.
  [CP08](WS-ARCH-001-CP08.md) exact task-attempt lineage and minimal writers are complete.
  [Physical economic cleanup](../../changes/remove-obsolete-task-payment-policy.md)
  is complete through migration 0023; historical CP09 coordination is superseded.
  [CP07A](WS-ARCH-001-CP07A.md) supplies the cross-owner authority lock repair
  and binding audit schema parity required before guide composition.
  The cleanup refuses retained economic facts and does not wait for public
  Submission cutover or activate acceptance/fulfillment authority.
- Consolidated ARCH-04A supplies one current catalogue, immutable phase contracts and
  registered structural conformance, not durable runs. Following CP08, ARCH-03B/03C and ARCH-04B-04F build task readiness,
  post-submit checker/materialization, remediation, and `allow_review` before
  final public 02I cutover and later REV admission.
