"""Small public policy commands; owner fixtures supply only existing prerequisites."""

from uuid import UUID, uuid4
from dataclasses import dataclass


UNPAID = {"rules": [
    {"contribution_type": "accepted_submission", "compensation_mode": "unpaid", "definitions": []},
    {"contribution_type": "completed_review", "compensation_mode": "unpaid", "definitions": []},
]}


@dataclass(frozen=True)
class PolicyProject:
    project: UUID
    grant: str


async def world(access, scope="project"):
    """Create only a project shell and real Finance authority, with no bindings."""
    creator = await access.signed.actor("policy-project-creator")
    await access.signed.grant(access.admin, creator, role="project_manager")
    response = await access.signed.client.post(
        "/api/v1/projects", json={"name": "Policy project", "slug": "policy-" + str(uuid4())},
        headers=creator.headers | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    project = UUID(response.json()["id"])
    grant = await access.signed.grant(
        access.admin, access.target, role="finance_authority",
        project_id=project if scope == "project" else None,
    )
    return PolicyProject(project, grant)


def path(project, receipt=None):
    root = f"/api/v1/projects/{project}/contribution-policies"
    if receipt is None:
        return root
    return root + f"/{receipt['contribution_policy_id']}/versions/{receipt['contribution_policy_version_id']}"


async def mutate(access, actor, method, url, body, *, key=None):
    return await access.signed.client.request(
        method, url, json=body,
        headers=actor.headers | {"Idempotency-Key": str(key or uuid4())},
    )


async def draft(access, *, scope="project"):
    target = await world(access, scope)
    response = await mutate(access, access.target, "POST", path(target.project) + "/drafts", {"name": "Project policy"})
    assert response.status_code == 201, response.text
    return target, response.json()


async def published(access):
    target, receipt = await draft(access)
    response = await mutate(access, access.target, "PUT", path(target.project, receipt), UNPAID)
    assert response.status_code == 200, response.text
    response = await mutate(access, access.target, "POST", path(target.project, receipt) + "/publication", {})
    assert response.status_code == 200, response.text
    return target, response.json()
