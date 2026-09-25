"""Public route shape and admission boundaries without mocking policy outcomes."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
import pytest

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.contribution_policies import get_policy_request
from app.api.routes.contribution_policies import router
from app.modules.contributions.api import ContributionPolicyCreateDraftRequest
from tests.authentication.support import issue_asymmetric_token
from .support import UNPAID

ROOT = "/api/v1/projects/{project_id}/contribution-policies"
ROUTES = (
    ("post", "/drafts", "create_draft", {"name": "Policy"}),
    ("put", "/{policy_id}/versions/{version_id}", "update_draft", UNPAID),
    ("post", "/{policy_id}/versions/{version_id}/publication", "publish", {}),
    ("post", "/{policy_id}/versions/{version_id}/retirement", "retire", {}),
)


def url(suffix):
    return (ROOT + suffix).format(project_id=uuid4(), policy_id=uuid4(), version_id=uuid4())


def test_public_policy_contract():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    schema = app.openapi()
    for method, suffix, action, _ in ROUTES:
        operation = schema["paths"][ROOT + suffix][method]
        assert operation["x-workstream-action-id"] == "contribution.policy." + action
        key = [p for p in operation["parameters"] if p["name"] == "Idempotency-Key"]
        assert len(key) == 1 and key[0]["required"] and key[0]["schema"]["format"] == "uuid"
    for suffix in ("/current", "/{policy_id}"):
        assert schema["paths"][ROOT + suffix]["get"]["x-workstream-action-id"] == "contribution.policy.read"
    models = schema["components"]["schemas"]
    for name in ("PolicyCreateInput", "PolicyUpdateInput", "PolicyDecisionInput", "PolicyRuleInput", "PolicyDefinitionInput"):
        assert models[name]["additionalProperties"] is False
    assert set(schema["paths"]) == {ROOT + suffix for suffix in (
        "/current", "/{policy_id}", *(r[1] for r in ROUTES),
    )}


@pytest.mark.parametrize("method,suffix,action,body", ROUTES)
async def test_mutation_input_admission(method, suffix, action, body):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    async def admitted():
        return None
    async def forbidden():
        raise AssertionError("invalid header reached CON composition")
    app.dependency_overrides[enforce_human_authorization_read] = admitted
    app.dependency_overrides[get_policy_request] = forbidden
    key = str(uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        for headers in ([], [("Idempotency-Key", "bad")], [("Idempotency-Key", key), ("Idempotency-Key", key)]):
            response = await client.request(method, url(suffix), json=body, headers=headers)
            assert response.status_code == 422, response.text
        with pytest.raises(AssertionError, match="reached CON composition"):
            await client.request(method, url(suffix), json=body, headers={"Idempotency-Key": key})
        reached = []
        async def operation(command):
            reached.append(command)
            raise HTTPException(418, "valid input reached owner")
        async def composed():
            return SimpleNamespace(actor_profile_id=uuid4(), service=SimpleNamespace(**{action: operation}))
        app.dependency_overrides[get_policy_request] = composed
        for field in ("actor_profile_id", "operation_id", "authority"):
            response = await client.request(method, url(suffix), json=body | {field: str(uuid4())}, headers={"Idempotency-Key": key})
            assert response.status_code == 422, response.text
            assert reached == []
        response = await client.request(method, url(suffix), json=body, headers={"Idempotency-Key": key})
        assert response.status_code == 418 and len(reached) == 1, response.text
        assert str(reached[0].operation_id) == key
        if action == "create_draft":
            assert type(reached[0]) is ContributionPolicyCreateDraftRequest


async def test_nonhuman_policy_admission(admin_access):
    app = admin_access.signed.client._transport.app
    entered = []
    async def observe():
        entered.append(True)
        raise HTTPException(418, "human reached CON composition")
    app.dependency_overrides[get_policy_request] = observe
    token = issue_asymmetric_token(admin_access.signed.private_key, subject_kind="service", scope="workstream:service")
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": str(uuid4())}
    try:
        for method, suffix, _, body in ROUTES:
            response = await admin_access.signed.client.request(method, url(suffix), headers=headers, json=body)
            assert response.status_code == 404, response.text
        for suffix in ("/current", "/{policy_id}"):
            response = await admin_access.signed.client.get(url(suffix), headers=headers)
            assert response.status_code == 404, response.text
        assert entered == []
        positive = await admin_access.signed.client.get(url("/current"), headers=admin_access.target.headers)
        assert positive.status_code == 418 and entered == [True], positive.text
    finally:
        app.dependency_overrides.pop(get_policy_request)
