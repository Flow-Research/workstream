"""Real PostgreSQL proof for contributor-safe locked compensation reads."""

from dataclasses import replace
from uuid import UUID

from app.db import session as db_session
from tests.authorization.guide_activation.pg_support import activate
from tests.authorization.task_authority.test_postgresql import grant, project_manager
from tests.authorization.task_reads.support import create_task
from tests.projects.guide_activation.pg_support import activation_case
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    admin_access as admin_access,
    signed_access as signed_access,
)
from tests.test_tasks import (
    admit_and_grant_project_submitter,
    auth_headers,
    create_active_project,
    create_ready_task,
    task_client as task_client,
    task_database_env as task_database_env,
)


EXPECTED_PAID = {
    "accepted_submission": [
        {"instrument": "money", "unit": "USD", "quantity": "2.125000000000000001"},
        {"instrument": "project_points", "unit": "PTS", "quantity": "7"},
    ],
    "completed_review": [
        {"instrument": "money", "unit": "USD", "quantity": "2.125000000000000001"},
        {"instrument": "project_points", "unit": "PTS", "quantity": "7"},
    ],
}
FINANCE_INTERNALS = (
    "adapter_binding_id",
    "route_key",
    "binding_status",
    "compensation_mode",
    "policy_status",
    "version_status",
)


async def publish_unpaid_successor(world):
    result = None
    for operation in ("create_draft", "update_draft", "publish"):
        async with db_session.get_session_factory()() as session, session.begin():
            result = await getattr(world.service(session), operation)(
                world.request(operation, result)
            )
    return result


async def test_unpaid_ready_and_detail_share_the_task_locked_version(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "unpaid-compensation-reader"
    )
    queue = await task_client.get(
        f"/api/v1/projects/{project['id']}/tasks/ready", headers=auth_headers()
    )
    detail = await task_client.get(f"/api/v1/tasks/{task['id']}", headers=auth_headers())
    assert queue.status_code == detail.status_code == 200, (queue.text, detail.text)
    expected = {
        "contribution_policy_version_id": task["locked_contribution_policy_version_id"],
        "accepted_submission": "unpaid",
        "completed_review": "unpaid",
    }
    assert queue.json()["items"][0]["compensation"] == expected
    assert detail.json()["compensation"] == expected
    assert all(name not in queue.text + detail.text for name in FINANCE_INTERNALS)


async def test_ready_and_detail_show_exact_locked_paid_terms_to_both_project_roles(
    admin_access,
):
    factory = db_session.get_session_factory()
    url = factory.kw["bind"].url.render_as_string(hide_password=False)
    async with activation_case(
        url, contribution_awards=("money", "project_points")
    ) as (sessions, command, actor, _manager_grant, world, published):
        await activate(sessions, actor, command)
        project = command.target.proposal.project_id
        manager = await project_manager(admin_access, project)
        task = await create_task(admin_access, project, manager)
        await grant(admin_access, manager, project, "submitter")

        async def read(headers):
            queue = await admin_access.signed.client.get(
                f"/api/v1/projects/{project}/tasks/ready", headers=headers
            )
            detail = await admin_access.signed.client.get(
                f"/api/v1/tasks/{task}", headers=headers
            )
            assert queue.status_code == detail.status_code == 200, (queue.text, detail.text)
            assert len(queue.json()["items"]) == 1
            queue_terms = queue.json()["items"][0]["compensation"]
            detail_terms = detail.json()["compensation"]
            assert queue_terms == detail_terms == {
                "contribution_policy_version_id": str(
                    command.contribution_policy_version_id
                ),
                **EXPECTED_PAID,
            }
            encoded = queue.text + detail.text
            assert all(name not in encoded for name in FINANCE_INTERNALS)
            return queue_terms

        submitter_terms = await read(admin_access.target.headers)
        reviewer = await admin_access.signed.actor("locked-compensation-reviewer")
        reviewer_access = replace(admin_access, target=reviewer)
        await grant(reviewer_access, manager, project, "reviewer")
        assert await read(reviewer.headers) == submitter_terms

        outsider = await admin_access.signed.actor("locked-compensation-outsider")
        for path in (
            f"/api/v1/projects/{project}/tasks/ready",
            f"/api/v1/tasks/{task}",
        ):
            denied = await admin_access.signed.client.get(path, headers=outsider.headers)
            assert denied.status_code == 404
            assert denied.json()["error"]["code"] == "project_authorization_resource_not_found"

        successor = await publish_unpaid_successor(world)
        assert successor.contribution_policy_version_id != published.contribution_policy_version_id
        assert UUID(str(published.contribution_policy_version_id)) == command.contribution_policy_version_id
        assert await read(admin_access.target.headers) == submitter_terms
