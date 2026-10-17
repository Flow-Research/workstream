"""Real activation transaction, exact replay and default-deny controls."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.projects.models import ProjectGuide
from .pg_support import activation_case, activation_service, readiness_read


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


def _capability_outcome(*, supported):
    """Return the same requirement before and after exact capability coverage."""
    from app.interfaces.project_agents import (
        AtomicGuideRequirement,
        CapabilitySuggestion,
        PreSubmissionBindingProposal,
    )
    from tests.projects.guide_compilation.helpers import result

    outcome = result()
    refs = outcome.findings[0].evidence_refs
    requirement = AtomicGuideRequirement(
        requirement_id="specialist_archive",
        statement="Inspect the specialist archive before admission.",
        disposition="supported_pre_submit" if supported else "pre_submit_capability_gap",
        evidence_refs=refs,
    )
    return outcome.model_copy(
        update={
            "status": "draft_ready" if supported else "draft_ready_with_warnings",
            "findings": (
                outcome.findings[0].model_copy(
                    update={
                        "severity": "info" if supported else "warning",
                        "code": "guide.ready" if supported else "checker.capability_gap",
                        "message": (
                            "Exact checker coverage is available."
                            if supported
                            else "Register and bind the required checker capability."
                        ),
                    }
                ),
            ),
            "requirements": (requirement,),
            "pre_submit_bindings": (
                PreSubmissionBindingProposal(
                    requirement_id=requirement.requirement_id,
                    capability_id="acme.safe_archive",
                    capability_version="v1.2.3",
                    stage="pre_submit",
                ),
            )
            if supported
            else (),
            "capability_suggestions": ()
            if supported
            else (
                CapabilitySuggestion(
                    requirement_id=requirement.requirement_id,
                    stage="pre_submit",
                    title="Specialist archive checker",
                    rationale="The required immutable checker is not registered yet.",
                    evidence_refs=refs,
                ),
            ),
        }
    )


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
    """Public manager activation binds an exact registered POST requirement."""
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
            assert [item["disposition"] for item in result["requirements"]] == [
                "supported_post_submit"
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


async def test_checker_registration_requires_corrected_approval_before_activation(
    clean_postgres_database,
):
    """F-020 closes only after register, recompile, approve and exact activation."""
    from app.modules.projects.api.guide_proposals import (
        GuideProposalApproval,
        GuideProposalCorrection,
    )
    from tests.checkers.external.support import registry_spec
    from tests.projects.guide_compilation.proposals.pg_support import (
        finalize_corrected_attempt,
        read_package,
        seed_selected_review_revision_inputs,
    )
    from tests.projects.guide_compilation.proposals.test_postgresql import approve, correct
    from .pg_support import publish_policy
    from .source_fixtures import _register_external_checker_fixture, source_case

    gap, covered = _capability_outcome(supported=False), _capability_outcome(supported=True)
    async with source_case(
        clean_postgres_database,
        compilation_outcome=gap,
    ) as (values, factory, initial, actor, grant):
        package = await read_package(factory, initial, actor, grant)
        first = await approve(
            factory,
            initial,
            actor,
            grant,
            GuideProposalApproval(
                target=package.target,
                acknowledged_warning_hashes=package.warning_hashes,
                idempotency_key=uuid4(),
            ),
        )
        await _register_external_checker_fixture(factory, registry_spec("pre_submit"))
        _, policy = await publish_policy(factory, initial.project_id)
        await seed_selected_review_revision_inputs(
            factory, initial, actor, human_review_required=False
        )
        stale = await _activation_inputs(factory, initial, first, actor, grant, values, policy)
        async with factory() as session, session.begin():
            before = await _activation_effects(session)
            with pytest.raises(GuideProposalError, match="approval_blocked") as refusal:
                await activation_service(session, actor, stale, grant).activate(
                    stale, actor=actor, request_id=uuid4()
                )
            assert [item.model_dump(mode="json") for item in refusal.value.missing_capabilities] == [
                dict(requirement_id=item.requirement_id, stage=item.stage, title=item.title)
                for item in gap.capability_suggestions
            ]
            guide = await session.get(ProjectGuide, str(stale.target.proposal.guide_id))
            assert guide.status == "draft" and guide.activation_operation_id is None
            assert await _activation_effects(session) == before
        # PILOT-READ-3 C3: readiness reports the same refusal with the same capability list.
        readiness = await readiness_read(factory, initial.project_id, initial.guide_id)
        first_unmet = readiness.unmet[0]
        assert (first_unmet.code, first_unmet.reason) == (refusal.value.code, "checker_capability_missing")
        assert [item.model_dump(mode="json") for item in first_unmet.missing_capabilities] == [
            item.model_dump(mode="json") for item in refusal.value.missing_capabilities
        ]

        correction = await correct(
            factory,
            initial,
            actor,
            grant,
            GuideProposalCorrection(
                target=package.target,
                reason="Bind the registered checker to the required pre-admission stage.",
                idempotency_key=uuid4(),
            ),
        )
        successor = await finalize_corrected_attempt(
            factory, values, actor, correction, outcome=covered
        )
        revised = await read_package(factory, successor, actor, grant)
        second = await approve(
            factory,
            successor,
            actor,
            grant,
            GuideProposalApproval(
                target=revised.target,
                expected_previous_approval_operation_id=first.operation_id,
                expected_previous_approval_output_digest=revised.current_approval_output_digest,
                idempotency_key=uuid4(),
            ),
        )
        assert second.pre_submit_bundle_hash != first.pre_submit_bundle_hash
        command = await _activation_inputs(factory, successor, second, actor, grant, values, policy)
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        assert receipt.command.target.proposal.compilation_id == successor.compilation_id
        async with factory() as session, session.begin():
            with pytest.raises(GuideProposalError, match="proposal_(stale|unavailable)"):
                await activation_service(session, actor, stale, grant).activate(
                    stale, actor=actor, request_id=uuid4()
                )
