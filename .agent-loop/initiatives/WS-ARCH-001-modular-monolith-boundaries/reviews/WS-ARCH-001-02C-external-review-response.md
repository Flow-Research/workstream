# WS-ARCH-001-02C External Review Response

## Comments addressed

- Backend preflight on `a6b4ea52f1ad071173377523a25214cd8ac96196`
  reported `behavior_ownership_error:partition_target_mismatch`.
  The new callable-bearing public API target
  `backend/app/modules/checkers/api/pre_submit.py` is now registered in the
  existing public-API foundation allowlist and deterministic ownership
  partition.
- Hosted lanes on `86e24b5d99f990e77c0d57679e0306f208b645f2`
  then rejected the new focused test module because it was not in the canonical
  semantic-lane inventory. Its two tests were moved into the already-touched
  architecture module, preserving the proof without changing lane topology or
  oversized lane-catalogue tests.
- The full hosted Backend workflow passed on
  `543efe4e2be623ad3604ee581b5cf331bead5737`.
- CodeRabbit's earlier review requested CHECKER-specific lifecycle names, an
  exact dotted public namespace assertion, deterministic repeated compilation
  through the public planning port, and explicit metadata-boundary proof. All
  four were applied in `ad3237f4938ebcae4662c32e7cbe467945057519`.
  Public metadata projection now independently retains only the exact allowed
  keys whose values are non-negative integers.
- CodeRabbit's follow-up exact-head review of
  `ad3237f4938ebcae4662c32e7cbe467945057519` requested coverage evidence for
  every changed CHECKERS module and unambiguous review-round SHAs. The coverage
  command and this record now provide both.

## Comments deferred

None.

## Human decisions needed

Human maintainers retain review and merge authority.

## Commands rerun

```bash
(cd backend && .venv/bin/python -m scripts.behavior_ownership validate)
(cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_asyncio.plugin tests/test_behavior_ownership.py tests/architecture/test_module_boundaries.py)
(cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_asyncio.plugin tests/architecture/test_module_boundaries.py tests/test_checker_catalogue.py tests/test_effective_pre_submit_execution.py)
(cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_asyncio.plugin -p pytest_cov.plugin tests/architecture/test_module_boundaries.py tests/test_submission_bundle_admission.py tests/test_checker_catalogue.py tests/test_effective_pre_submit_execution.py --cov=app.modules.checkers.api --cov=app.modules.checkers.catalogue --cov=app.modules.checkers.effective_plan --cov=app.modules.checkers.pre_submit_execution --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
```

## Remaining risks

The new target remains unresolved in the behavior catalogue, consistent with
the current public-API foundation transition. No CI rule, threshold, workflow,
or test selection was weakened.
