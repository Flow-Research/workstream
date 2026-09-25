# WS-ARCH-001 — Modular monolith boundaries

Current remaining design: [acyclic dependency and ownership contract through
allow_review](planning/PLAN.md#current-dependency-contract).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: through 02H, [CP05](WS-ARCH-001-CP05.md), [CP06](WS-ARCH-001-CP06.md), [CP07](WS-ARCH-001-CP07.md), [ARCH-03A](WS-ARCH-001-03A.md), and
  [ARCH-04A consolidation](WS-ARCH-001-04A.md) canonical post-submit contracts/conformance.
- Intent: keep product modules behind explicit ports and composition roots.
- Current boundary: one CHECKERS catalogue, compiler/parser and implementation
  per checker ID serve active policy consumers; production post-submit phase
  execution remains unavailable.
- Next usable boundary: public guide activation and approved-guide intake integration.
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
  The production post-submit phase remains unavailable until its separately
  sequenced ART/CHECKER/AUTH execution boundaries land.
- Governing sources: `docs/architecture_lockdown.md`, accepted ADRs, code, and
  architecture tests.
- Preserve: no concrete-adapter imports in product services and no duplicate
  factory or authorization paths.

## Delivered and remaining

- Canonical module registry, frozen general/AUTH edge ledgers, CI enforcement,
  owner-facing TASK/PROJECT/CHECKER/ART APIs, hidden atomic Submission
  composition, and exact contributor/binding activation are merged through
  02H; the public route remains unchanged.
- Adapter-binding behavior and activation and hidden ContributionPolicy
  draft/publication behavior and exact Finance Authority are complete.
  CP06 exact selected-policy validation and CP07 hidden complete-guide activation
  and [AUTH-12H live authority](../WS-AUTH-001/WS-AUTH-001-12H.md) are complete.
  [CP08](WS-ARCH-001-CP08.md) exact task-attempt lineage and minimal writers are complete.
  CP09 scoped economic removal remains.
  [CP07A](WS-ARCH-001-CP07A.md) supplies the cross-owner authority lock repair
  and binding audit schema parity required before guide composition.
  CP09 physical removal follows zero legacy consumers, including checker/public
  Submission cutover; it is not on the `allow_review` critical path.
- Consolidated ARCH-04A supplies one current catalogue, immutable phase contracts and
  registered structural conformance, not durable runs. Following CP08, ARCH-03B/03C and ARCH-04B-04F build task readiness,
  post-submit checker/materialization, remediation, and `allow_review` before
  final public 02I cutover and later REV admission.
