"""Real proposal, approval and correction transactions over finalized setup evidence."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.adapters.artifacts import guide_document_manifest_port
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    project_guide_compilation_prompt_bytes,
)
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
from app.modules.projects.api import (
    ProjectGuideCompilationExecutionClassification,
    ProjectGuideCompilationExecutionCommand,
)
from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval,
    GuideProposalCorrection,
    GuideProposalError,
)
from app.modules.checkers.api.external_policy import ExternalCheckerImageAttachment
from app.modules.projects.guide_compilation.models import (
    ProjectGuideCompilation,
    ProjectGuideCompilationAttempt,
    ProjectGuideProposalApproval,
    ProjectGuideProposalCorrection,
)
from app.modules.projects.guide_compilation.orchestrator import GuideCompilationOrchestrator
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from app.modules.projects.guide_compilation.request_inputs import CompilationRequestInputs
from app.modules.projects.guide_compilation.service import GuideCompilationService
from app.modules.projects.guide_compilation.validation import identity_from_attempt
from app.modules.projects.guide_setup_continuation import retryable_compilation_dispatch_predicate
from app.modules.projects.models import ProjectSetupRun
from tests.projects.guide_compilation.finalization.pg_support import finalize, stored_state
from tests.projects.guide_compilation.helpers import runtime_configuration
from tests.projects.guide_compilation.test_hidden_orchestrator_postgresql import _Runtime, _backend

from .pg_support import ProposalAuthority, proposal_case, read_package


async def approve(factory, command, actor, grant, payload):
    try:
        async with factory() as session, session.begin():
            from app.adapters.checkers import external_checker_registry_reader, model_profile_reader

            return await GuideProposalService(
                session,
                ProposalAuthority(
                    session,
                    actor,
                    command.project_id,
                    grant,
                ),
                external_checker_registry_reader(session),
                model_profile_reader(session),
            ).approve(
                payload,
                actor=actor,
                request_id=uuid4(),
            )
    except GuideProposalError as exc:
        raise exc from exc.__context__


async def correct(factory, command, actor, grant, payload, *, authority_resource=None):
    try:
        async with factory() as session, session.begin():
            return await GuideProposalService(
                session,
                ProposalAuthority(
                    session,
                    actor,
                    command.project_id,
                    grant,
                    resource_override=authority_resource,
                ),
            ).request_correction(payload, actor=actor, request_id=uuid4())
    except GuideProposalError as exc:
        raise exc from exc.__context__


async def test_review_package_is_exact_complete_and_redacted(clean_postgres_database):
    from tests.projects.guide_compilation.helpers import generated_result

    outcome = generated_result()
    async with proposal_case(
        clean_postgres_database,
        classification=outcome.status,
        outcome=outcome,
    ) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        assert package.target.compilation_id == command.compilation_id
        assert package.target.setup_run_id == command.setup_run_id
        assert package.current is True
        expected = outcome.model_dump(mode="json")
        assert len(expected["requirements"]) == 1
        assert expected["requirements"][0]["stage"] == "pre_submit"
        assert "pre_submit_bindings" not in expected
        assert "post_submit_bindings" not in expected
        for section in ("findings", "requirements"):
            for item in expected[section]:
                item["evidence_refs"] = [
                    dict(
                        document_number=1,
                        start_page=ref["start_page"],
                        end_page=ref["end_page"],
                        section=ref["section"],
                    )
                    for ref in item["evidence_refs"]
                ]
        assert package.result.model_dump(mode="json") == expected
        serialized = package.model_dump_json()
        for forbidden in (
            "source_item_id",
            "document_version_id",
            "provider_object_ref",
            "runtime_configuration",
            "provider_idempotency_key",
            "put_attempt_id",
        ):
            assert forbidden not in serialized


async def test_later_publication_and_one_human_image_cover_independent_suggestions(
    clean_postgres_database,
):
    from tests.checkers.external.support import registry_spec
    from tests.projects.guide_activation.source_fixtures import _register_external_checker_fixture
    from tests.projects.guide_compilation.helpers import generated_result

    suggestion = generated_result().requirements[0]
    outcome = generated_result().model_copy(update={
        "requirements": (
            suggestion,
            suggestion.model_copy(update={"suggestion_id": "another_suggestion"}),
        ),
    })
    async with proposal_case(clean_postgres_database, outcome=outcome) as (
        _, factory, command, actor, grant,
    ):
        package = await read_package(factory, command, actor, grant)
        original_digest = package.target.digest
        assert len(package.result.requirements) == 2
        assert package.target.result_schema_version == "project_guide_check_specification.v1"
        with pytest.raises(ValidationError):
            GuideProposalApproval(target=package.target, idempotency_key=uuid4())
        empty = GuideProposalApproval(
            target=package.target, pre_submit_attachments=(), post_submit_attachments=(),
            idempotency_key=uuid4(),
        )
        assert empty.pre_submit_attachments == ()
        entry = await _register_external_checker_fixture(factory, registry_spec("pre_submit"))
        after_publication = await read_package(factory, command, actor, grant)
        assert after_publication.target.digest == original_digest
        attachment = ExternalCheckerImageAttachment(
            requirement_id="human_project_pre_image",
            registry_entry_id=entry.registry_entry_id,
            registry_entry_digest=entry.entry_digest,
            configuration={},
        )
        command_key = uuid4()
        approval = GuideProposalApproval(
            target=after_publication.target,
            pre_submit_attachments=(attachment,), post_submit_attachments=(),
            idempotency_key=command_key,
        )
        receipt = await approve(factory, command, actor, grant, approval)
        assert await approve(factory, command, actor, grant, approval) == receipt
        async with factory() as session:
            operation = await session.get(ProjectGuideProposalApproval, receipt.operation_id)
            assert operation.request_json == approval.model_dump(mode="json")
            assert operation.request_digest == canonical_json_hash(operation.request_json)
            assert [item["requirement_id"] for item in operation.effective_pre_submit_plan["pre_submit"]["entries"]] == [
                "human_project_pre_image"
            ]
        with pytest.raises(GuideProposalError, match="operation_conflict"):
            await approve(
                factory, command, actor, grant,
                approval.model_copy(update={"pre_submit_attachments": (
                    attachment.model_copy(update={"requirement_id": "another_human_image"}),
                )}),
            )


async def test_unified_approval_postgresql_commits_exact_chain_and_provenance(
    clean_postgres_database,
):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        before = await stored_state(factory, command)
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(), target=package.target, idempotency_key=uuid4())
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
                GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
                    target=package.target,
                    idempotency_key=uuid4(),
                ),
            )


async def test_correction_uses_canonical_human_request_and_binds_feedback(clean_postgres_database):
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
            predecessor = await session.get(ProjectGuideCompilation, command.compilation_id)
            prompt = json.loads(project_guide_compilation_prompt_bytes(context))
            assert prompt["correction_predecessor"] == predecessor.canonical_result
            assert canonical_json_hash(prompt["correction_predecessor"]) == package.target.result_hash
            original_identity = (attempt.canonical_input_hash, attempt.provider_idempotency_key)
        class RecordingFailure(_Runtime):
            async def compile_project_guide(self, execution_context, capabilities):
                assert execution_context == context
                assert execution_context.correction_predecessor.model_dump(mode="json") == predecessor.canonical_result
                return await super().compile_project_guide(execution_context, capabilities)

        runtime = RecordingFailure(ProjectAgentRuntimeError("transport failed"))
        backend = _backend(factory)
        execution = ProjectGuideCompilationExecutionCommand(attempt_id=receipts[0].attempt_id)
        first = await GuideCompilationOrchestrator(backend, lambda _: runtime).execute(execution)
        assert first.classification is ProjectGuideCompilationExecutionClassification.PROVIDER_UNRESOLVED

        class RecoveryOnly:
            async def load(self, attempt_id):
                return await backend.load(attempt_id)

            def __getattr__(self, name):
                pytest.fail("uncertain correction reached " + name)

        def forbidden_runtime(_):
            pytest.fail("uncertain correction created a second runtime")

        assert await GuideCompilationOrchestrator(RecoveryOnly(), forbidden_runtime).execute(execution) == first
        assert runtime.calls == 1
        async with factory() as session:
            retained = await session.get(ProjectGuideCompilation, command.compilation_id)
            attempt = await session.get(ProjectGuideCompilationAttempt, receipts[0].attempt_id)
            assert retained.canonical_result == predecessor.canonical_result
            assert retained.result_hash == package.target.result_hash
            assert (attempt.canonical_input_hash, attempt.provider_idempotency_key) == original_identity


async def test_correction_rejects_authority_for_a_substituted_locator_operation(
    clean_postgres_database,
):
    from sqlalchemy.exc import DBAPIError

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalCorrection(
            target=package.target,
            idempotency_key=uuid4(),
            reason="Reconsider the existing source evidence.",
        )
        with pytest.raises(DBAPIError, match="guide proposal authority evidence mismatch"):
            await correct(
                factory,
                command,
                actor,
                grant,
                payload,
                authority_resource=new_record_id(),
            )

        receipt = await correct(factory, command, actor, grant, payload)
        assert receipt.target_digest == package.target.digest


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
                    GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
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
            GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
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
                    GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
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
            GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
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
                GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
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
        for action in ("approve", "correct"):
            with pytest.raises(GuideProposalError, match="authority_unavailable"):
                async with factory() as session, session.begin():
                    from app.adapters.checkers import (
                        external_checker_registry_reader,
                    )

                    service = GuideProposalService(
                        session,
                        ProposalAuthority(
                            session,
                            actor,
                            command.project_id,
                            grant,
                            close_error=True,
                        ),
                        external_checker_registry_reader(session),
                    )
                    if action == "approve":
                        await service.approve(
                            GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
                                target=package.target,
                                idempotency_key=uuid4(),
                            ),
                            actor=actor,
                            request_id=uuid4(),
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
            GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
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
            GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
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
                from app.adapters.checkers import (
                    external_checker_registry_reader,
                )

                await GuideProposalService(
                    session,
                    ProposalAuthority(
                        session,
                        actor,
                        command.project_id,
                        grant,
                    ),
                    external_checker_registry_reader(session),
                ).approve(
                    GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
                        target=package.target,
                        idempotency_key=uuid4(),
                    ),
                    actor=actor,
                    request_id=uuid4(),
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
        first_payload = GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(), target=first_package.target, idempotency_key=uuid4())
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
                GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
                    target=next_package.target,
                    idempotency_key=uuid4(),
                ),
            )
        second = await approve(
            factory,
            next_command,
            actor,
            grant,
            GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
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
            GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(), target=package.target, idempotency_key=uuid4()) for _ in range(2)
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
        payload = GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(), target=package.target, idempotency_key=uuid4())
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
                GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(),
                    target=package.target,
                    idempotency_key=uuid4(),
                ),
            )
        ).artifact_policy_id == package.target.artifact_policy_id


@pytest.mark.parametrize("guide_version", ["v0.1", "example-proof"])
async def test_approval_preserves_opaque_guide_version(clean_postgres_database, guide_version):
    async with proposal_case(clean_postgres_database, guide_version=guide_version) as (
        values,
        factory,
        command,
        actor,
        grant,
    ):
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(), target=package.target, idempotency_key=uuid4())
        receipt = await approve(factory, command, actor, grant, payload)
        assert await approve(factory, command, actor, grant, payload) == receipt
        async with factory() as session:
            operation = await session.get(ProjectGuideProposalApproval, receipt.operation_id)
            assert operation.effective_pre_submit_plan["schema_version"] == (
                "external_checker_policies.v1"
            )
            assert operation.target_json["guide_version"] == guide_version
        await finalize(factory, values, command)


@pytest.mark.parametrize(
    "authority_change",
    [
        "revoked_grant",
        "suspended_actor",
        "revoked_link",
        "audit",
        "operator",
        "system_manager",
        "foreign_project",
    ],
)
async def test_stored_authority_variants_deny_review_replay_and_correction(
    clean_postgres_database, authority_change
):
    from sqlalchemy import text
    from .pg_support import seed_review_actor, revoke_review_grant
    from project_create_fixtures import seed_historical_project

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        payload = GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(), target=package.target, idempotency_key=uuid4())
        receipt = await approve(factory, command, actor, grant, payload)
        assert await approve(factory, command, actor, grant, payload) == receipt
        denied_grant = grant
        if authority_change == "revoked_grant":
            await revoke_review_grant(factory, actor, grant)
        elif authority_change in {"suspended_actor", "revoked_link"}:
            async with factory() as session, session.begin():
                if authority_change == "suspended_actor":
                    await session.execute(
                        text(
                            "UPDATE actor_profiles SET status='suspended',suspended_by=:id,suspended_at=now(),suspension_reason='Test turnover' WHERE id=:id"
                        ),
                        {"id": str(actor.actor_profile_id)},
                    )
                else:
                    await session.execute(
                        text(
                            "UPDATE actor_identity_links SET status='revoked',revoked_by=:actor,revoked_at=now(),revoked_reason='Test turnover' WHERE id=:id"
                        ),
                        {"actor": str(actor.actor_profile_id), "id": str(actor.identity_link_id)},
                    )
        else:
            project = command.project_id
            role, scope = {
                "audit": ("audit_authority", "project"),
                "operator": ("operator", "system"),
                "system_manager": ("project_manager", "system"),
                "foreign_project": ("project_manager", "project"),
            }[authority_change]
            if authority_change == "foreign_project":
                project = new_record_id()
                async with factory() as session, session.begin():
                    await seed_historical_project(
                        session,
                        project_id=str(project),
                        name="Foreign guide owner",
                        slug=f"foreign-{project}",
                    )
            _, denied_grant = await seed_review_actor(
                factory, project, actor=actor, role=role, scope=scope
            )
        before = await stored_state(factory, command)
        async with factory() as session:
            audit_before = (
                await session.execute(text("SELECT id FROM audit_events ORDER BY id"))
            ).all()
        for operation in (
            read_package(factory, command, actor, denied_grant),
            approve(factory, command, actor, denied_grant, payload),
            correct(
                factory,
                command,
                actor,
                denied_grant,
                GuideProposalCorrection(
                    target=package.target,
                    idempotency_key=uuid4(),
                    reason="Reconsider this proposal.",
                ),
            ),
        ):
            with pytest.raises(GuideProposalError, match="authority_unavailable"):
                await operation
        assert await stored_state(factory, command) == before
        async with factory() as session:
            assert (
                await session.execute(text("SELECT id FROM audit_events ORDER BY id"))
            ).all() == audit_before
            assert (
                await session.execute(
                    text("SELECT count(*) FROM project_guide_proposal_corrections")
                )
            ).scalar_one() == 0


async def test_another_current_manager_can_admit_correction_after_creator_revocation(
    clean_postgres_database,
):
    from .pg_support import seed_review_actor, revoke_review_grant, request_corrected_attempt
    from app.modules.projects.guide_compilation.models import (
        ProjectGuideCompilationRequestOperation,
    )

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        before = await stored_state(factory, command)
        successor = await correct(
            factory,
            command,
            actor,
            grant,
            GuideProposalCorrection(
                target=package.target,
                idempotency_key=uuid4(),
                reason="Recheck the guide requirement.",
            ),
        )
        second_actor, _ = await seed_review_actor(factory, command.project_id)
        await revoke_review_grant(factory, actor, grant)
        requested = await request_corrected_attempt(factory, second_actor, successor)
        assert await request_corrected_attempt(factory, second_actor, successor) == requested
        async with factory() as session:
            correction = await session.get(ProjectGuideProposalCorrection, successor.operation_id)
            setup = await session.get(ProjectSetupRun, str(successor.successor_setup_run_id))
            operation = (
                await session.scalars(
                    select(ProjectGuideCompilationRequestOperation).where(
                        ProjectGuideCompilationRequestOperation.attempt_id == requested.attempt_id
                    )
                )
            ).one()
            assert correction.actor_profile_id == str(actor.actor_profile_id)
            assert setup.authorized_by_actor_profile_id == str(actor.actor_profile_id)
            assert operation.actor_profile_id == str(second_actor.actor_profile_id)
            assert setup.status == "dispatch_pending"
            assert setup.current_step == "dispatch"
            assert setup.celery_task_id is not None
        assert await stored_state(factory, command) == before


async def assert_approval_replay_unchanged(factory, command, actor, grant, payload, receipt):
    from sqlalchemy import text

    async def counts():
        async with factory() as session:
            return (
                await session.execute(
                    text(
                        "SELECT (SELECT count(*) FROM project_guide_proposal_approvals),"
                        "(SELECT count(*) FROM submission_policy_mutation_idempotency_records),"
                        "(SELECT count(*) FROM effective_project_submission_artifact_policies),"
                        "(SELECT count(*) FROM pre_submit_checker_policies),"
                        "(SELECT count(*) FROM audit_events)"
                    )
                )
            ).one()

    before = await counts()
    assert await approve(factory, command, actor, grant, payload) == receipt
    assert await counts() == before


@pytest.mark.parametrize("activate_before_commit", [False, True])
async def test_database_approval_requires_guide_to_remain_draft(
    clean_postgres_database, activate_before_commit
):
    from contextlib import nullcontext
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from .pg_support import seed_selected_review_revision_inputs

    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        await seed_selected_review_revision_inputs(factory, command, actor)
        package = await read_package(factory, command, actor, grant)
        before = await stored_state(factory, command)
        expected = (
            pytest.raises(DBAPIError, match="proposal approval target is no longer current")
            if activate_before_commit
            else nullcontext()
        )
        with expected:
            async with factory() as session, session.begin():
                from app.adapters.checkers import (
                    external_checker_registry_reader,
                )

                if activate_before_commit:
                    # Transaction rollback restores these unrelated activation prerequisites.
                    for trigger in (
                        "guide_mutation_product_custody",
                        "guide_lineage_lifecycle_guard",
                    ):
                        await session.execute(
                            text(f"ALTER TABLE project_guides DISABLE TRIGGER {trigger}")
                        )
                await GuideProposalService(
                    session,
                    ProposalAuthority(session, actor, command.project_id, grant),
                    external_checker_registry_reader(session),
                ).approve(
                    GuideProposalApproval(pre_submit_attachments=(), post_submit_attachments=(), target=package.target, idempotency_key=uuid4()),
                    actor=actor,
                    request_id=uuid4(),
                )
                if activate_before_commit:
                    # Stage lifecycle drift after valid approval assembly to reach the DB guard itself.
                    await session.execute(
                        text(
                            "UPDATE project_guides SET status='active',approved_by=:actor,effective_at=now() WHERE id=:guide"
                        ),
                        {"actor": str(actor.actor_profile_id), "guide": str(command.guide_id)},
                    )
                await session.execute(
                    text("SET CONSTRAINTS guide_proposal_approval_custody IMMEDIATE")
                )
        if activate_before_commit:
            assert await stored_state(factory, command) == before
            async with factory() as session:
                assert (
                    await session.scalar(
                        text(
                            "SELECT count(*) FROM pg_trigger WHERE tgrelid='project_guides'::regclass AND tgenabled='D'"
                        )
                    )
                    == 0
                )
                for table in (
                    "project_guide_proposal_approvals",
                    "submission_policy_mutation_idempotency_records",
                    "effective_project_submission_artifact_policies",
                    "pre_submit_checker_policies",
                ):
                    assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
                assert (
                    await session.scalar(
                        text(
                            "SELECT count(*) FROM audit_events WHERE action_id='project.submission_artifact_policy.approve'"
                        )
                    )
                    == 0
                )
