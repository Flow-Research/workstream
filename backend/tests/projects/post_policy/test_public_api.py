"""Public discovery, separate approval and current project authority over real custody."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.main import create_app
from app.modules.projects.post_policy.compiler import compile_saved_post_policy
from app.modules.checkers.api.external_policy import validate_stored_external_checker_policies
from tests.projects.guide_compilation.proposals.pg_support import revoke_review_grant, seed_review_actor
from tests.projects.guide_compilation.proposals.public_support import proposal_client, proposal_path
from .public_support import public_approved_case, deliver


def test_public_policy_openapi_has_exact_actions_and_no_derivation_route():
    schema = create_app().openapi()
    prefix = "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/post-submission-policies/{policy_id}"
    for suffix, verb, action in (
        ("", "get", "project.guide_compilation.review_package.read"),
        ("/approval", "post", "project.post_submit_checker_policy.approve"),
        ("/corrections", "post", "project.post_submit_checker_policy.correction.request"),
    ):
        operation = schema["paths"][prefix + suffix][verb]
        assert operation["x-workstream-action-id"] == action
        if verb == "post":
            assert any(p["name"] == "Idempotency-Key" and p["required"] for p in operation["parameters"])
    assert not any("derive" in path for path in schema["paths"])
    for name in ("PostPolicyApprovalInput", "PostPolicyCorrectionInput"):
        assert "idempotency_key" not in schema["components"]["schemas"][name]["properties"]


@pytest.mark.parametrize("suffix", ["approval", "corrections"])
@pytest.mark.parametrize("keys", [[], [("Idempotency-Key", "bad")],
    [("Idempotency-Key", str(uuid4())), ("idempotency-key", str(uuid4()))],
    [("Idempotency-Key", "00000000-0000-0000-0000-000000000001"),
     ("idempotency-key", "00000000-0000-0000-0000-000000000001")]])
@pytest.mark.parametrize("kind,expected", [("human", 422), ("service", 404)])
async def test_policy_admission_precedes_identity_and_sql(suffix, keys, kind, expected):
    from types import SimpleNamespace
    from httpx import ASGITransport, AsyncClient
    from app.api.deps.auth import get_auth_verification_result
    from app.api.deps.api_controls import enforce_authorization_read_rate_limit
    from app.api.deps.authorization import get_authorization_actor
    from app.db.session import get_db_session

    app = create_app()
    app.dependency_overrides[get_auth_verification_result] = lambda: SimpleNamespace(token=SimpleNamespace(subject_kind=kind))
    app.dependency_overrides[enforce_authorization_read_rate_limit] = lambda: None
    def forbidden():
        pytest.fail("rejected admission reached identity or SQL")
    app.dependency_overrides[get_authorization_actor] = forbidden
    app.dependency_overrides[get_db_session] = forbidden
    path = f"/api/v1/projects/{uuid4()}/guides/{uuid4()}/compilations/{uuid4()}/post-submission-policies/{uuid4()}/{suffix}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(path, json={}, headers=keys)
    assert response.status_code == expected, response.text


async def test_public_policy_body_separate_approval_replay_and_revocation(
    isolated_database_env, monkeypatch, post_policy_worker,
):
    async with public_approved_case(isolated_database_env, monkeypatch) as (
        factory, command, actor, grant, approval_id, _,
    ):
        outcome = deliver(post_policy_worker, approval_id)
        assert outcome["status"] == "policy_draft_ready", outcome
        assert deliver(post_policy_worker, approval_id) == outcome
        async with proposal_client(factory, actor) as client:
            path = proposal_path(command)
            proposal = await client.get(path + "/proposal")
            policy_id = proposal.json()["post_submit_policy_id"]
            assert policy_id == outcome["policy_id"]
            policy_path = path + "/post-submission-policies/" + policy_id
            response = await client.get(policy_path)
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["lifecycle_status"] == "compiled" and body["current"] is True
            assert body["approval_operation_id"] is None
            assert body["target"]["upstream"]["operation_id"] == str(approval_id)
            async with factory() as session:
                approved_plan = await session.scalar(text(
                    "SELECT effective_pre_submit_plan FROM project_guide_proposal_approvals WHERE operation_id=:id"
                ), {"id": approval_id})
                expected = compile_saved_post_policy(
                    policies=validate_stored_external_checker_policies(approved_plan),
                )
                assert body["policy"] == expected.model_dump(mode="json")
                assert body["target"]["policy_hash"] == expected.policy_sha256
                assert await session.scalar(text("SELECT count(*) FROM project_post_policy_operations WHERE kind='derive'")) == 1
            headers = {"Idempotency-Key": str(uuid4())}
            payload = {"target": body["target"]}
            approved = await client.post(policy_path + "/approval", headers=headers, json=payload)
            assert approved.status_code == 200, approved.text
            assert approved.json()["kind"] == "approve"
            assert (await client.post(policy_path + "/approval", headers=headers, json=payload)).json() == approved.json()
            assert (await client.get(policy_path)).json()["lifecycle_status"] == "approved"
            for role, scope in (("operator", "system"), ("audit_authority", "project"), ("project_manager", "system")):
                other, _ = await seed_review_actor(factory, command.project_id if scope == "project" else None, role=role, scope=scope)
                async with proposal_client(factory, other) as denied:
                    assert (await denied.get(policy_path)).status_code == 404
                    assert (await denied.post(policy_path + "/approval", headers=headers, json=payload)).status_code == 404
            for replaced in (str(command.project_id), str(command.guide_id), str(command.compilation_id), policy_id):
                invalid = policy_path.replace(replaced, str(uuid4()))
                assert (await client.post(invalid + "/approval", headers=headers, json=payload)).status_code == 404
                corrected = await client.post(invalid + "/corrections", headers=headers,
                    json={**payload, "reason":"Reconsider the evaluation requirements."})
                assert corrected.status_code == 404, corrected.text
            await revoke_review_grant(factory, actor, grant)
            assert (await client.get(policy_path)).status_code == 404
            assert (await client.post(policy_path + "/approval", headers=headers, json=payload)).status_code == 404


async def test_public_commit_failures_rollback_policy_and_correction_evidence(
    isolated_database_env, monkeypatch, post_policy_worker,
):
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.projects.post_policy.test_authority import state

    async with public_approved_case(isolated_database_env, monkeypatch) as (
        factory, command, actor, _, approval_id, _,
    ):
        outcome = deliver(post_policy_worker, approval_id)
        path = proposal_path(command) + "/post-submission-policies/" + outcome["policy_id"]
        async with proposal_client(factory, actor) as client:
            package = await client.get(path)
            assert package.status_code == 200, package.text
            target = package.json()["target"]
            async def fail_commit(session):
                # Mutations have already staged product and audit writes. The
                # request dependency must roll all of them back after this fault.
                raise SQLAlchemyError("private database diagnostic")
            before = await state(factory)
            with monkeypatch.context() as patch:
                patch.setattr(AsyncSession, "commit", fail_commit)
                for suffix in ("", "/approval", "/corrections"):
                    if suffix:
                        payload = {"target":target}
                        if suffix == "/corrections":
                            payload["reason"] = "Reconsider the evidence requirement."
                        response = await client.post(path + suffix,
                            headers={"Idempotency-Key":str(uuid4())}, json=payload)
                    else:
                        response = await client.get(path)
                    assert response.status_code == 503, response.text
                    assert "private database diagnostic" not in response.text
                    assert await state(factory) == before
            assert (await client.get(path.replace(outcome["policy_id"], str(uuid4())))).status_code == 404
            invalid = {**target, "policy_hash":"sha256:" + "f" * 64}
            response = await client.post(path + "/corrections", headers={"Idempotency-Key":str(uuid4())},
                json={"target":invalid, "reason":"Reconsider the evidence requirement."})
            assert response.status_code == 409, response.text


@pytest.mark.parametrize("suffix", ["", "/approval", "/corrections"])
async def test_service_http_denial_with_valid_key_precedes_identity_and_sql(suffix):
    from types import SimpleNamespace
    from httpx import ASGITransport, AsyncClient
    from app.api.deps.auth import get_auth_verification_result
    from app.api.deps.api_controls import enforce_authorization_read_rate_limit
    from app.api.deps.authorization import get_authorization_actor
    from app.db.session import get_db_session

    app = create_app()
    app.dependency_overrides[get_auth_verification_result] = lambda: SimpleNamespace(token=SimpleNamespace(subject_kind="service"))
    app.dependency_overrides[enforce_authorization_read_rate_limit] = lambda: None
    def forbidden():
        pytest.fail("service admission reached identity or SQL")
    app.dependency_overrides[get_authorization_actor] = forbidden
    app.dependency_overrides[get_db_session] = forbidden
    path = f"/api/v1/projects/{uuid4()}/guides/{uuid4()}/compilations/{uuid4()}/post-submission-policies/{uuid4()}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        if suffix:
            response = await client.post(path + suffix, json={}, headers={"Idempotency-Key":str(uuid4())})
        else:
            response = await client.get(path)
    assert response.status_code == 404, response.text
