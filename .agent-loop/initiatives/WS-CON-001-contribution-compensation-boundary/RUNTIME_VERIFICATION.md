# Runtime Verification Contract: WS-CON-001

Repository-wide tests and repository coverage run in the existing GitHub
`Backend full-suite coverage` job after the full PR is pushed. Do not run that
multi-hour suite locally. Local verification is bounded to the chunk's focused
PostgreSQL selectors, focused coverage, Ruff, and repository static gates.

Every runtime chunk executes the local template below after replacing
`<CHUNK_ID>`, `<FOCUSED_TEST_COMMAND>`, and `<RUFF_TARGETS>` with its reviewed
contract. The focused test command must start from an erased coverage file,
must use the isolated database runner and real required local services, must
select a non-empty test set, and must generate fresh coverage with
`--cov=app --cov-report=`. A pre-existing `.coverage` file is never accepted.

```bash
(cd backend && .venv/bin/python -m coverage erase)
(cd backend && <FOCUSED_TEST_COMMAND>)
(cd backend && .venv/bin/python -m coverage report --include='<EACH SUBSYSTEM PATTERN FROM THE ROW>' --fail-under=90)
(cd backend && .venv/bin/ruff check <RUFF_TARGETS>)
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
```

| Chunk | Separate focused subsystem reports (one `coverage report` per entry) | `<RUFF_TARGETS>` |
|---|---|---|
| CON-02A | `app/modules/outbox/*` | `app/modules/outbox app/db/models.py tests/assertion_helpers.py tests/test_assertion_helpers.py tests/test_outbox.py tests/test_alembic.py alembic/versions/0029_shared_transactional_outbox.py` |
| CON-02B | `app/modules/outbox/*`; `app/workers/outbox.py` | `app/modules/outbox app/workers/outbox.py app/workers/celery_app.py app/core/config.py tests/test_outbox.py tests/test_config.py` |
| CON-02C | `app/modules/audit/*` | `app/modules/audit tests/test_audit.py` |
| CON-03A | `app/modules/compensation/*` | `app/modules/compensation app/db/models.py tests/test_compensation.py alembic/versions/<exact-file>.py` |
| CON-03B | `app/modules/contributions/*` | `app/modules/contributions app/modules/projects/models.py app/db/models.py tests/test_contributions.py tests/test_projects.py alembic/versions/<exact-file>.py` |
| CON-03C | `app/modules/contributions/*`; `app/modules/compensation/*` | `app/modules/contributions app/modules/compensation app/db/models.py tests/test_contributions.py tests/test_compensation.py alembic/versions/<exact-file>.py` |
| CON-03D | `app/modules/compensation/*` | `app/modules/compensation app/db/models.py tests/test_compensation.py alembic/versions/<exact-file>.py` |
| CON-04A | `app/modules/compensation/*` | `app/modules/compensation app/composition/compensation.py tests/test_compensation.py tests/test_authorization.py tests/test_api_contract_e2e.py` |
| CON-04B | `app/modules/contributions/*` | `app/modules/contributions app/modules/projects/repository.py app/composition/contributions.py tests/test_contributions.py tests/test_projects.py tests/test_authorization.py tests/test_api_contract_e2e.py` |
| CON-05A | `app/modules/contributions/*`; `app/modules/projects/*`; `app/modules/tasks/*`; `app/modules/checkers/*` | `app/modules/contributions app/modules/projects app/modules/tasks app/modules/checkers app/db/models.py tests/test_contributions.py tests/test_projects.py tests/test_tasks.py tests/test_checkers.py tests/test_authorization.py tests/test_alembic.py tests/test_api_contract_e2e.py alembic/versions/<exact-file>.py` |
| CON-05B | `app/modules/projects/models.py`; `app/modules/tasks/models.py`; `app/modules/checkers/models.py`; `app/db/models.py` | `app/modules/projects/models.py app/modules/tasks/models.py app/modules/checkers/models.py app/db/models.py tests/test_projects.py tests/test_tasks.py tests/test_checkers.py tests/test_alembic.py alembic/versions/<exact-file>.py` |
| CON-06 | `app/modules/contributions/*` | `app/modules/contributions tests/test_contributions.py tests/test_authorization.py` |
| CON-07 | `app/modules/contributions/*`; `app/modules/compensation/*` | `app/modules/contributions app/modules/compensation tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_outbox.py` |
| CON-08A | `app/modules/compensation/*`; `app/workers/compensation.py`; `app/interfaces/compensation.py`; `app/adapters/compensation/*` | `app/interfaces/compensation.py app/adapters/compensation app/modules/compensation app/modules/outbox/handlers.py app/workers/compensation.py app/workers/celery_app.py app/composition/compensation.py tests/test_compensation.py tests/test_outbox.py tests/test_external_service_adapters.py` |
| CON-08R | `app/modules/api_controls/*`; `app/api/deps/api_controls.py`; `app/core/config.py` | `app/modules/api_controls app/api/deps/api_controls.py app/core/config.py tests/test_api_rate_controls.py tests/test_config.py tests/test_alembic.py alembic/versions/<exact-file>.py` |
| CON-08B | `app/modules/compensation/*` | `app/modules/compensation app/api/internal_compensation.py app/composition/compensation.py tests/test_compensation.py tests/test_authorization.py tests/test_api_controls.py tests/test_api_rate_controls.py tests/test_api_contract_e2e.py` |
| CON-09A (optional) | Defined only by a separately approved refreshed contract | Do not execute from this table alone |
| CON-09B (optional) | Defined only by a separately approved refreshed contract | Do not execute from this table alone |
| CON-10A | `app/modules/contributions/*`; `app/modules/compensation/*` | `app/modules/contributions app/modules/compensation app/api/internal_contributions.py app/api/internal_compensation.py app/composition/contributions.py app/composition/compensation.py tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_api_contract_e2e.py` |
| CON-10B | `app/modules/contributions/*`; `app/modules/compensation/*`; `app/modules/audit/*` | `app/modules/contributions app/modules/compensation app/modules/audit app/api/internal_operations.py app/composition/contributions.py app/composition/compensation.py tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_outbox.py tests/test_audit.py` |
| CON-10C | `app/modules/contributions/*`; `app/modules/compensation/*`; `app/workers/contributions.py`; `app/workers/compensation.py` | `app/modules/contributions app/modules/compensation app/modules/outbox/handlers.py app/workers/contributions.py app/workers/compensation.py app/composition/contributions.py app/composition/compensation.py tests/test_contributions.py tests/test_compensation.py tests/test_outbox.py tests/test_authorization.py` |
| CON-11 | `app/modules/contributions/*`; `app/modules/compensation/*`; `app/modules/outbox/*`; `app/modules/audit/*`; `app/modules/api_controls/*`; `app/api/deps/api_controls.py`; `app/core/config.py`; `app/modules/projects/*`; `app/modules/tasks/*`; `app/modules/checkers/*`; `app/interfaces/compensation.py`; `app/adapters/compensation/*`; `app/workers/outbox.py`; `app/workers/contributions.py`; `app/workers/compensation.py`; `app/composition/contributions.py`; `app/composition/compensation.py`; `app/composition/outbox.py`; `app/api/internal_contributions.py`; `app/api/internal_compensation.py`; `app/api/internal_operations.py` | `app/composition/contributions.py app/composition/compensation.py app/composition/outbox.py tests/test_api_contract_e2e.py tests/test_authorization.py tests/test_contributions.py tests/test_compensation.py tests/test_outbox.py tests/test_audit.py` |

If a named path differs after prerequisite merges, the chunk stops and its
contract is re-reviewed; it may not silently broaden a glob or skip the target.

The GitHub job remains responsible for the unchanged full test selection,
isolated PostgreSQL database, real MinIO service, and repository 78 percent
coverage floor. Focused local evidence does not replace that job and may not be
used to waive a failing or missing GitHub full-suite result. The subsystem 90
percent coverage floor remains a local and CI review requirement.
