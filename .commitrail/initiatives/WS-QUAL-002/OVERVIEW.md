# WS-QUAL-002 — Behavior ownership catalogue

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: catalogue foundation and local context evidence.
- Intent: map important behavior to authoritative implementation and proof
  without turning raw mutation output into ownership truth.
- Next usable boundary: populate subsystem ownership before completeness or
  changed-line-aware mutation enforcement.
- Governing sources: `.ci/behavior-ownership/`, backend scripts, tests, and
  `CONTRIBUTING.md`.
- Preserve: current coverage floors; candidate output remains advisory;
  unchanged executable lines cannot block declaration-only changes.

## Delivered and remaining

- Catalogue schema, deterministic partition/inventory/candidate generation,
  fail-closed validation, and local digest-bound coverage-context evidence are
  merged; hosted mutation enforcement remains retired.
- Populate ownership records by subsystem before enabling completeness or
  changed-line mutation checks. Backend semantic lanes and the 78/90 percent
  coverage floors remain authoritative meanwhile.
