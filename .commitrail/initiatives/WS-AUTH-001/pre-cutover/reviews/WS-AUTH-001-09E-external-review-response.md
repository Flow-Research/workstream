# WS-AUTH-001-09E External Review Response

## Comments Addressed

1. CodeRabbit minor wording finding in `docs/spec_authorization_service.md`:
   changed “required closed” to “required, closed” without changing the typed
   context contract.
2. CodeRabbit stability finding in the post-lock human administrative path:
   added an exact human-kind guard before rebuilding
   `HumanAuthorizationContext`. Locked actor-kind drift now produces bounded
   `permission_not_granted` evidence instead of an uncaught validation error.
   A focused regression test proves the request is revalidated and no grant
   lookup occurs after drift.

## Comments Deferred

None.

## Human Decisions Needed

None.

## Commands Rerun

- `.venv/bin/python -m ruff check app/modules/authorization/kernel.py tests/test_authorization.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin -q tests/test_authorization.py -k 'locked_human_kind_drift or inactive_service_dependency or real_revalidation_rejects_locked_drift or revalidation_rejects_matrix_or_availability_drift'`

Result: Ruff passed; 11 focused tests passed.

## Remaining Risks

GitHub Backend, Agent Gates, CodeRabbit re-review, and explicit human review
remain mandatory. This response changes no action availability, feature call
site, outbox integration, or migration.
