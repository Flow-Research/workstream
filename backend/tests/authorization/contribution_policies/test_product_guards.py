"""Real Finance composition retains the established CP04 product guards."""

from dataclasses import replace
from uuid import uuid4

import pytest

from adapter_binding_test_support import Authorization as BindingAuthorization
from app.db import session as db_session
from app.modules.compensation.api import AdapterBindingSuspendRequest
from app.modules.compensation.service import AdapterBindingService
from app.modules.contributions.api import ContributionPolicyConflict, ContributionPolicyUnavailable
from .foreign_fixtures import foreign_project
from .postgresql_support import world, snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", ("0", "-1", "1e2", "NaN"))
async def test_real_authority_preserves_cp04_quantity_guards(admin_access, quantity):
    target = await world(admin_access)
    draft = await target.execute("create_draft", target.request("create_draft"))
    valid = target.request("update_draft", draft, compensated=True)
    paid, review = valid.rules
    invalid = replace(
        valid,
        rules=(
            paid.model_copy(update={"quantities": paid.quantities.model_copy(update={"small": quantity})}),
            review,
        ),
    )
    before = await snapshot(target.project)
    with pytest.raises(ContributionPolicyConflict, match="^contribution_policy_conflict$"):
        await target.execute("update_draft", invalid)
    assert await snapshot(target.project) == before
    assert await target.execute("update_draft", valid)


@pytest.mark.asyncio
async def test_real_authority_preserves_cp04_complete_graph_guard(admin_access):
    target = await world(admin_access)
    draft = await target.execute("create_draft", target.request("create_draft"))
    request = target.request("publish", draft)
    before = await snapshot(target.project)
    with pytest.raises(ContributionPolicyConflict):
        await target.execute("publish", request)
    assert await snapshot(target.project) == before
    await target.execute("update_draft", target.request("update_draft", draft))
    assert await target.execute("publish", request)


@pytest.mark.asyncio
async def test_real_authority_preserves_cp04_foreign_binding_guard(admin_access):
    target = await world(admin_access)
    draft = await target.execute("create_draft", target.request("create_draft"))
    _, foreign_binding = await foreign_project(target, with_binding=True)
    valid = target.request("update_draft", draft, compensated=True)
    invalid = replace(
        valid,
        adapter_binding_id=foreign_binding,
    )
    before = await snapshot(target.project)
    with pytest.raises((ContributionPolicyConflict, ContributionPolicyUnavailable)):
        await target.execute("update_draft", invalid)
    assert await snapshot(target.project) == before
    assert await target.execute("update_draft", valid)


@pytest.mark.asyncio
async def test_real_authority_preserves_cp04_inactive_binding_publication_guard(admin_access):
    target = await world(admin_access)
    draft = await target.execute("create_draft", target.request("create_draft"))
    draft = await target.execute(
        "update_draft", target.request("update_draft", draft, compensated=True)
    )
    publish = target.request("publish", draft)
    with pytest.raises(RuntimeError, match="roll back positive publication control"):
        async with db_session.get_session_factory()() as session, session.begin():
            assert await target.service(session).publish(publish)
            raise RuntimeError("roll back positive publication control")
    async with db_session.get_session_factory()() as session, session.begin():
        # Seed a suspended binding through CP04's lifecycle fixture authority.
        # Only policy authorization is under test; its real AUTH adapter is unchanged.
        auth = BindingAuthorization()
        auth.bind_session(session)
        await AdapterBindingService(session, mutation_authorization=auth).suspend(
            AdapterBindingSuspendRequest(
                operation_id=uuid4(),
                actor_profile_id=target.context.actor_profile_id,
                project_id=target.project,
                adapter_binding_id=target.binding,
                expected_lifecycle_version=1,
            )
        )
    before = await snapshot(target.project)
    with pytest.raises((ContributionPolicyConflict, ContributionPolicyUnavailable)):
        await target.execute("publish", publish)
    assert await snapshot(target.project) == before
