# Internal Review: Chunk 10 Checker Trial

## Scope

Chunk 10 adds the checker trial specification, failure catalog, and API-level trial coverage for five sample submission scenarios.

Changed contract surfaces:

- `docs/spec_chunk_10_checker_trial.md`
- `docs/checker_trial_failure_catalog.md`
- `docs/spec_week2_checker_framework.md`
- `docs/roadmap_day_by_day_execution_plan.md`
- `README.md`
- `backend/tests/test_checkers.py`

## Verifier Results

### Senior engineering

Finding: the first draft overclaimed reviewer checker-output visibility even though current checker read access is limited to admin, project manager, and assigned worker.

Resolution: corrected Chunk 10 wording to trusted internal and project-manager/admin API visibility. Reviewer visibility remains a Week 3 contract.

Verdict after fix: no lifecycle expansion, no new review decision, worker-fixable failures route to `needs_revision`, and internal setup defects remain `task_setup_blocked`.

### QA/test

Finding: same reviewer-visibility wording issue; test coverage itself matched current backend contracts.

Resolution: corrected the docs and kept the trial as real API coverage.

Verified coverage:

- clean packet reaches `review_pending`
- missing required file routes to `needs_revision`
- forbidden file path routes to `needs_revision` without worker path leakage
- weak confidentiality attestation routes to `needs_revision`
- locked task setup defect routes to internal `task_setup_blocked`
- trusted checker retry after repair reaches `review_pending`

### Security/auth

Finding: the original catalog visibility column implied broader internal checker access than the backend allows.

Resolution: renamed the column to `Project Manager/Admin API Visibility` and kept worker redaction assertions in the trial test.

Verified boundaries:

- test auth remains dev-only fixture usage
- no production Flow auth behavior changed
- worker responses hide `task_setup_blocked`
- worker responses hide internal task setup field names and metadata
- forbidden path details do not leak through worker-visible messages

### Product/ops

Findings:

- normalize `needs_revision` wording where Chunk 10 touched Week 2 docs
- use `trusted checker retry` as the canonical phrase
- commit the new Chunk 10 docs with the README link

Resolution: normalized wording and kept the operator/worker mental model: workers see `needs_revision`; project-manager-owned setup defects stay internal.

## Validation

Passed:

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
```

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py::test_chunk10_checker_trial_runs_sample_submissions_through_real_api -q
```

Result: `1 passed in 23.20s`.

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py -q
```

Result: `23 passed in 150.27s`.

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_tasks.py tests/test_checkers.py -q
```

Result: `62 passed in 406.92s`.

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest -q
```

Result: `112 passed in 695.21s`.

Passed:

```bash
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
```

Result: `100.0%`.

## Closure

Valid findings addressed.

Open sub-agent sessions: none.
