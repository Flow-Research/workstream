"""Historical schema upgrade proof; historical seeding is not AUTH evidence."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.exc import DBAPIError

from app.modules.projects.policy_lineage import (
    ReviewPolicySemantics,
    policy_digest,
    require_complete_policy,
)
from app.modules.projects.repository import ProjectRepository
from project_create_fixtures import seed_authorized_project, suspend_historical_product_custody
from test_project_policy_mutations import _review_payload

pytestmark = pytest.mark.postgres_schema_contract
OWN = "0011_review_policy_human_review"
PRIOR = "0010_project_guide_setup_finalization"


def _config():
    return Config(Path(__file__).resolve().parents[3] / "alembic.ini")


async def _history(url):
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    project = str(uuid4())
    values = _review_payload().model_dump(exclude={"human_review_required"})
    digest = policy_digest(
        "review", ReviewPolicySemantics.model_validate(values), review_semantics_format="v1"
    )
    try:
        async with factory() as session, session.begin():
            await seed_authorized_project(
                session, project_id=project, name="Historical mode", slug=f"mode-{project}"
            )
        async with factory() as session, session.begin():
            for version, status in (("v1", "complete"), ("v2", "legacy_incomplete")):
                guide, policy = str(uuid4()), str(uuid4())
                async with suspend_historical_product_custody(
                    session,
                    table="project_guides",
                    triggers=("guide_mutation_product_custody", "guide_lineage_lifecycle_guard"),
                ):
                    await session.execute(
                        text(
                            "insert into project_guides (id,project_id,version,status,content_markdown,created_by) values (:id,:project,:version,'draft','historical','historical')"
                        ),
                        {"id": guide, "project": project, "version": version},
                    )
                    # Preserve shape/FKs; only historical mutation-custody proof is suspended.
                    # Authority references are fixture anchors, not proof of a past policy action.
                    async with suspend_historical_product_custody(
                        session,
                        table="review_policies",
                        triggers=("review_policy_mutation_custody",),
                    ):
                        await session.execute(
                            text("""
insert into review_policies (id,project_id,guide_version,policy_generation,policy_hash,semantics_status,
review_preference_window_seconds,review_lease_duration_seconds,max_active_review_leases_per_reviewer,
self_review_allowed,reject_policy,finding_evidence_requirement,requires_second_review,allowed_decisions,minimum_finding_fields,
created_by_actor_profile_id,created_via_identity_link_id,created_by_admin_role_grant_id,creation_scope_type,creation_action_id,authorization_decision_event_id)
select :id,p.id,:version,1,:digest,:status,:preference_window,:lease_duration,1,false,'close_task','optional',false,cast(:decisions as json),'[]'::json,
p.created_by_actor_profile_id,p.created_via_identity_link_id,p.created_by_admin_role_grant_id,'system','project.review_policy.update',p.authorization_decision_event_id
from projects p where p.id=:project
"""),
                            {
                                "id": policy,
                                "project": project,
                                "version": version,
                                "digest": digest,
                                "status": status,
                                "preference_window": values["review_preference_window_seconds"],
                                "lease_duration": values["review_lease_duration_seconds"],
                                "decisions": json.dumps(values["allowed_decisions"]),
                            },
                        )
                    await session.execute(
                        text(
                            "update project_guides set selected_review_policy_id=:policy, selected_review_policy_generation=1, selected_review_policy_hash=:digest where id=:guide"
                        ),
                        {"guide": guide, "policy": policy, "digest": digest},
                    )
        return project
    finally:
        await engine.dispose()


async def _snapshot(url, project):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            policies = (
                (
                    await connection.execute(
                        text(
                            "select row_to_json(p) from review_policies p where project_id=:p order by guide_version"
                        ),
                        {"p": project},
                    )
                )
                .scalars()
                .all()
            )
            selectors = (
                await connection.execute(
                    text(
                        "select id,selected_review_policy_id,selected_review_policy_generation,selected_review_policy_hash from project_guides where project_id=:p order by version"
                    ),
                    {"p": project},
                )
            ).all()
            return policies, [tuple(row) for row in selectors]
    finally:
        await engine.dispose()


async def _verify_upgrade(url, project, before):
    after, selectors = await _snapshot(url, project)
    assert selectors == before[1]
    for old, current in zip(before[0], after, strict=True):
        assert current.pop("human_review_required") is True
        assert current.pop("semantics_format") == "v1"
        assert current == old
    engine = create_async_engine(url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session, session.begin():
            repository = ProjectRepository(session)
            for old in before[0]:
                locked = await repository.lock_review_policy(project, old["guide_version"])
                assert locked.id == old["id"] and locked.policy_hash == old["policy_hash"]
                assert locked.human_review_required is True and locked.semantics_format == "v1"
                semantic_values = {
                    name: old[name]
                    for name in ReviewPolicySemantics.model_fields
                    if name != "human_review_required"
                }
                if old["semantics_status"] == "complete":
                    require_complete_policy(
                        kind="review",
                        status=locked.semantics_status,
                        policy_hash=locked.policy_hash,
                        semantic_values=semantic_values,
                        review_semantics_format=locked.semantics_format,
                    )
                else:
                    with pytest.raises(ValueError, match="incomplete"):
                        require_complete_policy(
                            kind="review",
                            status=locked.semantics_status,
                            policy_hash=locked.policy_hash,
                            semantic_values=semantic_values,
                            review_semantics_format=locked.semantics_format,
                        )
            columns = (
                await session.execute(
                    text(
                        "select column_name,is_nullable,column_default from information_schema.columns where table_name='review_policies' and column_name in ('human_review_required','semantics_format') order by column_name"
                    )
                )
            ).all()
            assert columns[0] == ("human_review_required", "NO", None)
            assert columns[1][0:2] == ("semantics_format", "NO")
            assert "v2" in columns[1][2]
    finally:
        await engine.dispose()


def test_nonempty_upgrade_preserves_v1_history_hashes_and_selected_locks(
    isolated_database_env, migration_lock, migration_schema_at
):
    with migration_lock():
        migration_schema_at(PRIOR)
        project = asyncio.run(_history(isolated_database_env))
        before = asyncio.run(_snapshot(isolated_database_env, project))
        command.upgrade(_config(), OWN)
        asyncio.run(_verify_upgrade(isolated_database_env, project, before))
        command.downgrade(_config(), PRIOR)
        assert asyncio.run(_snapshot(isolated_database_env, project)) == before
        command.upgrade(_config(), OWN)


async def _insert_version(url, project, mode, format):
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as session:
            async with suspend_historical_product_custody(
                session, table="review_policies", triggers=("review_policy_mutation_custody",)
            ):
                await session.execute(
                    text("""
insert into review_policies (id,project_id,guide_version,policy_generation,policy_hash,semantics_status,
requires_second_review,allowed_decisions,minimum_finding_fields,human_review_required,semantics_format)
values (:id,:project,'v2',2,:digest,'legacy_incomplete',false,'[]'::json,'[]'::json,:mode,:format)
"""),
                    {
                        "id": str(uuid4()),
                        "project": project,
                        "digest": "sha256:" + "a" * 64,
                        "mode": mode,
                        "format": format,
                    },
                )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.parametrize("mode", [True, False])
def test_v2_history_blocks_downgrade_even_for_true(isolated_database_env, migration_lock, migration_schema_at, mode):
    with migration_lock():
        migration_schema_at(PRIOR)
        project = asyncio.run(_history(isolated_database_env))
        command.upgrade(_config(), OWN)
        for bad_mode, bad_format in ((False, "v1"), (True, "v3"), (None, "v2"), (True, None)):
            with pytest.raises(DBAPIError):
                asyncio.run(_insert_version(isolated_database_env, project, bad_mode, bad_format))
        asyncio.run(_insert_version(isolated_database_env, project, mode, "v2"))
        before = asyncio.run(_snapshot(isolated_database_env, project))
        with pytest.raises(RuntimeError, match="v2 review policy history cannot be downgraded"):
            command.downgrade(_config(), PRIOR)
        assert asyncio.run(_snapshot(isolated_database_env, project)) == before
