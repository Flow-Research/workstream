"""Database failures protect the same tier and version boundaries as policy input."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.authorization.contribution_policies.postgresql_support import world


async def test_v2_policy_tiers_and_version_markers_fail_closed_in_postgres(admin_access):
    target = await world(admin_access)
    created = await target.execute("create_draft", target.request("create_draft"))
    updated = await target.execute(
        "update_draft", target.request("update_draft", created, compensated=True)
    )
    version = updated.contribution_policy_version_id
    async with db_session.get_session_factory()() as session, session.begin():
        ids = dict(
            (
                await session.execute(
                    text(
                        "SELECT task_size,id FROM contribution_award_definitions "
                        "WHERE contribution_policy_version_id=:version"
                    ),
                    {"version": version},
                )
            ).all()
        )
        assert set(ids) == {"small", "medium", "large"}
        for statement, parameters, message in (
            (
                "UPDATE contribution_award_definitions SET task_size=NULL WHERE id=:id",
                {"id": ids["small"]},
                "reward_definition_size",
            ),
            (
                "UPDATE contribution_award_definitions SET task_size='medium' WHERE id=:id",
                {"id": ids["small"]},
                "uq_award_definition_v2_size",
            ),
            (
                "UPDATE contribution_award_definitions SET reward_model_version=1,task_size=NULL WHERE id=:id",
                {"id": ids["small"]},
                "fk_award_definition_reward_version",
            ),
            (
                "INSERT INTO contribution_policy_versions "
                "(id,contribution_policy_id,project_id,version_number,status,created_by,reward_model_version) "
                "SELECT :id,contribution_policy_id,project_id,version_number+1,'draft',created_by,1 "
                "FROM contribution_policy_versions WHERE id=:version",
                {"id": new_record_id(), "version": version},
                "new reward policies require v2",
            ),
        ):
            with pytest.raises(DBAPIError, match=message):
                async with session.begin_nested():
                    await session.execute(text(statement), parameters)
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    approved = await target.execute("publish", target.request("publish", updated))
    async with db_session.get_session_factory()() as session, session.begin():
        with pytest.raises(DBAPIError, match="immutable"):
            async with session.begin_nested():
                await session.execute(
                    text(
                        "UPDATE contribution_policy_versions SET unit_code='NGN' WHERE id=:version"
                    ),
                    {"version": version},
                )
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM contribution_award_definitions WHERE contribution_policy_version_id=:version"
                ),
                {"version": approved.contribution_policy_version_id},
            )
            == 3
        )

        assert (
            await session.scalar(
                text("SELECT unit_code FROM contribution_policy_versions WHERE id=:version"),
                {"version": version},
            )
            == "USD"
        )


@pytest.mark.parametrize("corruption", ["common_header", "missing_tier"])
async def test_deferred_sql_rejects_malformed_publication_and_allows_valid_retry(
    admin_access, monkeypatch, corruption
):
    import app.modules.contributions.policy_publication as publication

    target = await world(admin_access)
    created = await target.execute("create_draft", target.request("create_draft"))
    updated = await target.execute(
        "update_draft", target.request("update_draft", created, compensated=True)
    )
    version = updated.contribution_policy_version_id
    request = target.request("publish", updated)
    # Exercise the database failure boundary with real authorization and the
    # real publication owner; bypass only its pure application graph check.
    with monkeypatch.context() as patch:
        patch.setattr(publication, "require_complete_policy_graph", lambda *args: None)
        with pytest.raises(
            DBAPIError,
            match="published contribution policy graph is incomplete|incomplete contribution policy definitions",
        ):
            async with db_session.get_session_factory()() as session, session.begin():
                statement = (
                    "UPDATE contribution_policy_versions SET unit_code='EUR' WHERE id=:version"
                    if corruption == "common_header"
                    else "DELETE FROM contribution_award_definitions WHERE contribution_policy_version_id=:version AND task_size='medium'"
                )
                await session.execute(text(statement), {"version": version})
                await target.service(session).publish(request)
                assert (
                    await session.scalar(
                        text("SELECT status FROM contribution_policy_versions WHERE id=:version"),
                        {"version": version},
                    )
                    == "published"
                )
    async with db_session.get_session_factory()() as session:
        row = (
            await session.execute(
                text("SELECT status,unit_code FROM contribution_policy_versions WHERE id=:version"),
                {"version": version},
            )
        ).one()
        assert tuple(row) == ("draft", "USD")
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM contribution_award_definitions WHERE contribution_policy_version_id=:version"
                ),
                {"version": version},
            )
            == 3
        )
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM contribution_policy_transition_custody WHERE contribution_policy_version_id=:version"
                ),
                {"version": version},
            )
            == 0
        )
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM contribution_policy_lifecycle_events WHERE contribution_policy_version_id=:version AND event_type='published'"
                ),
                {"version": version},
            )
            == 0
        )
    assert (await target.execute("publish", request)).event_type == "published"
