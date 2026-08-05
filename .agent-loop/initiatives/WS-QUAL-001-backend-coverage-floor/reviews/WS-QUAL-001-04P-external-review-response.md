# WS-QUAL-001-04P External Review Response

## Comments addressed

- 04M now names only the protected base-revision
  `scripts/mutation-requirements.txt` as dependency authority and explicitly
  rejects an alternate allowlist or prebuilt runtime for this pilot.
- The 04P acceptance criterion now permits its two authority files while
  preserving the prohibition on production dependency, lockfile, workflow,
  Backend, test, and coverage-gate changes.
- The verification command now creates a disposable Python 3.12 virtual
  environment, records its interpreter version, and runs the hash-checked dry
  run through that environment's Python executable.

## Comments deferred

None.

## Commands rerun

- Disposable Python 3.12 `pip --dry-run --require-hashes`: passed for all 20
  dependencies.
- `python3 scripts/check_markdown_links.py`: passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_lightweight_agent_gates.py`:
  10 passed.
- `git diff --check`: passed.

## CI status at repair time

Agent Gates and CodeRabbit passed on the prior remote head. The five Backend
lanes were pending, not failed. Rebasing onto current `main` intentionally
restarts exact-head checks.

## Remaining risk

None for 04P dependency custody. Mutation behavior and runtime remain 04M work.
