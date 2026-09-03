# Workstream PR Trust Bundle

## Chunk

`WS-AUTH-001-12F1` - Submission Policy Authority Foundation

## Goal

Install exact PREP, replay, provenance, audit, and transaction custody needed by
12F2-12F4 without activating any submission-policy mutation action or changing
route, worker, or product behavior.

## What changed

- Extended the typed submission-policy authorization context with exact
  operation, request, policy, setup, compiler, catalogue, and output facts.
- Added whole-context PREP equality and canonical resource-digest binding.
- Added flush-only human/fixed-service replay reservation and typed completion.
- Added migration 0057 nullable provenance, replay constraints, immutable
  completion, deferred product/evidence custody, and guarded downgrade.
- Aligned kernel, audit schema, and database evidence vocabulary for the future
  exact submission-policy mutation resource.
- Added focused unit, PostgreSQL convergence, migration, audit, documentation,
  and per-file coverage proof.

## Scope and behavior

- No action is activated.
- No API route, Celery worker, agent call, or product-policy writer changes.
- Historical product rows remain readable with all authority provenance null.
- 12F2 owns manual create/update, 12F3 owns fixed-service derive, and 12F4 owns
  approval plus effective/pre-submit output creation.

## Evidence

```text
Ruff app/tests/scripts: passed
AUTH exact selector: 3 passed
Replay/service unit selector: 2 passed
CI lane contract: 33 passed
Focused per-file coverage: repository 92.31%, service 94.74%, total 93.75%
Semantic collection: 3,277 tests
Stale authorization docs: passed
Markdown links: passed
git diff --check: passed
```

PostgreSQL and Alembic selectors require `WORKSTREAM_TEST_DATABASE_URL` and are
delegated to the hosted Backend matrix rather than the user's slow local host.

## Acceptance proof

- [x] All submission-policy mutation actions remain planned/unavailable.
- [x] PREP binds the exact typed context and computed resource digest.
- [x] Human and fixed-service replay namespaces are disjoint and exact.
- [x] Completion uses operation UUID plus the complete immutable namespace.
- [x] Product provenance, replay completion, and allowed evidence are linked by
      deferred database custody.
- [ ] Historical null provenance survives upgrade and empty roundtrip (hosted
      Backend result pending on the corrected exact head).
- [ ] Pending replay and admitted audit evidence block downgrade (hosted
      Backend result pending on the corrected exact head).
- [x] New subsystem files have a non-weakened hosted 90 percent coverage gate.

## Internal review

Architecture, security, QA, senior engineering, test delta, CI integrity,
documentation, and reuse/dedup completed with no blocking findings. Product/ops
review passed after approval/output provenance immutability was added.

## Remaining risk and follow-up

- Hosted PostgreSQL migration/custody tests and repository-wide aggregate
  coverage must pass on the exact pushed head.
- Full real-writer fault injection is intentionally proved in 12F2-12F4 because
  this foundation activates no product writer.

## Human review focus

- Zero activation and absence of route/worker behavior changes.
- Full human/service replay namespace and single completion transition.
- Deferred custody across policy/effective/pre-submit rows and AUTH evidence.
- Historical all-null provenance and downgrade refusal predicates.

## Human merge ownership

- [ ] The user explicitly approved this specific PR for merge.
