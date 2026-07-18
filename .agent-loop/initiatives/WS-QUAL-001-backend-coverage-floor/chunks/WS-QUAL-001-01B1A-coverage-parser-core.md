# Chunk Contract: WS-QUAL-001-01B1A Coverage Parser Core

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: blocked at 394/400 lines after two parser-normalization repair cycles.
The remaining QA/security findings require replanning before implementation
continues.

## Goal And Reason

Deliver the read-only parser and arithmetic half of the coverage policy without
mixing repository-diff semantics into the same PR. This chunk exists because
the combined 01B1 exhausted its 500-line budget while repeated test-delta gaps
remained.

Risk: L1 test-policy integrity. SLA: P1.

## Scope

Allowed implementation files:

- `backend/scripts/coverage_policy.py`
- `backend/tests/test_coverage_contract.py`
- `docs/operations_backend_testing.md`
- WS-QUAL initiative artifacts and global loop memory/reviews

Not allowed: Git-delta helpers or tests, CI/workflow/config/evidence mutation,
`backend/app/**`, database runner changes, migrations, APIs, product/auth
behavior, coverage-raising tests, skips/xfails, exclusions, or pragmas.

Implementation cap: 400 lines outside `.agent-loop`. Stop and replan above 370
before remaining work; never compress assertions to fit.

## Acceptance Criteria

- Complete `app/**/*.py` inventory and reconciled per-file/top-level coverage
  counts fail closed on malformed or fabricated input.
- Six-place percentage truncation has parameterized success proof for 0%, 100%,
  repeating fractions, and a truncation boundary.
- Intended pytest-cov/config parsing requires one exact pin, table shapes,
  finite exact floors, precision, and no exclusion/narrowing keys using only
  temporary fixtures; live configuration remains unchanged.
- Canonical evidence and runner metadata parsers enforce exact schemas, bounded
  versions, SHA/Alembic/database fields, arithmetic consistency, and credential
  exclusion without writing evidence or connecting to Postgres.
- Application coverage pragmas fail closed. The compute-only CLI is stable,
  read-only, and documented as preparatory rather than CI enforcement.

## Verification And Review

```text
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && .venv/bin/python -m pytest -q tests/test_coverage_contract.py)
(cd backend && .venv/bin/python -m pip check)
BASE_SHA="$(git merge-base HEAD origin/main)"
test -z "$(git diff --name-only "$BASE_SHA"...HEAD | grep -Ev '^(backend/scripts/coverage_policy.py|backend/tests/test_coverage_contract.py|docs/operations_backend_testing.md|\.agent-loop/(LOOP_STATE.md|REVIEW_LOG.md|WORK_QUEUE.md|initiatives/WS-QUAL-001-backend-coverage-floor/.*))$')"
test "$(git diff --numstat "$BASE_SHA"...HEAD -- backend/scripts/coverage_policy.py backend/tests/test_coverage_contract.py docs/operations_backend_testing.md | awk '{total += $1 + $2} END {print total + 0}')" -le 400
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta. Human focus:
fail-closed parser behavior, arithmetic boundaries, read-only operation, and no
semantic-delta or 01B2 scope.

Stop after this chunk. Do not start 01B1B, 01B2, chunk 02, or AUTH.
