# Internal Review Evidence: WS-ART-001-03A

Reviewed against trusted main: `033654ac129eea05e0f00176257c94e6b3447dcf`

Reviewed at: `2026-07-28`

## Candidate

Hidden, fail-closed guide-source byte ingest through the existing bounded
scratch, admission, immutable put, verification, and publication path. The
guide ingest action remains planned and unavailable pending AUTH 04A.

## Deterministic Evidence

- changed-file Ruff and Python compilation: PASS;
- `tests/test_guide_artifacts.py`: PASS, 9 tests;
- artifact architecture tests: PASS, 11 tests;
- isolated PostgreSQL migration replay/populated downgrade refusal: PASS;
- isolated PostgreSQL admission, lineage mismatch, transaction boundary, and
  confirmed-missing replay/capacity reacquisition: PASS;
- stale wording, artifact/auth contract, Markdown link, diff, and lightweight
  agent gates: PASS;
- full repository Ruff currently reports four unchanged `app/core/config.py`
  F821 findings already present on trusted main; no ART file fails Ruff;
- full sharded suite and 78/90 percent coverage remain hosted GitHub gates to
  avoid loading the user's machine.
- initial hosted Backend run `30360132709` exposed missing semantic-lane
  ownership for the new test module; the repair assigns it to
  `shared_foundations`, strengthens the lane regression, and passes canonical
  collect-only validation.
- hosted rerun `30360448433` reached lane execution and identified only the
  expected-schema fingerprint stale after the SHA-256 constraint was added;
  the guard now records GitHub's canonical migrated-schema fingerprint.
- hosted run `30360906515` executed 1,618 tests with 1,615 passing and exposed
  three stale fixtures for complete guide lineage/staged facts. Those fixtures
  now exercise the intended exact-lineage boundaries; production is unchanged.
- hosted run `30361748346` passed all shared (1,618), project (236), and task
  (217) tests. Schema passed 91/92; the sole failure was a multi-command asyncpg
  test seed, now split into six transactional statements with isolated proof.
- hosted run `30363061162` again passed all shared (1,618), project (236), and
  task (217) tests. Schema passed 91/92; its sole failure was that the migration
  fixture did not create the identity link now required for every human actor.
  The fixture now creates the canonical active, verified link, and the exact
  isolated migration proof passes.
- hosted run `30364425613` passed all four semantic lanes, the API E2E proof,
  and repository coverage. The unchanged 90% artifact-foundation gate measured
  89.77%; focused production-path tests now cover absent/missing/resolved replay
  selection and fail-closed missing PREP transaction behavior without changing
  production code or the threshold.
- The final rebase onto merged AUTH 11B preserved both the new project-read
  authorization dependencies and hidden ART ingest wiring. Bounded senior,
  QA, security/auth, and CI-integrity reconciliation reviews passed.
- rebased hosted run `30366469273` passed all semantic lanes, API E2E, and
  repository coverage, and raised artifact-foundation coverage to 89.87%.
  Additional focused proofs cover rejection before preparation for an invalid
  guide logical role and scratch cleanup when PREP commit itself fails.
- hosted run `30367711119` passed all semantic lanes, API E2E, and repository
  coverage, raising artifact-foundation coverage to 89.98%. A final focused
  boundary proof exercises fail-closed rejection of partial guide lineage
  claims; production code and the 90% gate remain unchanged.

## Reviewer Results

| Reviewer | Result | Blocking findings |
|---|---|---|
| senior engineering | PASS WITH LOW RISKS | none |
| architecture | PASS WITH LOW RISKS | none |
| QA/test | PASS WITH LOW RISKS | none |
| security/auth | PASS WITH LOW RISKS | none |
| product/ops | PASS | none |
| reuse/dedup | PASS WITH LOW RISKS | none |
| CI integrity | PASS WITH LOW RISKS | none |
| test delta | PASS | none |
| docs | PASS | none |

## Material Repairs

- replaced raw durable authorization with the merged opaque PREP handle;
- kept preflight, final lineage/fact consumption, capacity, and put intent in
  one root transaction, with provider I/O only after commit;
- composed post-commit writes through the activated fixed-service put resolver;
- made confirmed-missing exact replay reacquire capacity and write again;
- concealed missing/malformed idempotency metadata without invoking ingest;
- refused populated migration downgrade and added the projects 90% CI gate.

## Accepted Low Risks

- The explicit PREP context-manager handoff is delicate but bounded and covered
  for active/committed ordering and scratch cleanup.
- Lower-level admission tests use process-local fake opaque handles; production
  uses the merged issuer-local PREP implementation.

Valid findings addressed: yes

Open sub-agent sessions: none
