# WS-ARCH-001 — Modular monolith boundaries

Current remaining design: [acyclic dependency and ownership contract through
allow_review](planning/PLAN.md#current-dependency-contract).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: through 02H, [CP05](WS-ARCH-001-CP05.md), [CP06](WS-ARCH-001-CP06.md), and
  [ARCH-04A consolidation](WS-ARCH-001-04A.md) canonical post-submit contracts/conformance.
- Intent: keep product modules behind explicit ports and composition roots.
- Current boundary: one CHECKERS catalogue, compiler/parser and implementation
  per checker ID serve active policy consumers; production post-submit phase
  execution remains unavailable.
- Next usable boundary: CP07 guide binding, then AUTH-12H activation, using
  completed CP06 selected ContributionPolicy validation. POL-04B unified setup, POL-05/06
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
  CP06 exact selected-policy validation is complete. CP07-CP09 remain:
  hidden guide binding/activation and task-attempt lineage.
  CP09 physical removal follows zero legacy consumers, including checker/public
  Submission cutover; it is not on the `allow_review` critical path.
- Consolidated ARCH-04A supplies one current catalogue, immutable phase contracts and
  registered structural conformance, not durable runs. ARCH-03A-03C then ARCH-04B-04F build project/task readiness,
  post-submit checker/materialization, remediation, and `allow_review` before
  final public 02I cutover and later REV admission.
