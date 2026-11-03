"""Real activation transaction, exact replay and default-deny controls."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.projects.models import ProjectGuide
from .pg_support import activation_case, activation_service


async def _activation_effects(session):
    """Capture lifecycle, activation replay, release and dispatch facts exactly."""
    return {
        table: tuple(await session.scalars(text(
            f"SELECT to_jsonb(r)::text FROM public.{table} r ORDER BY to_jsonb(r)::text"
        )))
        for table in (
            "projects", "project_guides", "guide_mutation_idempotency_records",
            "workstream_tasks", "submissions", "outbox_events",
        )
    }


async def _activation_inputs(factory, finalization, approval, actor, grant, values, policy):
    """Approve the exact derived POST policy and return one activation command."""
    from app.core.hashing import canonical_json_hash
    from app.modules.projects.api.guide_proposals import GuideProposalSelection
    from app.modules.projects.api.post_policy import PostPolicyApproval
    from app.modules.projects.api.post_policy import PostPolicyDerive
    from tests.projects.guide_compilation.helpers import service_actor
    from tests.projects.post_policy.pg_support import operate
    from .pg_support import activation_command

    derived = await operate(
        factory,
        service_actor(values),
        finalization.project_id,
        None,
        "derive",
        PostPolicyDerive(
            selection=GuideProposalSelection(
                project_id=finalization.project_id,
                guide_id=finalization.guide_id,
                compilation_id=finalization.compilation_id,
            ),
            upstream_approval_operation_id=approval.operation_id,
            upstream_approval_output_digest=canonical_json_hash(approval.model_dump(mode="json")),
        ),
    )
    approved = await operate(
        factory,
        actor,
        finalization.project_id,
        grant,
        "approve",
        PostPolicyApproval(target=derived.target, idempotency_key=uuid4()),
    )
    return await activation_command(factory, approved, policy)


async def test_complete_activation_and_exact_replay(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (
        factory,
        command,
        actor,
        grant,
        world,
        policy,
    ):
        async with factory() as session:
            for table in ("workstream_tasks", "submissions"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        async with factory() as session, session.begin():
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "active"
            assert guide.contribution_policy_version_id == command.contribution_policy_version_id
            assert await load_guide_activation(session, guide) == receipt
            assert (
                await session.scalar(
                    text("SELECT status FROM projects WHERE id=:id"), dict(id=guide.project_id)
                )
                == "active"
            )
        async with factory() as session, session.begin():
            replay = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
            assert replay == receipt
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 1
            )
        from tests.projects.guide_compilation.proposals.public_support import proposal_client

        async with proposal_client(factory, actor) as client:
            response = await client.get(
                f"/api/v1/projects/{command.target.proposal.project_id}/active-guide"
            )
            assert response.status_code == 200, response.text
            assert response.json()["guide"]["contribution_policy_version_id"] == str(
                command.contribution_policy_version_id
            )
        async with factory() as session, session.begin():
            await world.service(session).retire(world.request("retire", policy))
        async with proposal_client(factory, actor) as client:
            after_retirement = await client.get(
                f"/api/v1/projects/{command.target.proposal.project_id}/active-guide"
            )
            assert after_retirement.status_code == 200, after_retirement.text
            assert after_retirement.json() == response.json()
        async with factory() as session, session.begin():
            assert (
                await activation_service(session, actor, command, grant).activate(
                    command, actor=actor, request_id=uuid4()
                )
                == receipt
            )


async def test_registered_post_checker_activates_false_guide_with_real_authority(
    clean_postgres_database,
):
    """Public manager activation carries a separately selected POST image."""
    from tests.checkers.external.support import registry_spec
    from tests.projects.guide_compilation.proposals.public_support import proposal_client

    async with activation_case(
        clean_postgres_database,
        human_review_required=False,
        post_submit_registry_spec=registry_spec("post_submit"),
    ) as (factory, command, actor, _, _, _):
        target = command.target.proposal
        path = f"/api/v1/projects/{target.project_id}/guides/{target.guide_id}/activate"
        async with proposal_client(factory, actor) as client:
            response = await client.post(
                path,
                json=command.model_dump(mode="json", exclude={"idempotency_key"}),
                headers={"Idempotency-Key": str(command.idempotency_key)},
            )
            assert response.status_code == 200, response.text
            receipt = response.json()
            replay = await client.post(
                path,
                json=command.model_dump(mode="json", exclude={"idempotency_key"}),
                headers={"Idempotency-Key": str(command.idempotency_key)},
            )
            assert replay.status_code == 200 and replay.json() == receipt
        async with factory() as session:
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "active"
            assert str(guide.activation_operation_id) == receipt["operation_id"]
            result = await session.scalar(text(
                "SELECT canonical_result::jsonb FROM project_guide_compilations "
                "WHERE id=:id"
            ), {"id": command.target.proposal.compilation_id})
            assert "post_submit" in {item["stage"] for item in result["requirements"]}
            assert all("disposition" not in item for item in result["requirements"])
            selected = await session.scalar(text(
                "SELECT policy_body::jsonb FROM checker_policies WHERE id=:id"
            ), {"id": command.target.policy_id})
            assert [item["registry"]["capability_id"] for item in selected["entries"]] == [
                registry_spec("post_submit").capability_id
            ]
            assert await session.scalar(text(
                "SELECT human_review_required FROM review_policies WHERE id=:id"
            ), {"id": command.review.policy_id}) is False


@pytest.mark.parametrize("pinned", [True, False])
async def test_activation_custody_ignores_temporary_relation_shadows(
    clean_postgres_database, monkeypatch, pinned,
):
    """A stored search path, rather than a caller path, protects deferred custody."""
    from app.modules.projects.guide_mutation_repository import GuideMutationRepository

    original = GuideMutationRepository.complete

    async def shadow_after_complete(self, record, **kwargs):
        await original(self, record, **kwargs)
        if not pinned:
            # Sensitivity probe: roll back this DDL with the rejected activation.
            await self._session.execute(text(
                "ALTER FUNCTION public.require_guide_activation_custody(uuid, boolean) "
                "RESET search_path"
            ))
        # This leaves real authority, new-binding custody, and all triggers on.
        await self._session.execute(text(
            "CREATE TEMP TABLE review_policies (LIKE public.review_policies) ON COMMIT DROP"
        ))
        await self._session.execute(text(
            "CREATE TEMP TABLE project_guide_compilations "
            "(LIKE public.project_guide_compilations) ON COMMIT DROP"
        ))
        await self._session.execute(text("SET LOCAL search_path=pg_temp,public"))

    async with activation_case(clean_postgres_database, human_review_required=False) as (
        factory, command, actor, grant, _, _,
    ):
        monkeypatch.setattr(GuideMutationRepository, "complete", shadow_after_complete)
        if pinned:
            async with factory() as session, session.begin():
                receipt = await activation_service(session, actor, command, grant).activate(
                    command, actor=actor, request_id=uuid4()
                )
        else:
            with pytest.raises(DBAPIError, match="guide activation approved generation unavailable"):
                async with factory() as session, session.begin():
                    await activation_service(session, actor, command, grant).activate(
                        command, actor=actor, request_id=uuid4()
                    )
        async with factory() as session:
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            if pinned:
                assert guide.status == "active"
                assert guide.activation_operation_id == receipt.operation_id
            else:
                assert guide.status == "draft"
                assert guide.activation_operation_id is None


async def test_activation_default_authority_is_unavailable(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        async with factory() as session, session.begin():
            with pytest.raises(GuideProposalError, match="authority_unavailable"):
                await activation_service(session, actor, command, grant, authority=False).activate(
                    command, actor=actor, request_id=uuid4()
                )
        async with factory() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 0
            )
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "draft" and guide.activation_operation_id is None


async def test_later_checker_registration_attaches_to_unchanged_proposal_before_activation(
    clean_postgres_database,
):
    """F-020: later image publication changes human selection, not setup evidence."""
    from app.modules.checkers.api.external_policy import ExternalCheckerImageAttachment
    from app.modules.projects.api.guide_proposals import GuideProposalApproval
    from tests.checkers.external.support import registry_spec
    from tests.projects.guide_compilation.proposals.pg_support import (
        read_package,
        seed_selected_review_revision_inputs,
    )
    from tests.projects.guide_compilation.proposals.test_postgresql import approve
    from .pg_support import publish_policy
    from .source_fixtures import _register_external_checker_fixture, source_case

    async with source_case(clean_postgres_database) as (
        values, factory, finalization, actor, grant,
    ):
        before = await read_package(factory, finalization, actor, grant)
        assert {item.stage for item in before.result.requirements} == {
            "pre_submit", "post_submit"
        }
        assert values["pre_submit_attachments"] == ()
        assert values["post_submit_attachments"] == ()
        async with factory() as session:
            retained_before = (
                await session.execute(text(
                    "SELECT result_hash, canonical_result::jsonb FROM "
                    "project_guide_compilations WHERE id=:id"
                ), {"id": finalization.compilation_id})
            ).one()
            counts_before = (
                await session.scalar(text("SELECT count(*) FROM project_guide_compilation_attempts")),
                await session.scalar(text("SELECT count(*) FROM project_guide_compilations")),
            )

        pre_entry = await _register_external_checker_fixture(factory, registry_spec("pre_submit"))
        post_entry = await _register_external_checker_fixture(factory, registry_spec("post_submit"))
        values["pre_submit_attachments"] = (ExternalCheckerImageAttachment(
            requirement_id="project.archive_rules",
            registry_entry_id=pre_entry.registry_entry_id,
            registry_entry_digest=pre_entry.entry_digest,
            configuration={},
        ),)
        values["post_submit_attachments"] = (ExternalCheckerImageAttachment(
            requirement_id="project.post_evidence",
            registry_entry_id=post_entry.registry_entry_id,
            registry_entry_digest=post_entry.entry_digest,
            configuration={},
        ),)
        after = await read_package(factory, finalization, actor, grant)
        assert after.target == before.target
        assert after.target.result_hash == before.target.result_hash
        assert after.result == before.result
        async with factory() as session:
            retained_after = (
                await session.execute(text(
                    "SELECT result_hash, canonical_result::jsonb FROM "
                    "project_guide_compilations WHERE id=:id"
                ), {"id": finalization.compilation_id})
            ).one()
            counts_after = (
                await session.scalar(text("SELECT count(*) FROM project_guide_compilation_attempts")),
                await session.scalar(text("SELECT count(*) FROM project_guide_compilations")),
            )
        assert retained_after == retained_before
        assert counts_after == counts_before

        approval = await approve(
            factory,
            finalization,
            actor,
            grant,
            GuideProposalApproval(
                target=after.target,
                pre_submit_attachments=values["pre_submit_attachments"],
                post_submit_attachments=values["post_submit_attachments"],
                acknowledged_warning_hashes=after.warning_hashes,
                idempotency_key=uuid4(),
            ),
        )
        assert approval.target_digest == before.target.digest
        async with factory() as session:
            compiled_pre = await session.scalar(text(
                "SELECT compiled_bundle::jsonb FROM pre_submit_checker_policies WHERE id=:id"
            ), {"id": approval.pre_submit_policy_id})
        assert [entry["registry"]["registry_entry_id"] for entry in compiled_pre["entries"]] == [
            str(pre_entry.registry_entry_id)
        ]

        await seed_selected_review_revision_inputs(
            factory, finalization, actor, human_review_required=False
        )
        _, policy = await publish_policy(factory, finalization.project_id)
        command = await _activation_inputs(
            factory, finalization, approval, actor, grant, values, policy
        )
        assert command.target.proposal.result_hash == before.target.result_hash
        assert command.target.upstream.pre_submit_bundle_hash == approval.pre_submit_bundle_hash
        async with factory() as session:
            compiled_post = await session.scalar(text(
                "SELECT policy_body::jsonb FROM checker_policies WHERE id=:id"
            ), {"id": command.target.policy_id})
        assert [entry["registry"]["registry_entry_id"] for entry in compiled_post["entries"]] == [
            str(post_entry.registry_entry_id)
        ]
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        assert receipt.command.target.proposal.compilation_id == finalization.compilation_id
        async with factory() as session:
            guide = await session.get(ProjectGuide, str(finalization.guide_id))
            assert guide.status == "active"
            assert guide.activation_operation_id == receipt.operation_id
