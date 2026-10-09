# WS-ARCH-001 — Modular monolith boundaries

[REV-12A4A](../WS-REV-001/WS-REV-001-12A4A.md) adds internal Operator-controlled lifecycle transitions and current-generation terminal replay. New acceptance effects require LIVE; source AUTH custody and production routing remain unavailable. Conditional award facts stay atomic, while fulfillment admission, payment delivery and their root/cutoff machinery remain deferred until a successor manifest enables them.

[ARCH-04E1B-B5](WS-ARCH-001-04E1BB5.md) delivers shared bounded evaluation content and rejects unrepresentable ZIP input before durable admission. ARCH-04E1B-B6 reuses this projection in atomic Submission/dispatch creation with exact AUTH receipts and select-only replay. B7 adds hidden request delivery with exact invocation fencing; complete authorized outcomes precede completion-handler wiring. Production registration remains unavailable.

Delivery priority: [first complete contributor milestone](planning/PLAN.md#first-complete-contributor-milestone). Use its five remaining outcome groups and end-to-end exit proof when selecting the next bounded change; live human review/revision and external integration are later work.

[ARCH-04E1B-B4](WS-ARCH-001-04E1BB4.md) binds Submission summary and attestation to the packet retained by intake, including database custody. B6 now commits the initial reservation and request event with exact receipts and fresh-authorized replay. B7 supplies hidden request delivery; complete authorized outcomes precede completion-handler wiring.

[ARCH-04E1B-B3](WS-ARCH-001-04E1BB3.md) retains the inspected ZIP manifest in immutable ART evidence and returns verified file metadata on admission consumption. ARCH-04E1B-B6 commits that content, exact authority, generation-one reservation and shared request event with each new Submission. No delivery handler or routing authority is activated.

[ARCH-04E1B-B2](WS-ARCH-001-04E1BB2.md) supplies exact source preparation through
TASK, CHECKERS and historical PROJECTS policy facts. It stages only the existing
routing request; proposed source facts have no fabricated creation timestamp.
Remaining handlers, source publication, current pointers and authority/effect
activation are still required. False composition must acquire its REV lifecycle
fence before TASK and revalidate policy under TASK custody; true admission
remains independent of that fence.

[AUTH-19A](../WS-AUTH-001/WS-AUTH-001-19A.md) delivers inert exact source/receipt contracts and the
planned router identity. ARCH-04E1B-A delivers caller-owned routing-request and
future source-identity reservation. ARCH-04E2-A now delivers strict hidden
resource/preparation matching and a nominal fixed-router adapter through canonical
PREP. The action remains planned and unavailable, so it issues no handle, allow or
receipt and writes no source or effect. The selected automated path now has
CON-07 hidden submitter participation and complete frozen award-set staging/replay.
[REV-04C](../WS-REV-001/WS-REV-001-04C.md) now composes FinalAcceptance, TASK terminal effects and CON participation
inside one hidden caller-owned transaction. Mandatory exact AUTH receipt input,
database complete-set enforcement, currentness race proof, shared audit/outbox,
the reviewed scoped lifecycle manifest remain
required before production consumption. Neither phase may
commit a standalone allow. The first durable receipt must commit with its full
governed consequence. Hidden handlers and activation follow as 04E1B-B/04E2-B,
then live 04E3; true admission does not depend on CON/shared acceptance.

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
  Automatic request delivery/routing and acceptance remain unavailable.
- Delivered storage boundary: hidden [ARCH-04B2 checker-output custody](WS-ARCH-001-04B2.md), following hidden input materialization (ARCH-04B). Typed store, byte-free recovery and flush-only verified binding exist; the CHECKERS zero-slot reservation reader is implemented; output write/bind authority remains unavailable.
- Delivered source boundary: [ARCH-04E1A routing-source facts](WS-ARCH-001-04E1A.md)
  follow [ARCH-04D2](WS-ARCH-001-04D2.md) exact input, execute and finalize
  authority. The source table has no routing handler, current pointer or routing
  authority. REV-04C supplies the hidden acceptance-effects participant. False is proven only as
  a scalar DTO value because activation still rejects it.
- Delivered preparation boundary: [ARCH-04E2-A](WS-ARCH-001-04E2A.md) binds
  the reserved request, exact source and branch consequence through canonical
  AUTH/PREP. True binds only TASK `evaluation_pending -> review_pending`; false
  binds exact `TaskAcceptedEffectsRequest` for future shared FinalAcceptance.
  The planned action yields no executable handle, receipt, publication or effect.
- Delivered storage: [REV-03B](../WS-REV-001/WS-REV-001-03B.md) freezes exact
  lease packets with normalized live guide ingests; no resolver or byte authority.
  [REV-04A](../WS-REV-001/WS-REV-001-04A.md) adds complete immutable Review, findings, resolutions and completed request storage; no decision runtime.
  [REV-04B](../WS-REV-001/WS-REV-001-04B.md) adds shared FinalAcceptance source
  storage, without AUTH receipt custody or a production writer.
- Next usable boundary: ARCH-04E2-B completes the authorized outcome operation
  before completion-handler wiring over delivered B7 request delivery and B6
  atomic Submission/dispatch. It proves genuine authority
  with exact receipt/database/effect closure under a valid scoped controller
  generation for false. Prove ARCH-04F remediation before production false-policy
  enablement and ARCH-04E3 live composition. True handoff remains independent of
  CON/shared acceptance. Public intake and the first-layer drill follow the
  [governing sequence](planning/PLAN.md#first-complete-contributor-milestone).
  Output-file authority remains unavailable for the zero-output catalogue.
  [AUTH-18](../WS-AUTH-001/WS-AUTH-001-18.md) delivers public manager activation
  context and exact guide activation using the existing CP07 operation.
  [CP05A](WS-ARCH-001-CP05A.md) supplies public Finance policy administration and recoverable draft selectors.
  [ARCH-03C7](WS-ARCH-001-03C7.md) exposes bounded exact-authorized task history.
  [ARCH-03C6](WS-ARCH-001-03C6.md) exposes distinct exact-authorized locked-context reads.
  [ARCH-03C5](WS-ARCH-001-03C5.md) exposes exact-authorized task detail and requirements.
  [ARCH-03C4](WS-ARCH-001-03C4.md) exposes the three exact-authorized public queues.
  [ARCH-03C3](WS-ARCH-001-03C3.md) supplies exact-authorized manager task
  create/screen/release with atomic audit and durable replay.
  [ARCH-03C2](../WS-ARCH-001/WS-ARCH-001-03C2.md) supplies atomic publication and
  registered assignment delivery with enforced prefork topology. ARCH-03C1 supplies exact fixed-service
  reconciliation authority and decision-bound release receipts. ARCH-03B9 supplies the
  hidden exact-assignment operation and transaction fence. AUTH-OUTBOX-02 delivers
  shared live dispatcher authority, phase audit custody and Celery recovery after
  CON-02B delivery mechanics. This follows
  completed [ARCH-03B8](WS-ARCH-001-03B8.md) hidden task audit evidence and [ARCH-03B7](WS-ARCH-001-03B7.md) requirements projections and [ARCH-03B6](WS-ARCH-001-03B6.md) locked-context projections and [ARCH-03B5](WS-ARCH-001-03B5.md) current contributor/manager work context and ARCH-03B4 hidden contributor/management task detail, ARCH-03B3 hidden management/operational queues and ARCH-03B2 contributor-ready queue facts, ARCH-03B1 detached metadata and CP08 lineage
  and minimal writers and ARCH-03A internal guide context, following delivered CP07 activation and AUTH-12H live manager authority. POL-04B unified setup, POL-05/06
  manager operations and POL-07B internal phase composition are delivered.
  Exact hidden post-submit execution authority is delivered; automatic request delivery,
  routing and public intake remain subsequent boundaries.
- Governing sources: `docs/architecture_lockdown.md`, accepted ADRs, code, and
  architecture tests.
- Preserve: no concrete-adapter imports in product services and no duplicate
  factory or authorization paths.

Delivered [REV-12A1](../WS-REV-001/WS-REV-001-12A1.md) supplies only disabled
generation-zero controller storage and transaction locking. Acceptance-source
AUTH custody, database closure, currentness proof and authorized activation remain
separate work.

This is delivery priority, not a prerequisite of true human admission. Both
routing branches have delivered request reservation 04E1B-A → delivered AUTH preparation 04E2-A → hidden handlers 04E1B-B → activation 04E2-B → live 04E3; true routing
can proceed after its own prerequisites without CON/shared acceptance or
scoped lifecycle activation. False routing adds those requirements. Human final
acceptance later uses the same authorized shared acceptance/CON operation.

ARCH-04E1B-B1 delivers TASK-before-CHECKERS reservation/current-read custody
and ordered review admission INSERTs, including intermediate admission waits,
terminal read-only replay and both mechanical race controls. The
next steps after ARCH-04E1B-B6 atomic Submission/dispatch are
remaining 04E1B-B handlers and full authorized currentness proof;
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
