# WS-SEC-001-01: Patch Dependency Alerts

## Intent

Close the six open Dependabot alerts by moving direct and transitive runtime
dependencies and retained development tooling to patched versions.

## Allowed files

- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/config/guide_extractor_dependencies.json`
- `scripts/mutation-requirements.in`
- `scripts/mutation-requirements.txt`
- focused dependency tests or documentation if compatibility requires them
- `.agent-loop/CURRENT_STATE.md`
- `.agent-loop/initiatives/WS-SEC-001-dependency-alert-remediation/**`

## Not allowed

- Product behavior, API, persistence, migration, authorization, or workflow changes
- Disabling or dismissing alerts without a patched dependency
- Weakening dependency hashes, parser isolation, tests, coverage, or CI gates
- Unrelated dependency upgrades

## Acceptance criteria

- `cryptography` resolves to at least 50.0.0.
- `pypdf` is exactly 6.15.0 in the direct hash pin, approval manifest, and lock.
- Backend pytest resolves to at least 9.0.3 after compatibility validation.
- `pytest-asyncio` resolves to the tested pytest-9-compatible 1.4.x line.
- Retained mutation tooling pins pytest at least 9.0.3 and uv at least 0.11.15 with hashes.
- Guide dependency integrity and focused parser, auth, and mutation-policy tests pass.
- No Workstream product behavior changes.

## Risk and review

Risk: L1 security/dependency integrity. Required review: security, CI integrity,
test delta, and senior engineering.

## Verification

```bash
set -euo pipefail
cd backend
uv lock --check
uv run python scripts/check_guide_extractor_dependencies.py
uv pip install --dry-run --require-hashes \
  -r ../scripts/mutation-requirements.txt
uv run pytest -q tests/test_guide_extractor_dependencies.py tests/test_guide_pdf.py tests/test_mutation_policy.py
WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres \
  uv run python scripts/run_isolated_tests.py \
  --metadata-json /tmp/ws-sec-001-auth-test.json \
  --timeout-seconds 600 -- uv run pytest -q tests/test_auth.py
cd ..
python3 scripts/check_markdown_links.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
git diff --check
```

## Merge state

- Outcome on merge: `complete`
