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

Reviewed implementation commits:
`8c48c01e137f861210bccfbc6bfaa91f13b0a354` for the CodeRabbit correction and
`8b468881` for the behavior-preserving kernel coverage repair. The following
commit changes review evidence only; hosted checks must pass on that final
evidence head too.

- `cd backend && .venv/bin/ruff check app tests scripts`: passed.
- `cd backend && .venv/bin/pytest -q tests/test_audit.py
  tests/test_authorization.py -k 'action_aware_audit_input or guide_service or
  fixed_service_context or human_authority_cannot'`: 8 passed, 408 deselected.
- `cd backend && .venv/bin/pytest -q tests/test_artifact_architecture.py`: 20
  passed.
- `python3 scripts/check_stale_authorization_docs.py`: passed.
- `python3 scripts/check_stale_artifact_contracts.py`: passed.
- `python3 scripts/check_markdown_links.py`: passed.
- `git diff --check`: passed.
- Database-backed guide binding/materialization and full coverage remain assigned
  to hosted `Backend / test` because this local venv lacks Pillow and the local
  shell has no `WORKSTREAM_TEST_DATABASE_URL`.

## Corrective reviewer reruns

- Security/auth: pass with low risk; the binding handle remains intentionally
  process-local and caller-transaction-bound, while reading obtains fresh
  authority inside the materializer transaction.
- QA: pass with low risk; all CodeRabbit code findings are addressed and all
  review threads are resolved.
- Product/ops: pass after the PREP support and denial-restage documentation was
  corrected.
- Docs: runtime wording passes; this evidence now names the reviewed
  implementation head.
- Senior engineering: pass with low operational lock-duration risk deferred to
  ART worker tuning.
- Reuse/dedup: pass after consolidating the two guide action maps.
- Test delta: pass after adding scratch-cleanup and unchanged-incident-count
  assertions to the incident-write failure case.
- Security and QA re-reviewed `8b468881`: its consolidated terminal denial
  preserves `permission_not_granted` for known ART-internal actions and
  `action_unavailable` for other unsupported actions, without creating an allow
  path. Ruff and 15 focused behavior tests pass.

## Readiness dependency

Planning/scope PR #244 is merged and the runtime branch is rebased onto current
`main`. Hosted exact-head checks remain required before merge readiness.
Run `30749925248` proved all 2,841 semantic nodes but found
`authorization/kernel.py` at 89.93% against the unchanged 90% per-file gate.
The `8b468881` repair restores the kernel to its prior 584 executable statements
without exclusions or threshold changes; a fresh exact-head hosted run is
required.
