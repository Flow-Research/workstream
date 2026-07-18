# Internal Review: Week 2 Closeout Real API Drill

## Scope

This review covers the roadmap status update and the real HTTP Week 2 API drill.

Changed contract surfaces:

- `backend/scripts/week2_api_e2e.py`
- `docs/roadmap_status.md`
- `docs/roadmap_day_by_day_execution_plan.md`

## Verifier Results

### Senior engineering

Finding: the first version of the Week 2 drill proved lifecycle routing but not every Week 2 checker family over HTTP.

Resolution: expanded the drill to cover clean pass, missing required file, missing evidence pre-submit block, evidence integrity failure, weak confidentiality attestation, generated-output warning, forbidden path redaction, internal `task_setup_blocked`, and trusted checker retry.

Verdict after fix: the branch stays within scope, adds no product behavior, and introduces no lifecycle state or review decision.

### QA/test

Findings:

- the first drill did not assert that the full Week 2 durable checker set ran
- the roadmap documented only the E2E script instead of the full Week 2 validation gate
- the first script output lacked a compact scenario summary

Resolution:

- added `EXPECTED_DURABLE_CHECKERS` and clean-path checker-set assertions
- added `EXPECTED_PRE_SUBMIT_CHECKERS` for pre-submit feedback
- added negative and warning scenarios for evidence, integrity, confidentiality, generated-output warning, forbidden path, and task setup routes
- documented the full Week 2 validation gate in roadmap status
- added scenario summary output

Targeted QA re-review confirmed the blockers are resolved. The remaining operational note was to ensure `backend/scripts/week2_api_e2e.py` is committed with the PR.

### Security/auth

Finding: the first drill could inherit any `WORKSTREAM_DATABASE_URL` and run migrations/write drill data against it.

Resolution: added `assert_local_database_url()` before environment update, migrations, API startup, or writes. The drill now allows only local `postgresql+asyncpg://` URLs for `workstream_test` or `test_workstream`, unless an explicit write-risk override is set.

Security re-review confirmed:

- non-local host is blocked
- local host with non-local database name is blocked
- non-Postgres URL is blocked
- local async Postgres URLs for `workstream` and `workstream_test` are allowed
- Flow-token auth remains in use
- superseded: the local demo worker-profile route was later removed; current
  drills use `POST /api/v1/workers/me/profile`
- worker redaction and reviewer denial are asserted
- no production route or checker-read permission is widened

### Product/ops

Findings:

- no blocking findings
- superseded: the demo worker-profile helper was removed; current drills use
  the canonical worker profile API
- uppercase lifecycle labels must not drift into persisted token contracts

Resolution: roadmap wording keeps Week 3 readiness explicit and does not overclaim reviewer checker visibility.

### CodeRabbit follow-up

Findings:

- the local database safety gate allowed plain `postgresql://` URLs even though the backend uses SQLAlchemy async engines
- checker-set assertions only proved expected checkers were present, not that the contract had no unexpected extras
- the drill read checker runs and task status immediately after submission lock, which made async background execution timing-sensitive

Resolution:

- tightened the database guard to local `postgresql+asyncpg://`
- made durable, setup-defect, and pre-submit checker-set assertions exact
- added polling for automatic checker-run creation, checker-run terminal status, and task status transitions

Internal follow-up findings:

- QA found that setup-defect checker runs and trusted checker retry responses also needed exact checker-set assertions
- QA found that failed pre-submit responses needed the same exact pre-submit checker-set assertion as the clean pre-submit response
- docs/product-ops found that the evidence still used broad local Postgres wording after the guard was narrowed to async Postgres

Internal follow-up resolution:

- added exact setup-defect checker-set assertions for the blocked run and trusted checker retry
- added exact pre-submit checker-set assertions for failed missing-file and missing-evidence prechecks
- narrowed the accepted local database scheme to the installed `postgresql+asyncpg` driver
- tightened this evidence file to say local async Postgres instead of generic local Postgres

## Validation

The following checks were rerun after the CodeRabbit follow-up edits and internal re-review fixes.

Passed:

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
```

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
```

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week2_api_e2e.py
```

Scenario summary:

```text
clean=review_pending
missing_file=needs_revision
missing_evidence=pre_submit_blocked
duplicate_artifact_integrity=needs_revision
weak_attestation=needs_revision
generated_output_warning=review_pending
forbidden_path=needs_revision
task_setup_blocked=auto_checking->review_pending
```

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py tests/test_tasks.py -q
```

Result: `62 passed in 415.29s`.

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest -q
```

Result: `112 passed in 565.34s`.

Passed:

```bash
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
```

Result: `100.0%`.

Passed:

- stale wording scan
- Markdown relative link check
- XLSX/sheets check: no local sheet exports present

## Closure

Valid findings addressed.

Open sub-agent sessions: none.
