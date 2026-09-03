# WS-ARCH-001 — Modular monolith boundaries

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: through 02H and CP04B.
- Intent: keep product modules behind explicit ports and composition roots.
- Current boundary: hidden ContributionPolicy behavior has durable custody;
  live activation remains separate.
- Next usable boundary: prepare CP05 against current code and specifications.
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
  draft/publication behavior are complete. CP05-CP09 remain: policy activation,
  validation, guide binding, task-attempt lineage, and clean legacy removal.
- ARCH-03A-03C then ARCH-04A-04F build current project/task readiness,
  post-submit checker/materialization, remediation, and `allow_review` before
  final public 02I cutover and later REV admission.
