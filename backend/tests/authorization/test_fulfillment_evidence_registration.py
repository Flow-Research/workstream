"""Public fulfillment registration and active-service denial boundaries."""

import pytest

from app.core.config import Settings
from app.main import create_app
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import (
    ACTION_BY_ID, ActionAvailability, ActionId, ActionOwner, SERVICE_ACTIONS_BY_IDENTITY,
)
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    ActorKind, AuthorizationDenialCode, PreparedAuthorizationUnsupported,
)
from app.modules.finance.api.contract_schema import (
    fulfillment_exception_schema, fulfillment_report_schema,
)
from tests.authorization.runtime_support import (
    _ForbiddenMatrixActorLock, _PreparedTestSession, _fulfillment_service_matrix_inputs,
    _runtime_context, _runtime_service,
)

_ACTIONS = (
    ActionId.COMPENSATION_FULFILLMENT_REPORT,
    ActionId.COMPENSATION_FULFILLMENT_EXCEPTION_REPORT,
    ActionId.COMPENSATION_FULFILLMENT_SOURCE_READ,
)
_PREFIX = "/api/v1/compensation/awards/{award_id}"


@pytest.fixture(scope="module")
def fulfillment_openapi():
    return create_app(Settings()).openapi()


def test_only_three_service_actions_and_four_routes_activate(fulfillment_openapi):
    assert SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.COMPENSATION_ADAPTER] == frozenset(_ACTIONS)
    for action in _ACTIONS:
        assert ACTION_BY_ID[action].availability is ActionAvailability.ACTIVE
        assert ACTION_BY_ID[action].owner is ActionOwner.COMPENSATION_FULFILLMENT
        assert ACTION_BY_ID[action].permission_id.value == action.value
    found = {(route, method): operation["x-workstream-action-id"]
        for route, methods in fulfillment_openapi["paths"].items() if route.startswith(_PREFIX)
        for method, operation in methods.items()}
    assert found == {
        (_PREFIX + "/fulfillment-reports", "post"): _ACTIONS[0].value,
        (_PREFIX + "/fulfillment-reports/{external_event_id}", "get"): _ACTIONS[2].value,
        (_PREFIX + "/finance-evidence", "get"): _ACTIONS[2].value,
        (_PREFIX + "/fulfillment-exceptions", "post"): _ACTIONS[1].value,
    }


def test_openapi_closed_requests_responses_and_errors(fulfillment_openapi):
    paths, schemas = fulfillment_openapi["paths"], fulfillment_openapi["components"]["schemas"]
    for suffix, expected in (("fulfillment-reports", fulfillment_report_schema()),
                             ("fulfillment-exceptions", fulfillment_exception_schema())):
        operation = paths[_PREFIX + "/" + suffix]["post"]
        assert operation["requestBody"]["content"]["application/json"]["schema"] == expected
        keys = [p for p in operation["parameters"] if p["in"] == "header" and p["name"] == "Idempotency-Key"]
        assert len(keys) == 1 and keys[0]["required"] is True
        assert "65536" in operation["requestBody"]["description"]
        assert {"200", "201", "401", "403", "404", "409", "413", "422", "503"} <= set(operation["responses"])
    for name in ("FulfillmentSourceEvidence", "FulfillmentRecordedReport", "FulfillmentRecordedException",
                 "FulfillmentReportAcknowledgement", "FulfillmentExceptionAcknowledgement"):
        schema = schemas[name]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


@pytest.mark.parametrize("action", _ACTIONS)
@pytest.mark.parametrize("identity", tuple(i for i in ServiceIdentity if i is not ServiceIdentity.COMPENSATION_ADAPTER))
async def test_active_fulfillment_actions_reject_every_other_service_identity(action, identity):
    context, caller, scope = _fulfillment_service_matrix_inputs(_runtime_context(
        actor_kind=ActorKind.SERVICE, service_identity=identity,
    ), action)
    session = _PreparedTestSession()
    forbidden = _ForbiddenMatrixActorLock()
    kernel, evidence = _runtime_service(context, session=session, admin_repository=forbidden)
    prepared = PreparedAuthorizationService(session, context, kernel, forbidden)
    try:
        with pytest.raises(PreparedAuthorizationUnsupported) as caught:
            await prepared.prepare(action, caller, scope)
        assert caught.value.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
        assert forbidden.calls == 0
        assert prepared._issued == {}
        assert evidence.events == []
    finally:
        prepared.close()
