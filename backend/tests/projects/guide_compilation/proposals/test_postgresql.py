"""Real proposal, approval and correction transactions over finalized setup evidence."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.adapters.artifacts import guide_document_manifest_port
from app.modules.checkers.catalogue import (
    build_pre_submission_checker_catalogue,
    project_guide_pre_submission_capabilities,
)
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval,
    GuideProposalCorrection,
    GuideProposalError,
)
from app.modules.projects.guide_compilation.models import (
    ProjectGuideProposalApproval,
    ProjectGuideProposalCorrection,
)
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from app.modules.projects.guide_setup_continuation import retryable_compilation_dispatch_predicate
from app.modules.projects.models import ProjectSetupRun
from tests.projects.guide_compilation.finalization.pg_support import finalize, stored_state
from .pg_support import ProposalAuthority, proposal_case, read_package


async def approve(factory, command, actor, grant, payload):
    try:
        async with factory() as session, session.begin():
            planner = build_pre_submission_checker_catalogue()
            return await GuideProposalService(
                session,
                ProposalAuthority(
                    session,
                    actor,
                    command.project_id,
                    grant,
                ),
            ).approve(
                payload,
                actor=actor,
                request_id=uuid4(),
                material=guide_document_manifest_port(session),
                pre_capabilities=project_guide_pre_submission_capabilities(planner),
                post_capabilities=current_post_submit_catalogue(),
                planner=planner,
            )
    except GuideProposalError as exc:
        raise exc from exc.__context__


async def correct(factory, command, actor, grant, payload):
    try:
        async with factory() as session, session.begin():
            return await GuideProposalService(
                session,
                ProposalAuthority(
                    session,
                    actor,
                    command.project_id,
                    grant,
                ),
            ).request_correction(payload, actor=actor, request_id=uuid4())
    except GuideProposalError as exc:
        raise exc from exc.__context__


async def test_review_package_is_exact_complete_and_redacted(clean_postgres_database):
    from app.interfaces.project_agents import ProjectGuideCompilationResult
    from tests.projects.guide_compilation.helpers import result

    body = result().model_dump(mode="json")
    evidence = body["findings"][0]["evidence_refs"]
    body.update(
        status="guide_blocked", submission_artifact_policy=None,
        requirements=[
            dict(requirement_id="packet", statement="Limit artifact file size.",
                 disposition="supported_pre_submit", evidence_refs=evidence),
            dict(requirement_id="coverage", statement="Check acceptance criteria coverage.",
                 disposition="supported_post_submit", evidence_refs=evidence),
            dict(requirement_id="semantic", statement="Evaluate specialist correctness.",
                 disposition="post_submit_capability_gap", evidence_refs=evidence),
        ],
        pre_submit_bindings=[dict(requirement_id="packet", capability_id="policy.file_size.limit",
                                 capability_version="v1", stage="pre_submit")],
        post_submit_bindings=[dict(requirement_id="coverage", capability_id="check_acceptance_criteria_present",
                                  capability_version="v0.1", stage="post_submit", parameters=[])],
        capability_suggestions=[dict(requirement_id="semantic", stage="post_submit",
                                     title="Specialist correctness evaluator", rationale="The catalogue lacks this evaluation.",
                                     evidence_refs=evidence)],
        setup_notes=["A project manager must review the specialist evaluation gap."],
    )
    body["findings"][0]["severity"] = "blocking_gap"
    outcome = ProjectGuideCompilationResult.model_validate(body)
    async with proposal_case(clean_postgres_database, classification="guide_blocked", outcome=outcome) as (
        _, factory, command, actor, grant
    ):
        package = await read_package(factory, command, actor, grant)
        assert package.target.compilation_id == command.compilation_id
        assert package.target.setup_run_id == command.setup_run_id
        assert package.current is True
        expected = outcome.model_dump(mode="json")
        for section in ("findings", "requirements", "capability_suggestions"):
            for item in expected[section]:
                item["evidence_refs"] = [dict(document_number=1, start_page=ref["start_page"],
                                             end_page=ref["end_page"], section=ref["section"])
                                         for ref in item["evidence_refs"]]
        assert package.result.model_dump(mode="json") == expected
        serialized = package.model_dump_json()
        for forbidden in ("source_item_id", "document_version_id", "provider_object_ref",
                          "runtime_configuration", "provider_idempotency_key", "put_attempt_id"):
            assert forbidden not in serialized


async def test_unified_approval_postgresql_commits_exact_chain_and_provenance(
    clean_postgres_database,
):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        before = await stored_state(factory, command)
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalApproval(target=package.target, idempotency_key=uuid4())
        receipt = await approve(factory, command, actor, grant, payload)
        replay = await approve(factory, command, actor, grant, payload)
        assert replay == receipt
        async with factory() as session:
            operations = (
                await session.scalars(
                    select(ProjectGuideProposalApproval).where(
                        ProjectGuideProposalApproval.guide_id == str(command.guide_id)
                    )
                )
            ).all()
            assert len(operations) == 1
            assert operations[0].receipt_json == receipt.model_dump(mode="json")
        after = await read_package(factory, command, actor, grant)
        assert after.target == package.target
        assert after.artifact_policy_status == "approved"
        assert after.current_approval_operation_id == receipt.operation_id
        await finalize(factory, values, command)
        assert (await stored_state(factory, command))[:2] == before[:2]


async def test_correction_postgresql_replay_creates_one_successor(clean_postgres_database):
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        before = await stored_state(factory, command)
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalCorrection(
            target=package.target,
            idempotency_key=uuid4(),
            reason="  Reconsider the existing evidence.  ",
        )
        receipts = []
        for _ in range(2):
            receipts.append(await correct(factory, command, actor, grant, payload))
        assert receipts[0] == receipts[1]
        async with factory() as session:
            corrections = (
                await session.scalars(
                    select(ProjectGuideProposalCorrection).where(
                        ProjectGuideProposalCorrection.guide_id == str(command.guide_id)
                    )
                )
            ).all()
            assert len(corrections) == 1
            assert corrections[0].reason == "Reconsider the existing evidence."
            successor = await session.get(ProjectSetupRun, str(receipts[0].successor_setup_run_id))
            assert successor.setup_generation == command.setup_generation + 1
            assert successor.status == "correction_requested"
            assert successor.celery_task_id is None
            recoverable = await session.scalar(
                select(ProjectSetupRun.id).where(
                    ProjectSetupRun.id == successor.id,
                    retryable_compilation_dispatch_predicate(),
                )
            )
            assert recoverable is None
        assert (await stored_state(factory, command))[:2] == before[:2]
        with pytest.raises(GuideProposalError, match="proposal_stale"):
            await approve(
                factory,
                command,
                actor,
                grant,
                GuideProposalApproval(
                    target=package.target,
                    idempotency_key=uuid4(),
                ),
            )


async def test_correction_uses_canonical_human_request_and_binds_feedback(clean_postgres_database):
    from app.interfaces.project_agents import project_guide_compilation_prompt_bytes
    from app.modules.authorization.guide_compilation import (
        ProjectGuideCompilationAuthorizationAdapter,
    )
    from app.modules.authorization.kernel import AuthorizationService
    from app.modules.authorization.prepared import PreparedAuthorizationService
    from app.modules.authorization.repository import AdminAuthorizationRepository
    from app.modules.authorization.runtime import (
        ActorStatus,
        HumanAuthorizationContext,
        IdentityLinkStatus,
    )
    from app.modules.projects.guide_compilation.request_inputs import CompilationRequestInputs
    from app.modules.projects.guide_compilation.service import GuideCompilationService
    from app.modules.projects.guide_compilation.validation import identity_from_attempt
    from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt
    from tests.projects.guide_compilation.helpers import runtime_configuration

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        correction = await correct(
            factory,
            command,
            actor,
            grant,
            GuideProposalCorrection(
                target=package.target,
                idempotency_key=uuid4(),
                reason="Reconsider the existing source evidence.",
            ),
        )
        ctx = HumanAuthorizationContext(
            actor_profile_id=actor.actor_profile_id,
            actor_kind=actor.actor_kind,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=actor.identity_link_id,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        planner = build_pre_submission_checker_catalogue()
        pre, post = (
            project_guide_pre_submission_capabilities(planner),
            current_post_submit_catalogue(),
        )
        receipts = []
        for _ in range(2):
            async with factory() as session:
                repository = AdminAuthorizationRepository(session)
                kernel = AuthorizationService(session, ctx, admin_repository=repository)
                prepared = PreparedAuthorizationService(session, ctx, kernel, repository)
                service = GuideCompilationService(
                    session,
                    ProjectGuideCompilationAuthorizationAdapter(kernel, prepared),
                    request_inputs=CompilationRequestInputs(
                        guide_document_manifest_port(session),
                        pre,
                        post,
                        runtime_configuration(),
                    ),
                )
                receipts.append(
                    await service.request_correction(
                        actor=actor,
                        correction_operation_id=correction.operation_id,
                    )
                )
        assert receipts[0].attempt_id == receipts[1].attempt_id
        async with factory() as session:
            attempt = await session.get(ProjectGuideCompilationAttempt, receipts[0].attempt_id)
            inputs = CompilationRequestInputs(
                guide_document_manifest_port(session),
                pre,
                post,
                runtime_configuration(),
            )
            setup = await session.get(ProjectSetupRun, str(correction.successor_setup_run_id))
            context = await inputs.context_for_setup(session, setup)
            assert type(identity_from_attempt(attempt)).from_context(
                context
            ) == identity_from_attempt(attempt)
            assert context.correction_feedback.reason == "Reconsider the existing source evidence."
            assert context.correction_feedback.predecessor_compilation_id == command.compilation_id
            assert (
                b"Reconsider the existing source evidence."
                in project_guide_compilation_prompt_bytes(context)
            )
            assert attempt.status == "compilation_reserved"
            assert context.material.source_snapshot_id == package.target.source_snapshot_id


async def test_approval_rejects_every_substituted_target_identity(clean_postgres_database):
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        replacements = {}
        for name, value in package.target.model_dump().items():
            if name == "component_hashes":
                for component in type(package.target.component_hashes).model_fields:
                    replacements["component:" + component] = dict(
                        component_hashes=package.target.component_hashes.model_copy(
                            update={component: "sha256:" + "b" * 64}
                        )
                    )
            elif isinstance(value, type(uuid4())):
                replacements[name] = {name: uuid4()}
            elif isinstance(value, str):
                replacements[name] = {
                    name: "sha256:" + "b" * 64 if value.startswith("sha256:") else value + "-other"
                }
            elif isinstance(value, int):
                replacements[name] = {name: value + 1}
        for name, patch in replacements.items():
            with pytest.raises(GuideProposalError) as denied:
                await approve(
                    factory,
                    command,
                    actor,
                    grant,
                    GuideProposalApproval(
                        target=package.target.model_copy(update=patch),
                        idempotency_key=uuid4(),
                    ),
                )
            assert denied.value.code in {
                "proposal_stale",
                "proposal_unavailable",
                "authority_unavailable",
            }, name
        receipt = await approve(
            factory,
            command,
            actor,
            grant,
            GuideProposalApproval(
                target=package.target,
                idempotency_key=uuid4(),
            ),
        )
        assert receipt.artifact_policy_id == package.target.artifact_policy_id


async def test_warning_acknowledgment_is_exact_and_required(clean_postgres_database):
    async with proposal_case(
        clean_postgres_database, classification="draft_ready_with_warnings"
    ) as (
        _,
        factory,
        command,
        actor,
        grant,
    ):
        package = await read_package(factory, command, actor, grant)
        assert len(package.warning_hashes) == 1
        for warnings in ((), ("sha256:" + "b" * 64,)):
            with pytest.raises(GuideProposalError, match="approval_blocked"):
                await approve(
                    factory,
                    command,
                    actor,
                    grant,
                    GuideProposalApproval(
                        target=package.target,
                        idempotency_key=uuid4(),
                        acknowledged_warning_hashes=warnings,
                    ),
                )
        receipt = await approve(
            factory,
            command,
            actor,
            grant,
            GuideProposalApproval(
                target=package.target,
                idempotency_key=uuid4(),
                acknowledged_warning_hashes=package.warning_hashes,
            ),
        )
        assert receipt.artifact_policy_id == package.target.artifact_policy_id


async def test_blocked_result_allows_correction_but_never_approval(clean_postgres_database):
    async with proposal_case(clean_postgres_database, classification="guide_blocked") as (
        _,
        factory,
        command,
        actor,
        grant,
    ):
        package = await read_package(factory, command, actor, grant)
        assert package.target.artifact_policy_id is None
        with pytest.raises(GuideProposalError, match="approval_blocked"):
            await approve(
                factory,
                command,
                actor,
                grant,
                GuideProposalApproval(
                    target=package.target,
                    idempotency_key=uuid4(),
                ),
            )
        receipt = await correct(
            factory,
            command,
            actor,
            grant,
            GuideProposalCorrection(
                target=package.target,
                idempotency_key=uuid4(),
                reason="The cited source contains the missing requirement.",
            ),
        )
        assert receipt.successor_setup_generation == command.setup_generation + 1


async def test_capability_close_failure_rolls_back_every_decision_effect(clean_postgres_database):
    from sqlalchemy import func
    from app.modules.tasks.models import AuditEvent

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        before = await stored_state(factory, command)
        planner = build_pre_submission_checker_catalogue()
        for action in ("approve", "correct"):
            with pytest.raises(GuideProposalError, match="authority_unavailable"):
                async with factory() as session, session.begin():
                    service = GuideProposalService(
                        session,
                        ProposalAuthority(
                            session,
                            actor,
                            command.project_id,
                            grant,
                            close_error=True,
                        ),
                    )
                    if action == "approve":
                        await service.approve(
                            GuideProposalApproval(
                                target=package.target,
                                idempotency_key=uuid4(),
                            ),
                            actor=actor,
                            request_id=uuid4(),
                            material=guide_document_manifest_port(session),
                            pre_capabilities=project_guide_pre_submission_capabilities(planner),
                            post_capabilities=current_post_submit_catalogue(),
                            planner=planner,
                        )
                    else:
                        await service.request_correction(
                            GuideProposalCorrection(
                                target=package.target,
                                idempotency_key=uuid4(),
                                reason="Review the source evidence again.",
                            ),
                            actor=actor,
                            request_id=uuid4(),
                        )
            assert await stored_state(factory, command) == before
            async with factory() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(
                            AuditEvent.project_id == str(command.project_id),
                            AuditEvent.action_id.in_(
                                [
                                    "project.submission_artifact_policy.approve",
                                    "project.guide_compilation.correction.request",
                                ]
                            ),
                        )
                    )
                    == 0
                )
        receipt = await approve(
            factory,
            command,
            actor,
            grant,
            GuideProposalApproval(
                target=package.target,
                idempotency_key=uuid4(),
            ),
        )
        assert receipt.artifact_policy_id == package.target.artifact_policy_id


async def test_database_preserves_approved_content_lifecycle_and_operation(clean_postgres_database):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        receipt = await approve(
            factory,
            command,
            actor,
            grant,
            GuideProposalApproval(
                target=package.target,
                idempotency_key=uuid4(),
            ),
        )
        for table, key, identity, change, message in (
            (
                "submission_artifact_policies",
                "id",
                str(receipt.artifact_policy_id),
                "lifecycle_status='draft'",
                "approved proposal lifecycle cannot revert",
            ),
            (
                "submission_artifact_policies",
                "id",
                str(receipt.artifact_policy_id),
                "change_summary='Changed after approval'",
                "unified proposal content is immutable",
            ),
            (
                "submission_artifact_policies",
                "id",
                str(receipt.artifact_policy_id),
                "lifecycle_status='superseded',superseded_at=now()",
                "proposal supersession requires exact successor approval",
            ),
            (
                "effective_project_submission_artifact_policies",
                "id",
                str(receipt.effective_policy_id),
                "effective_policy_hash='sha256:' || repeat('b',64)",
                "unified proposal content is immutable",
            ),
            (
                "pre_submit_checker_policies",
                "id",
                str(receipt.pre_submit_policy_id),
                "lifecycle_status='pending_compilation'",
                "proposal approval lifecycle mismatch",
            ),
            (
                "project_guide_proposal_approvals",
                "operation_id",
                receipt.operation_id,
                "target_digest='sha256:' || repeat('b',64)",
                "guide proposal operation is immutable",
            ),
        ):
            with pytest.raises(DBAPIError, match=message):
                async with factory() as session, session.begin():
                    await session.execute(
                        text(f"UPDATE {table} SET {change} WHERE {key}=:id"), {"id": identity}
                    )
        after = await read_package(factory, command, actor, grant)
        assert after.target == package.target
        assert after.artifact_policy_status == "approved"


@pytest.mark.parametrize("omitted", [None, "reservation", "operation"])
async def test_unified_approval_postgresql_requires_reservation_and_operation(
    clean_postgres_database,
    monkeypatch,
    omitted,
):
    from contextlib import nullcontext
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.modules.projects.submission_policy_mutation_repository import (
        SubmissionPolicyMutationReplayRepository,
    )

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        planner = build_pre_submission_checker_catalogue()
        if omitted == "reservation":

            async def reserve_without_record(*_args, **_kwargs):
                return "claimed", None

            async def complete_without_record(*_args, **_kwargs):
                return None

            monkeypatch.setattr(
                SubmissionPolicyMutationReplayRepository, "reserve", reserve_without_record
            )
            monkeypatch.setattr(
                SubmissionPolicyMutationReplayRepository, "complete", complete_without_record
            )
        expected = {
            "reservation": "proposal approval reservation or output custody mismatch",
            "operation": "immutable proposal approval operation missing",
        }
        expectation = (
            pytest.raises(DBAPIError, match=expected[omitted]) if omitted else nullcontext()
        )
        with expectation:
            async with factory() as session, session.begin():
                if omitted == "operation":
                    add = session.add

                    def add_without_operation(row, **kwargs):
                        if not isinstance(row, ProjectGuideProposalApproval):
                            add(row, **kwargs)

                    monkeypatch.setattr(session, "add", add_without_operation)
                await GuideProposalService(
                    session,
                    ProposalAuthority(
                        session,
                        actor,
                        command.project_id,
                        grant,
                    ),
                ).approve(
                    GuideProposalApproval(
                        target=package.target,
                        idempotency_key=uuid4(),
                    ),
                    actor=actor,
                    request_id=uuid4(),
                    material=guide_document_manifest_port(session),
                    pre_capabilities=project_guide_pre_submission_capabilities(planner),
                    post_capabilities=current_post_submit_catalogue(),
                    planner=planner,
                )
                # Reach this exact deferred guard with complete output pointers;
                # other constraints cannot mask the missing relation under test.
                await session.execute(
                    text("SET CONSTRAINTS guide_proposal_approval_custody IMMEDIATE")
                )
        async with factory() as session:
            from app.modules.projects.models import SubmissionArtifactPolicy

            policy = await session.get(
                SubmissionArtifactPolicy, str(package.target.artifact_policy_id)
            )
            assert policy.lifecycle_status == ("draft" if omitted else "approved")


async def test_corrected_generation_replaces_exact_approved_chain_and_preserves_history(
    clean_postgres_database,
):
    from app.modules.projects.models import (
        SubmissionArtifactPolicy,
        EffectiveProjectSubmissionArtifactPolicy,
        PreSubmitCheckerPolicy,
    )
    from .pg_support import finalize_corrected_attempt

    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        first_package = await read_package(factory, command, actor, grant)
        first_payload = GuideProposalApproval(target=first_package.target, idempotency_key=uuid4())
        first = await approve(
            factory,
            command,
            actor,
            grant,
            first_payload,
        )
        original = await stored_state(factory, command)
        correction = await correct(
            factory,
            command,
            actor,
            grant,
            GuideProposalCorrection(
                target=first_package.target,
                idempotency_key=uuid4(),
                reason="Reconsider the proposal against the source.",
            ),
        )
        await assert_approval_replay_unchanged(factory, command, actor, grant, first_payload, first)
        next_command = await finalize_corrected_attempt(factory, values, actor, correction)
        next_package = await read_package(factory, next_command, actor, grant)
        assert next_package.current_approval_operation_id == first.operation_id
        with pytest.raises(GuideProposalError, match="proposal_stale"):
            await approve(
                factory,
                next_command,
                actor,
                grant,
                GuideProposalApproval(
                    target=next_package.target,
                    idempotency_key=uuid4(),
                ),
            )
        second = await approve(
            factory,
            next_command,
            actor,
            grant,
            GuideProposalApproval(
                target=next_package.target,
                idempotency_key=uuid4(),
                expected_previous_approval_operation_id=first.operation_id,
                expected_previous_approval_output_digest=next_package.current_approval_output_digest,
            ),
        )
        await assert_approval_replay_unchanged(factory, command, actor, grant, first_payload, first)
        assert first.effective_policy_hash == second.effective_policy_hash
        assert first.pre_submit_bundle_hash == second.pre_submit_bundle_hash
        for model, old_id, new_id, pointer in (
            (
                SubmissionArtifactPolicy,
                first.artifact_policy_id,
                second.artifact_policy_id,
                "supersedes_policy_id",
            ),
            (
                EffectiveProjectSubmissionArtifactPolicy,
                first.effective_policy_id,
                second.effective_policy_id,
                "supersedes_effective_policy_id",
            ),
            (
                PreSubmitCheckerPolicy,
                first.pre_submit_policy_id,
                second.pre_submit_policy_id,
                "supersedes_pre_submit_checker_policy_id",
            ),
        ):
            async with factory() as session:
                old = await session.get(model, str(old_id))
                new = await session.get(model, str(new_id))
                assert old.lifecycle_status == "superseded"
                assert old.superseded_at is not None
                assert getattr(new, pointer) == str(old_id)
        assert (await stored_state(factory, command))[:2] == original[:2]
        retained = await read_package(factory, command, actor, grant)
        assert retained.target == first_package.target
        assert retained.current is False
        assert retained.artifact_policy_status == "superseded"


async def test_concurrent_approvals_have_one_winner_and_one_exact_replay(clean_postgres_database):
    import asyncio
    from sqlalchemy import func

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        payloads = [
            GuideProposalApproval(target=package.target, idempotency_key=uuid4()) for _ in range(2)
        ]
        outcomes = await asyncio.gather(
            *(approve(factory, command, actor, grant, payload) for payload in payloads),
            return_exceptions=True,
        )
        successes = [
            (payload, result)
            for payload, result in zip(payloads, outcomes)
            if not isinstance(result, Exception)
        ]
        failures = [result for result in outcomes if isinstance(result, Exception)]
        assert len(successes) == len(failures) == 1
        assert isinstance(failures[0], GuideProposalError)
        assert failures[0].code == "proposal_stale"
        payload, receipt = successes[0]
        assert await approve(factory, command, actor, grant, payload) == receipt
        async with factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(ProjectGuideProposalApproval))
                == 1
            )


async def test_approval_requires_current_manager_authority_even_on_replay(clean_postgres_database):

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalApproval(target=package.target, idempotency_key=uuid4())
        receipt = await approve(factory, command, actor, grant, payload)
        # A different (nonexistent) grant cannot confer manager authority even
        # when all persisted result and replay identities are otherwise valid.
        for operation in (
            read_package(factory, command, actor, str(uuid4())),
            approve(factory, command, actor, str(uuid4()), payload),
            correct(
                factory,
                command,
                actor,
                str(uuid4()),
                GuideProposalCorrection(
                    target=package.target,
                    idempotency_key=uuid4(),
                    reason="Recheck the existing source.",
                ),
            ),
        ):
            with pytest.raises(GuideProposalError, match="authority_unavailable"):
                await operation
        assert await approve(factory, command, actor, grant, payload) == receipt


async def test_projected_draft_content_cannot_be_changed_before_approval(clean_postgres_database):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        with pytest.raises(DBAPIError, match="unified proposal content is immutable"):
            async with factory() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE submission_artifact_policies SET policy_body=jsonb_set(policy_body::jsonb,"
                        "'{allowed_storage_schemes}','[\"local\"]'::jsonb)::json WHERE id=:id"
                    ),
                    {"id": str(package.target.artifact_policy_id)},
                )
        assert await read_package(factory, command, actor, grant) == package
        assert (
            await approve(
                factory,
                command,
                actor,
                grant,
                GuideProposalApproval(
                    target=package.target,
                    idempotency_key=uuid4(),
                ),
            )
        ).artifact_policy_id == package.target.artifact_policy_id


@pytest.mark.parametrize("guide_version", ["v0.1", "example-proof"])
async def test_approval_preserves_opaque_guide_version(clean_postgres_database, guide_version):
    async with proposal_case(clean_postgres_database, guide_version=guide_version) as (
        values, factory, command, actor, grant
    ):
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalApproval(target=package.target, idempotency_key=uuid4())
        receipt = await approve(factory, command, actor, grant, payload)
        assert await approve(factory, command, actor, grant, payload) == receipt
        async with factory() as session:
            operation = await session.get(ProjectGuideProposalApproval, receipt.operation_id)
            assert operation.effective_pre_submit_plan["lineage"]["guide_version"] == guide_version
            assert operation.target_json["guide_version"] == guide_version
        await finalize(factory, values, command)


@pytest.mark.parametrize("authority_change", ["revoked_grant", "suspended_actor", "revoked_link", "audit", "operator", "system_manager", "foreign_project"])
async def test_stored_authority_variants_deny_review_replay_and_correction(clean_postgres_database, authority_change):
    from sqlalchemy import text
    from .pg_support import seed_review_actor, revoke_review_grant
    from project_create_fixtures import seed_historical_project

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalApproval(target=package.target, idempotency_key=uuid4())
        receipt = await approve(factory, command, actor, grant, payload)
        assert await approve(factory, command, actor, grant, payload) == receipt
        denied_grant = grant
        if authority_change == "revoked_grant":
            await revoke_review_grant(factory, actor, grant)
        elif authority_change in {"suspended_actor", "revoked_link"}:
            async with factory() as session, session.begin():
                if authority_change == "suspended_actor":
                    await session.execute(text("UPDATE actor_profiles SET status='suspended',suspended_by=:id,suspended_at=now(),suspension_reason='Test turnover' WHERE id=:id"), {"id": str(actor.actor_profile_id)})
                else:
                    await session.execute(text("UPDATE actor_identity_links SET status='revoked',revoked_by=:actor,revoked_at=now(),revoked_reason='Test turnover' WHERE id=:id"), {"actor": str(actor.actor_profile_id), "id": str(actor.identity_link_id)})
        else:
            project = command.project_id
            role, scope = {"audit": ("audit_authority", "project"), "operator": ("operator", "system"),
                           "system_manager": ("project_manager", "system"), "foreign_project": ("project_manager", "project")}[authority_change]
            if authority_change == "foreign_project":
                project = uuid4()
                async with factory() as session, session.begin():
                    await seed_historical_project(session, project_id=str(project), name="Foreign guide owner", slug=f"foreign-{project}")
            _, denied_grant = await seed_review_actor(factory, project, actor=actor, role=role, scope=scope)
        before = await stored_state(factory, command)
        async with factory() as session:
            audit_before = (await session.execute(text("SELECT id FROM audit_events ORDER BY id"))).all()
        for operation in (
            read_package(factory, command, actor, denied_grant),
            approve(factory, command, actor, denied_grant, payload),
            correct(factory, command, actor, denied_grant, GuideProposalCorrection(
                target=package.target, idempotency_key=uuid4(), reason="Reconsider this proposal.")),
        ):
            with pytest.raises(GuideProposalError, match="authority_unavailable"):
                await operation
        assert await stored_state(factory, command) == before
        async with factory() as session:
            assert (await session.execute(text("SELECT id FROM audit_events ORDER BY id"))).all() == audit_before
            assert (await session.execute(text("SELECT count(*) FROM project_guide_proposal_corrections"))).scalar_one() == 0


async def test_another_current_manager_can_admit_correction_after_creator_revocation(clean_postgres_database):
    from .pg_support import seed_review_actor, revoke_review_grant, request_corrected_attempt
    from app.modules.projects.guide_compilation.models import ProjectGuideCompilationRequestOperation

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        before = await stored_state(factory, command)
        successor = await correct(factory, command, actor, grant, GuideProposalCorrection(
            target=package.target, idempotency_key=uuid4(), reason="Recheck the guide requirement."))
        second_actor, _ = await seed_review_actor(factory, command.project_id)
        await revoke_review_grant(factory, actor, grant)
        requested = await request_corrected_attempt(factory, second_actor, successor)
        assert await request_corrected_attempt(factory, second_actor, successor) == requested
        async with factory() as session:
            correction = await session.get(ProjectGuideProposalCorrection, successor.operation_id)
            setup = await session.get(ProjectSetupRun, str(successor.successor_setup_run_id))
            operation = (await session.scalars(select(ProjectGuideCompilationRequestOperation).where(
                ProjectGuideCompilationRequestOperation.attempt_id == requested.attempt_id))).one()
            assert correction.actor_profile_id == str(actor.actor_profile_id)
            assert setup.authorized_by_actor_profile_id == str(actor.actor_profile_id)
            assert operation.actor_profile_id == str(second_actor.actor_profile_id)
            assert setup.status == "queued"
        assert await stored_state(factory, command) == before


async def assert_approval_replay_unchanged(factory, command, actor, grant, payload, receipt):
    from sqlalchemy import text

    async def counts():
        async with factory() as session:
            return (await session.execute(text(
                "SELECT (SELECT count(*) FROM project_guide_proposal_approvals),"
                "(SELECT count(*) FROM submission_policy_mutation_idempotency_records),"
                "(SELECT count(*) FROM effective_project_submission_artifact_policies),"
                "(SELECT count(*) FROM pre_submit_checker_policies),"
                "(SELECT count(*) FROM audit_events)"
            ))).one()
    before = await counts()
    assert await approve(factory, command, actor, grant, payload) == receipt
    assert await counts() == before


@pytest.mark.parametrize("activate_before_commit", [False, True])
async def test_database_approval_requires_guide_to_remain_draft(clean_postgres_database, activate_before_commit):
    from contextlib import nullcontext
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from .pg_support import seed_selected_review_revision_inputs

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        await seed_selected_review_revision_inputs(factory, command, actor)
        package = await read_package(factory, command, actor, grant)
        before = await stored_state(factory, command)
        expected = pytest.raises(DBAPIError, match="proposal approval target is no longer current") if activate_before_commit else nullcontext()
        with expected:
            async with factory() as session, session.begin():
                if activate_before_commit:
                    # Transaction rollback restores these unrelated activation prerequisites.
                    for trigger in ("guide_mutation_product_custody", "guide_lineage_lifecycle_guard"):
                        await session.execute(text(f"ALTER TABLE project_guides DISABLE TRIGGER {trigger}"))
                planner = build_pre_submission_checker_catalogue()
                await GuideProposalService(session, ProposalAuthority(session, actor, command.project_id, grant)).approve(
                    GuideProposalApproval(target=package.target, idempotency_key=uuid4()), actor=actor, request_id=uuid4(),
                    material=guide_document_manifest_port(session),
                    pre_capabilities=project_guide_pre_submission_capabilities(planner),
                    post_capabilities=current_post_submit_catalogue(), planner=planner,
                )
                if activate_before_commit:
                    # Stage lifecycle drift after valid approval assembly to reach the DB guard itself.
                    await session.execute(text("UPDATE project_guides SET status='active',approved_by=:actor,effective_at=now() WHERE id=:guide"),
                                          {"actor": str(actor.actor_profile_id), "guide": str(command.guide_id)})
                await session.execute(text("SET CONSTRAINTS guide_proposal_approval_custody IMMEDIATE"))
        if activate_before_commit:
            assert await stored_state(factory, command) == before
            async with factory() as session:
                assert await session.scalar(text("SELECT count(*) FROM pg_trigger WHERE tgrelid='project_guides'::regclass AND tgenabled='D'")) == 0
                for table in ("project_guide_proposal_approvals", "submission_policy_mutation_idempotency_records",
                              "effective_project_submission_artifact_policies", "pre_submit_checker_policies"):
                    assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
                assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE action_id='project.submission_artifact_policy.approve'")) == 0
