# Chunk Contract: WS-ART-001-04A4 - Legacy Standalone Precheck Removal

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after PLAN4 approval

Artifact contract phase: `upload_admission`

## Goal

Remove the independently invocable caller-owned submission-precheck API before
the authoritative server-derived catalogue path is installed. This is a clean
cut with no replacement route in this chunk.

## Allowed Files

- checker router/service/schema removal for
  `/api/v1/tasks/{task_id}/submission-precheck`;
- removal of pre-submit-only legacy request/response helpers and registry
  membership after proof that no durable/post-submit caller uses them;
- OpenAPI, route-negative, import/reachability, docs, and focused tests;
- CI only to preserve exact existing coverage gates.

## Not Allowed

- new catalogue, checker execution, ZIP/scratch changes, provider I/O, durable
  evidence/admission/Submission, compatibility alias, redirect, or fallback;
- removal of compiler primitives or durable/post-submit checker behavior needed
  by 04B1/04B3 and later ART-06;
- AUTH availability/grant changes or public replacement endpoints.

## Acceptance Criteria

- route and OpenAPI schema are absent and return the canonical not-found result;
- caller-owned `artifact_hash_manifest`, package/provider references, and legacy
  packet shape cannot reach a pre-submit service through HTTP or internal public
  methods;
- no alias, redirect, compatibility parser, or second registry survives;
- constrained compiler primitives and durable post-submit runner behavior remain
  available for 04B1 reuse;
- import/reachability tests prove no product composition root exposes the old
  path;
- no artifact, task, Submission, checker-run, audit, or AUTH behavior is added;
- focused subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent.

## Verification

```bash
(cd backend && .venv/bin/pytest tests/test_submission_precheck_removal.py tests/test_openapi_contract.py tests/test_checker_runner.py -q)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/coverage report --include='app/modules/checkers/*,app/api/router.py' --precision=2 --fail-under=90)
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is the old API truly unreachable rather than hidden behind an alias?
- Were reusable compiler/post-submit capabilities preserved?
- Does this chunk introduce no replacement behavior?
