# WS-QUAL-001-04M Internal Review Evidence

## Deterministic evidence gate

Result: PASS with a documented size exception.

The L1 diff exceeds the preferred 500-line guideline because the executable
policy, shared Git primitive, workflow custody, typed schema, focused tests, and
operator documentation form one approved review boundary. It does not modify
application code, migrations, the Backend workflow, `backend/uv.lock`, the
protected mutation manifest, coverage floors, or existing test inventory.

Commands and results:

- `pytest -q tests/test_mutation_policy.py --cov=scripts.mutation_policy --cov-fail-under=90`: 39 passed; 90.11 percent.
- `ruff check scripts/mutation_policy.py tests/test_mutation_policy.py`: passed.
- `python3 -m unittest -q scripts.test_git_delta`: passed.
- `pytest -q scripts/test_lightweight_agent_gates.py`: 11 passed.
- JSON Schema claim validation and workflow YAML parsing: passed.
- Markdown links, stale Workstream wording, stale authorization docs, stale artifact contracts, and `git diff --check`: passed.

## Exact pilot evidence

Rebased implementation head: `f8b59eec269c93a3e502b5dfc7b818011e3ac93c`

- Protected base: `98cf5f423c4c5010eba6dbfb3efa73843a96b4e4`
- Exact tree: `12436f084d011e10b29d70c4c094fb940e3111f1`
- Elapsed: 254.672 seconds
- Generated: 1,091
- Killed: 84
- Survived: 59
- Excluded: 948
- Timeout, suspicious, error: 0
- Strong calibration: 2 killed
- Weak calibration: 2 survived

The sum of all terminal categories equals the generated count. The hosted PR
workflow must reproduce exact final-head evidence; local evidence does not
replace GitHub Actions.

## Reviewer results

| Track | Result | Material outcome |
|---|---|---|
| Plan/architecture | PASS after fixes | Protected-only dependency authority, typed target ownership, and callable-bounded execution align with PLAN3. |
| Senior engineering | PASS | Complexity remains concentrated in one fail-closed policy module with focused coverage. |
| QA | PASS after fixes | Config triggers, exact claim path, ownership, calibration, and evidence reconciliation are proved. |
| Security | PASS after fixes | No PR packaging install; runner-temp outputs; no persisted credentials; symlink/special-file rejection; token stripping. |
| Product/ops | PASS after fixes | Engineering evidence remains observational and separate from Workstream product review/payment/reputation. |
| CI integrity | PASS after fixes | Independent workflow, pinned Actions, protected manifest, bounded timeout, artifact custody, and unchanged Backend gates. |
| Docs | PASS after correction | Operator guide now distinguishes checkout wrapper execution from disposable test/mutation execution and names the 05M checkpoint. |
| Reuse/dedup | PASS | Shared policy-free Git delta primitive and reusable typed `target_owners`; no parallel custody dialect. |
| Test delta | PASS | No test removal, skip, xfail, threshold lowering, or assertion weakening; intentional weak calibration is paired with strong proof. |

## First-pass findings resolved

- Removed PR-controlled editable backend installation from the mutation venv.
- Added `backend/pyproject.toml` to both workflow path filters.
- Moved toolchain and evidence to runner-temporary storage and enabled hidden-file artifact handling.
- Rejected symlinks and special archive entries before execution.
- Enforced canonical claim path and per-target callable/test/outcome/boundary ownership.
- Bounded mutation execution to reviewed callable filters after full-file runtime exceeded the hard limit.
- Added focused 90-percent subsystem coverage.
