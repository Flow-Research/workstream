"""Integrated ART replay proof for original-generation fixed-service authority."""

from dataclasses import replace
from pathlib import Path

import pytest

from app.adapters.artifacts import CheckerPhaseService
from tests.checkers.execution.support import forbidden_post_submission
from sqlalchemy import select

from app.modules.artifacts.authorization import PreparedPreSubmitMaterializationAuthorization
from app.modules.artifacts.pre_submit_evidence import PreSubmitEvidencePersistenceResult
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.authorization.catalogue import ActionId
from app.modules.tasks.models import AuditEvent
from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer
from tests.test_pre_submit_attempt_recovery import _harness


async def _reserve_with_real_materializer(workflow, request, preparation_request):
    """Issue the exact transaction-bound handle consumed by ART reservation."""
    materialization = workflow._materialization
    async with workflow._session.begin():
        await workflow._lock_authorized_context(request, preparation_request)
        handle = await materialization.prepare_authorization(
            task_id=request.task_id, assignment_id=request.assignment_id,
            submission_artifact_policy_id=request.submission_artifact_policy_id,
            checker_policy_id=request.checker_policy_id,
            prepared_artifact=request.prepared_artifact,
            effective_plan=request.effective_plan,
            idempotency_key=preparation_request.idempotency_key,
        )
        return await workflow.reserve(
            replace(request, prepared_authorization=handle),
            preparation_request=preparation_request,
        )


async def _materializer_audits(factory):
    async with factory() as session:
        return (await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id
            == ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE.value,
        ).order_by(AuditEvent.created_at, AuditEvent.id))).all()


@pytest.mark.asyncio
async def test_completed_replay_authorizes_retry_custody_and_stored_original_generation(
    tmp_path: Path, isolated_database_env: str,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    calls: list[int] = []
    retry = None
    try:
        await _seed_materializer(harness.factory)
        async with harness.factory() as session:
            contributor = harness.contributor_authority(session)
            await contributor.preflight(request=harness.preparation_request)
            async with session.begin():
                await contributor.revalidate(
                    request=harness.preparation_request,
                    project_id=harness.request.effective_plan.lineage.project_id,
                )
            authority = PreparedPreSubmitMaterializationAuthorization(
                session, request_id=harness.preparation_request.request_id,
                correlation_id=harness.preparation_request.correlation_id,
            )
            workflow = harness.workflow(
                session, calls, preparation_authorization=contributor,
            )
            workflow._materialization._authorization = authority
            phases = CheckerPhaseService(
                pre_submission=workflow, post_submission=forbidden_post_submission(),
            )
            try:
                reservation = await _reserve_with_real_materializer(
                    workflow, harness.request, harness.preparation_request,
                )
                original = await phases.evaluate_pre_submission(
                    replace(harness.request, prepared_authorization=None), reservation,
                    preparation_request=harness.preparation_request,
                )
                assert original.pass_capability is not None
                assert len(calls) == 1
                original_generation = original.execution.custody.prepared_generation_id
                initial_audits = await _materializer_audits(harness.factory)
                assert [event.resource_id for event in initial_audits] == [
                    str(original_generation), str(original_generation),
                ]

                await harness.request.prepared_artifact.close()
                retry = await harness.fresh_request()
                retry_generation = retry.prepared_artifact.generation_id
                assert retry_generation != original_generation

                # A failed original-generation AUTH consume must abort recovery.
                # The inspected retry consume has already passed in that root
                # transaction, but both its audit and the replay read roll back.
                real_consume = authority.consume

                async def deny_original(*, prepared_authorization, facts):
                    if facts.prepared_generation_id == original_generation:
                        facts = replace(facts, archive_sha256="sha256:" + "f" * 64)
                    await real_consume(
                        prepared_authorization=prepared_authorization, facts=facts,
                    )

                authority.consume = deny_original
                try:
                    with pytest.raises(ArtifactAuthorityDeniedError):
                        await _reserve_with_real_materializer(
                            workflow, retry, harness.preparation_request,
                        )
                finally:
                    authority.consume = real_consume
                assert len(calls) == 1
                assert len(await _materializer_audits(harness.factory)) == 2

                # The injected invalid consume intentionally leaves its exact
                # handle unconsumed. A subsequent request gets a new adapter.
                authority.close()
                authority = PreparedPreSubmitMaterializationAuthorization(
                    session, request_id=harness.preparation_request.request_id,
                    correlation_id=harness.preparation_request.correlation_id,
                )
                workflow._materialization._authorization = authority
                replay = await _reserve_with_real_materializer(
                    workflow, retry, harness.preparation_request,
                )
                selected = replay
                replay = await phases.evaluate_pre_submission(
                    replace(retry, prepared_authorization=None), selected,
                    preparation_request=harness.preparation_request,
                )
                assert replay is selected
                assert isinstance(replay, PreSubmitEvidencePersistenceResult)
                assert replay.evidence.evidence_set_id == original.evidence.evidence_set_id
                assert replay.execution.custody.prepared_generation_id == original_generation
                assert replay.pass_capability is None
                assert len(calls) == 1
                audits = await _materializer_audits(harness.factory)
                assert len(audits) == 4
                assert sorted(event.resource_id for event in audits) == sorted([
                    str(original_generation), str(original_generation),
                    str(original_generation), str(retry_generation),
                ])
                assert all(event.event_type == "SensitiveAuthorizationAllowed" for event in audits)
            finally:
                authority.close()
    finally:
        if retry is not None:
            await retry.prepared_artifact.close()
        await harness.close()
