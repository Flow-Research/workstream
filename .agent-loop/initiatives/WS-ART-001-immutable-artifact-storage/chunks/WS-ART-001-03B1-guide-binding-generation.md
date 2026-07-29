# Chunk Contract: WS-ART-001-03B1 - Guide Binding And Setup Generation

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after ART-03A and AUTH-04A

## Goal

Bind one exact verified `ArtifactContent` to one guide-source item and exact
setup run/generation without legacy cutover or activating fixed-service AUTH.

## Allowed Files

- project guide snapshot/item/setup-run models, one migration, repositories,
  and schemas;
- ART binding capability, exact canonical facts, guards, and hidden service;
- focused migration, binding, concurrency, stale-generation, and denial tests;
- related ART specification, plan evidence, and coverage configuration.

## Not Allowed

- provider reads, format parsing, extraction, agent invocation, legacy-field
  removal, submission/checker/review changes, or AUTH-owned availability edits.

## Acceptance Criteria

- an immutable binding references exact project, draft guide, snapshot, item,
  verified content, setup run, and monotonic setup generation;
- source-item metadata cannot claim or substitute content identity;
- one current binding exists per item/generation and replacement is explicit;
- missing, unverified, cross-project, cross-guide, wrong-run, or stale-generation
  content fails closed;
- concurrent binding produces one business effect;
- test-only fixed authority proves the hidden ART kernel's positive binding
  semantics while the composed live AUTH path proves deny-only before 04B;
- fresh prepared binding authority is consumed atomically with the binding when
  AUTH later activates it; the hidden real kernel denies before then;
- no provider I/O or human-authority inheritance occurs;
- changed subsystems remain at least 90% covered and repository coverage stays
  at least 78%.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_authorization.py tests/test_guide_artifacts.py -q --cov=app.modules.artifacts --cov=app.modules.projects --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

The exact PR head must pass hosted `Backend / test` and `Agent Gates / agent-gates`.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
