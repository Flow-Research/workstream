"""Public exact proposal behavior through production AUTH, compiler and SQL custody."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.main import create_app
from .pg_support import proposal_case, revoke_review_grant
from .public_support import proposal_client, proposal_path


def test_openapi_exposes_complete_proposal_journey():
    paths = create_app().openapi()["paths"]
    prefix = "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}"
    for suffix, verb, action in (
        ("/proposal", "get", "project.guide_compilation.review_package.read"),
        ("/pre-submission-approval", "post", "project.submission_artifact_policy.approve"),
        ("/corrections", "post", "project.guide_compilation.correction.request"),
        ("/corrections/{correction_operation_id}/dispatch", "post", "project.guide_compilation.request"),
    ):
        operation = paths[prefix + suffix][verb]
        assert operation["x-workstream-action-id"] == action
    for suffix in ("/pre-submission-approval", "/corrections"):
        assert any(p["name"] == "Idempotency-Key" and p["required"] for p in paths[prefix+suffix]["post"]["parameters"])
    schemas = create_app().openapi()["components"]["schemas"]
    assert "idempotency_key" not in schemas["GuideProposalApprovalInput"]["properties"]
    assert "provider_idempotency_key" not in schemas["GuideProposalDispatchResponse"]["properties"]


async def test_public_approval_read_replay_and_current_authority(clean_postgres_database):
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        path = proposal_path(command)
        async with proposal_client(factory, actor) as client:
            package = await client.get(path + "/proposal")
            assert package.status_code == 200, package.text
            body = package.json()
            assert body["target"]["compilation_id"] == str(command.compilation_id)
            key = {"Idempotency-Key": str(uuid4())}
            payload = {"target": body["target"], "acknowledged_warning_hashes": body["warning_hashes"]}
            approved = await client.post(path+"/pre-submission-approval", headers=key, json=payload)
            assert approved.status_code == 200, approved.text
            replay = await client.post(path+"/pre-submission-approval", headers=key, json=payload)
            assert replay.status_code == 200, replay.text
            assert replay.json() == approved.json()
            for secret in ("provider_idempotency_key", "source_item_id", "runtime_configuration", "document_version_id"):
                assert secret not in package.text
            async with factory() as session:
                count = await session.scalar(text("SELECT count(*) FROM project_guide_proposal_approvals"))
                assert count == 1
            await revoke_review_grant(factory, actor, grant)
            denied = await client.post(path+"/pre-submission-approval", headers=key, json=payload)
            assert denied.status_code == 404, denied.text


@pytest.mark.parametrize("failure", ["missing_key", "invalid_key", "wrong_path", "warning", "changed_target"])
async def test_public_approval_rejects_without_writes(clean_postgres_database, failure):
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, _):
        path = proposal_path(command)
        async with proposal_client(factory, actor) as client:
            package = await client.get(path+"/proposal")
            assert package.status_code == 200, package.text
            body = package.json()
            payload = {"target":body["target"], "acknowledged_warning_hashes":body["warning_hashes"]}
            headers = {"Idempotency-Key":str(uuid4())}
            expected = 409
            if failure == "missing_key":
                headers = {}
                expected = 422
            elif failure == "invalid_key":
                headers = {"Idempotency-Key":"bad"}
                expected = 422
            elif failure == "wrong_path":
                path = path.replace(str(command.project_id), str(uuid4()))
                expected = 404
            elif failure == "warning":
                payload["acknowledged_warning_hashes"] = ["sha256:"+"f"*64]
            else:
                payload["target"]["result_hash"] = "sha256:"+"f"*64
            response = await client.post(path+"/pre-submission-approval", headers=headers, json=payload)
            assert response.status_code == expected, response.text
            async with factory() as session:
                assert await session.scalar(text("SELECT count(*) FROM project_guide_proposal_approvals")) == 0
                assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE action_id='project.submission_artifact_policy.approve'")) == 0


@pytest.mark.parametrize("subject_kind,expected", [("service",404),("human",422)])
async def test_public_admission_rejects_before_identity_or_database(subject_kind, expected):
    from types import SimpleNamespace
    from httpx import ASGITransport, AsyncClient
    from app.api.deps.auth import get_auth_verification_result
    from app.api.deps.api_controls import enforce_authorization_read_rate_limit
    from app.api.deps.authorization import get_authorization_actor
    from app.db.session import get_db_session

    app = create_app()
    app.dependency_overrides[get_auth_verification_result] = lambda: SimpleNamespace(token=SimpleNamespace(subject_kind=subject_kind))
    app.dependency_overrides[enforce_authorization_read_rate_limit] = lambda: None
    def forbidden():
        pytest.fail("rejected admission accessed identity or database")
    app.dependency_overrides[get_authorization_actor] = forbidden
    app.dependency_overrides[get_db_session] = forbidden
    path = "/api/v1/projects/{0}/guides/{0}/compilations/{0}/corrections".format(uuid4())
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://testserver") as client:
        response = await client.post(path,json={})
    assert response.status_code == expected, response.text


async def test_public_package_denies_other_roles_and_scopes(clean_postgres_database):
    from .pg_support import seed_review_actor
    async with proposal_case(clean_postgres_database) as (_,factory,command,actor,_):
        path = proposal_path(command)
        async with proposal_client(factory,actor) as client:
            assert (await client.get(path+"/proposal")).status_code == 200
        for role,scope,project in (
            ("project_manager","system",None),
            ("audit_authority","project",command.project_id),
            ("operator","system",None),
        ):
            other,_ = await seed_review_actor(factory,project,role=role,scope=scope)
            async with proposal_client(factory,other) as client:
                response = await client.get(path+"/proposal")
                assert response.status_code == 404, response.text
                assert "target" not in response.json()
