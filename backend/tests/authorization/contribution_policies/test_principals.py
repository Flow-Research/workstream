"""Production grants cannot confer policy authority through unrelated roles."""

import pytest

from app.modules.contributions.api import ContributionPolicyConflict, ContributionPolicyUnavailable
from .foreign_fixtures import foreign_project
from .postgresql_support import world, snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("read", "create_draft", "update_draft", "publish", "retire"))
@pytest.mark.parametrize(
    "principal",
    ("access_administrator", "operator", "audit_authority", "foreign_finance", "foreign_manager"),
)
async def test_real_policy_authority_rejects_other_roles_and_foreign_grants(
    admin_access, operation, principal
):
    target = await world(admin_access)
    prior = None
    for setup in ("create_draft", "update_draft", "publish"):
        if setup == operation or (operation == "read" and prior is not None):
            break
        prior = await target.execute(setup, target.request(setup, prior))
    request = target.request(operation, prior)
    assert (await admin_access.signed.revoke(admin_access.admin, target.grant)).status_code == 200
    if principal in {"foreign_finance", "foreign_manager"}:
        other_project, _ = await foreign_project(target)
        await admin_access.signed.grant(
            admin_access.admin,
            admin_access.target,
            role="finance_authority" if principal == "foreign_finance" else "project_manager",
            project_id=other_project,
        )
    else:
        await admin_access.signed.grant(admin_access.admin, admin_access.target, role=principal)
    before = await snapshot(target.project)
    with pytest.raises((ContributionPolicyConflict, ContributionPolicyUnavailable)):
        await target.execute(operation, request)
    assert await snapshot(target.project) == before
    await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="finance_authority", project_id=target.project
    )
    assert await target.execute(operation, request)
