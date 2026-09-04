# WS-ARCH-001-02G Evidence

## Outcome

Activates only `artifact.submission_bundle.prepare`, retaining historical
`WS-XINT-002-05A` catalogue custody. The active path uses the existing opaque
AUTH PREP service for project-scoped submitter revalidation before byte intake
and exact final-fact consumption before capacity, durable intent, or provider
I/O. TASK Submission creation and artifact binding remain unavailable.

## Local evidence

- Ruff passed for all changed AUTH, ART adapter, and focused test files.
- Focused submission admission and AUTH boundary tests passed: 100 tests.
- Focused real PREP full-fact, mismatch, and replay proof passed.
- Module boundary validation and architecture tests passed without growing the
  AUTH private-import ledger.
- Stale AUTH/ART wording, atomic chunk state, Markdown links, and diff checks
  passed.
- The PostgreSQL end-to-end test now composes the real contributor preparation
  authority; GitHub Actions owns its execution and the full coverage gate.

## Human review focus

- Preliminary actor concealment and project-scoped submitter revalidation occur
  before request bytes are read.
- Final preparation binds every durable-intent fact in the same root database
  transaction and is consumed before capacity or provider work.
- No adjacent action, permission, route, TASK command, or fixed binding action
  becomes active.
