# Internal Review: WS-XINT-002-06A

## Result

Local L1 review passes after repair. Hosted database-backed tests, full
coverage, and external review remain required on the exact PR head.

## Blocking findings resolved

- Architecture/product review confirmed that immutable `TaskAssignment.id` is
  the assignment lineage token; replacement creates a new row/UUID and ART-04C1
  must lock the current active row before PREP. No parallel generation was
  invented.
- Security, QA, and senior review found that the original request had already
  been ZIP-inspected before authorization. The final design uses two-stage PREP:
  service/action/lifecycle/scope and scalar facts lock before inspection, then
  the same handle consumes the server-computed semantic manifest before scratch
  reservation or checker execution.
- QA found that manifest/change-gate equality alone did not prove the manifest
  came from the supplied inspection. The materializer now rebuilds the canonical
  manifest before final consumption and denies drift without touching authority
  or workspace.
- Security found missing bounded audit coordinates. Allowed decisions now carry
  the exact resource-context digest plus project and prepared-generation
  coordinates.
- Docs and product review found stale planned/owner wording. Canonical specs,
  operations, architecture, custody, chunk maps, and status now agree.
- Test-delta and reuse review found weak mocks and swapped protocol types. Tests
  now assert exact adapter arguments, pre-inspection ordering, same-handle
  two-stage flow, audit coordinates, manifest drift, replay, and real PREP
  behavior; the protocol matches prepare/final-consume types.

## Final reviewer results

- Architecture: pass with low ART-04C1 composition risk.
- Security/auth: pass with low ART-04C1 composition risk.
- Product/ops: pass with low ART-04C1 assignment-lock risk.
- QA: pass with low risk after manifest-drift repair.
- Senior engineering: pass with low risk after interface cleanup.
- CI integrity: pass with hosted database/coverage proof required.
- Reuse/dedup: pass after reusing the shared artifact PREP adapter.
- Test delta: pass after strengthened two-stage and audit tests.
- Docs: pass after runtime and custody reconciliation.

## Local verification

- Ruff and Ruff format on all touched backend/test files: passed.
- Focused catalogue, real PREP, adapter, two-stage materialization, denial,
  manifest-drift, and default-execution tests: 28 passed, 1 deselected.
- Lightweight agent gates: 11 passed.
- Stale Workstream wording, stale AUTH docs, stale ART contracts, Markdown links,
  and `git diff --check`: passed.
- Full database-backed coverage is intentionally assigned to hosted Backend CI;
  the local shell has no `WORKSTREAM_TEST_DATABASE_URL`.

## Scope confirmation

Only `artifact.pre_submit.checker_input.materialize` changes availability. No
contributor preparation, durable admission, Submission, post-submit,
checker-output, reviewer-packet, generic-read, route, migration, or Celery
payload capability is activated.
