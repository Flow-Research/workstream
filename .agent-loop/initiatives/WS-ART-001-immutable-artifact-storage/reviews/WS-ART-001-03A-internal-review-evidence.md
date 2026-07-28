# Internal Review Evidence: WS-ART-001-03A

Reviewed against trusted main: `13d9d5d1f462ab48a4dda4405ab2f4c1a426e710`

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
