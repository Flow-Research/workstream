"""Observe real manager-grant serialization against complete proposal disclosure."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_proposals import GuideProposalSelection, GuideProposalError
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.projects.guide_compilation.proposals.pg_support import proposal_case, seed_review_actor
from .test_postgresql import service, package


@pytest.mark.parametrize("first", ["read", "revoke"])
async def test_read_and_grant_revocation_serialize(clean_postgres_database, first):
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        administrator, admin_grant = await seed_review_actor(
            factory, None, role="access_administrator", scope="system"
        )
        second = "revoke" if first == "read" else "read"
        held, started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        pids = {}
        waiter = "proposal-revoke-" + uuid4().hex

        async def run(name):
            if name == second:
                await held.wait()
            try:
                async with service(factory, actor) as (session, owner, request):
                    pids[name] = await session.scalar(text("select pg_backend_pid()"))
                    if name == second:
                        await session.execute(
                            text("select set_config('application_name',:name,true)"),
                            {"name": waiter},
                        )
                        started.set()
                    if name == "read":
                        await owner.review_package(
                            GuideProposalSelection(
                                project_id=command.project_id,
                                guide_id=command.guide_id,
                                compilation_id=command.compilation_id,
                            ),
                            actor=actor,
                            request_id=request,
                        )
                    else:
                        await session.execute(
                            text(
                                "UPDATE admin_role_grants SET status='revoked',version=2,revoked_by_actor_profile_id=:actor,"
                                "revoked_by_admin_role_grant_id=:authorizer,revoked_at=now(),revoked_reason='Manager turnover' WHERE id=:id"
                            ),
                            {
                                "actor": str(administrator.actor_profile_id),
                                "authorizer": admin_grant,
                                "id": grant,
                            },
                        )
                    if name == first:
                        held.set()
                        await release.wait()
                return "committed"
            except GuideProposalError as exc:
                assert name == "read" and exc.code == "authority_unavailable"
                return "denied"

        tasks = {name: asyncio.create_task(run(name)) for name in (first, second)}
        try:
            await asyncio.wait_for(started.wait(), timeout=15)
            assert pids[first] != pids[second]
            await asyncio.wait_for(
                wait_for_named_database_lock(
                    clean_postgres_database,
                    waiter,
                    expected_waiter_pid=pids[second],
                    expected_blocker_pid=pids[first],
                ),
                timeout=15,
            )
            assert not tasks[second].done()
            release.set()
            assert await asyncio.wait_for(
                asyncio.gather(tasks[first], tasks[second]), timeout=30
            ) == (["committed", "committed"] if first == "read" else ["committed", "denied"])
        finally:
            release.set()
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            await package(factory, command, actor)
