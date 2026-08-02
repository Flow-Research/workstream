# Internal Review: WS-XINT-002-04B

## Result

Provisional local PASS after repair. Merge readiness remains pending hosted
full coverage and database-backed guide tests on the exact PR head.

## Blocking findings resolved

- Security and QA found that the first read adapter committed PREP evidence and
  released lineage locks before provider access. The materializer now locks the
  exact guide, snapshot, item, setup run/generation, binding, content, replica,
  namespace, verification job, and receipt through PREP consumption, provider
  materialization, classification, and the classification write in one root
  transaction.
- QA found missing exact resource-digest evidence. Both new resource types now
  persist `resource_context_digest` in bounded authorization audit facts.
- Test-delta review found missing human/Admin and binding-input negatives. Tests
  now prove humans cannot substitute for either fixed service and wrong content
  or logical role creates no binding or authority consumption.
- Product/docs review found stale catalogue and ART availability counts. The
  custody ledger, authorization spec, artifact spec, and operations runbook now
  agree on 71 permissions, 96 actions, 43 active, 53 planned, and 16 remaining
  planned ART actions.
- Senior/reuse review found cleanup and duplicated fixed-service lifecycle
  plumbing. Prepare failures now always close capabilities, and both guide and
  foundation ART adapters share one service-context loader and revalidator.

## Final reviewer results

- Security/auth: pass with low documentation risk, corrected.
- Architecture: pass with low risk.
- QA/test: pass with low operational risk.
- Senior engineering: pass with low operational risk.
- Product/ops: pass.
- CI integrity: pass with low hosted-test dependency.
- Docs: pass with low wording risk, corrected.
- Reuse/dedup: pass with low registry-map drift risk.
- Test delta: pass with low risk.

## Verification evidence

Reviewed implementation commit: pending the CodeRabbit corrective commit.

- Ruff over `backend/app`, `backend/tests`, and `backend/scripts`: passed.
- Artifact architecture tests: 20 passed.
- Focused AUTH catalogue, custody, fixed-service, exact-fact, human-denial,
  replay, and evidence tests: passed.
- Stale AUTH docs, stale ART contracts, Markdown links, and `git diff --check`:
  passed.
- Database-backed guide binding/materialization and full coverage remain assigned
  to hosted `Backend / test` because this local venv lacks Pillow and the local
  shell has no `WORKSTREAM_TEST_DATABASE_URL`.

## Readiness dependency

Planning/scope PR #244 is merged and the runtime branch is rebased onto current
`main`. Hosted exact-head checks remain required before merge readiness.
