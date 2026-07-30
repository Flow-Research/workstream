# Chunk Contract: WS-ART-001-03B4 — Guide Sufficiency Continuation

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03B3B2,
03B3B3B-03B3B3D, and 03B3B4

## Goal

Continue the existing Celery project-setup workflow with complete verified,
same-generation canonical guide material and exact persisted provenance.

## Allowed Files

- existing project-setup Celery task/queue and setup-run generation fields;
- project service/repository and agent input schemas consuming typed canonical
  extraction records;
- in-place evolution or replacement of existing `GuideSourceMaterial` and
  `GuideSourceItemMaterial`; no parallel sufficiency-material model;
- sufficiency-report usage provenance; extraction models/migration remain owned
  by 03B3A and complex adapter provenance remains owned by 03B3B2-03B3B4;
- focused stale-delivery, completeness, incident, unsupported, broker replay,
  agent-input, persistence, cancellation, and coverage tests; related docs.

## Not Allowed

- bytes, extracted content, scratch paths/handles, prepared authorization, or
  credentials in Celery payloads; direct provider access; raw binary/excerpts
  as authoritative input; policy derivation after incomplete extraction;
  legacy-field removal; AUTH availability edits.

## Acceptance Criteria

- project-setup Celery payload is exactly project, guide, snapshot, setup run, and
  setup generation identifiers;
- the project-setup executor reloads and revalidates current
  project/guide/snapshot/run/generation,
  complete bindings, content, and extraction provenance before agent invocation
  and again before report commit;
- all required items must have successful policy-compatible extraction;
- artifact incident, missing/corrupt/stale/unsupported/failed extraction stops
  setup with an internal status and creates no insufficiency decision;
- agent input is bounded canonical content only, never raw binaries or caller
  excerpts, and reports preserve exact content/extraction provenance;
- source content is explicitly delimited/labeled as untrusted data, supplies no
  tools/provider/secret authority, and prompt-injection fixtures cannot override
  system/developer policy or the typed sufficiency output contract;
- `setup_blocked` exposes the stable redacted error codes and remediation defined
  by D46 for `unsupported`, `ambiguous`, `malformed`, `limit_exceeded`,
  `parser_failure`, `cancelled`, and `artifact_incident`, with bounded Operator
  incident reference only for ART incidents;
- canonical agent material is capped at 12 MiB; an exact-boundary assembly may
  proceed, a one-over assembly records `guide_source_limit_exceeded`, and no
  agent call or partial report occurs;
- duplicate or stale Celery execution cannot create or overwrite current output;
- test-only fixed authority proves the complete hidden pipeline while composed
  live binding/read remains deny-only until AUTH-04B;
- changed subsystems remain at least 90% covered and repository coverage stays
  at least 78%.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_project_setup.py tests/test_guide_artifacts.py tests/test_guide_extraction.py tests/test_project_agents.py -q --cov=app --cov-report=term-missing --cov-fail-under=0)
(cd backend && .venv/bin/coverage report --precision=2 --fail-under=78)
(cd backend && .venv/bin/coverage report --include='app/modules/projects/*,app/*ers/project_setup.py' --precision=2 --fail-under=90)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

The exact PR head must pass hosted `Backend / test` and `Agent Gates / agent-gates`.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
