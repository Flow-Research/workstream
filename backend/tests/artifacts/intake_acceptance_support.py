"""Real T1/upload/PRE owners with the portable worker/runtime fixture for T4."""
from app.adapters.artifacts import submission_intake_pre_source_port
from app.adapters.auth import selected_pre_submit_authority
from app.adapters.checkers import selected_pre_submit_coordinator, SelectedPreSubmitCheckerExecutionAdapter
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
from app.modules.artifacts.authorization import PreparedPreSubmitMaterializationAuthorization
from app.modules.artifacts.selected_pre_submit_admission import (
    bind_selected_pre_submit_admission, build_selected_pre_submit_reservation,
)
from app.modules.artifacts.selected_pre_submit_execution import SelectedPreSubmitSourceReads, SelectedPreSubmitExecutionService
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from tests.artifact_store_helpers import initialize_local_store
from tests.artifacts.test_submission_intake_custody import foreground_upload, foreground_limits
from tests.artifacts.test_submission_pre_source import _source_runtime
from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer
from tests.checkers.execution.support import provision_post_submit_service
from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation
from tests.test_trusted_intake import _archive


async def completed_source(f, tmp_path):
    """Return a real committed eligible PRE plus its exact original foreground owner."""
    metadata = SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment)
    key = new_record_id()
    owner = await f.admission.admit(metadata, actor_id=f.actor.actor_profile_id,
        identity_link_id=f.actor.identity_link_id, idempotency_key=key, declared_raw_bytes=None)
    payload = _archive()
    async def body():
        yield payload
    store = (f.source_store_factory() if getattr(f, "source_store_factory", None) else
             initialize_local_store(root=tmp_path / "durable", buffer_bytes=256 * 1024))
    try:
        source = await foreground_upload(f, store).receive(
            owner.operation_id, owner.lease_id, owner.generation, body(), **foreground_limits())
        async with f.factory.begin() as session:
            task, project = await f.admission._validate_context(session, metadata, f.actor.actor_profile_id)
            custody = await submission_intake_pre_source_port(session).lock_pre_source(
                source=source, lease_id=owner.lease_id, generation=owner.generation)
            selected = bind_selected_pre_submit_admission(
                task=task, project=project, predecessor=None, predecessor_rules_sha256=None,
                predecessor_exists=False, packet=SubmissionPacketView(metadata.summary, metadata.contributor_attestation))
            request = build_selected_pre_submit_reservation(
                source=custody, metadata=metadata, task=task, project=project, attempt_id=new_record_id(),
                idempotency_key=key, selected=selected, runtime_profile=_source_reservation().runtime_profile)
            await selected_pre_submit_coordinator(session).reserve(request)
        await provision_post_submit_service(f.factory, ServiceIdentity.CHECKER_PRE_SUBMIT)
        await _seed_materializer(f.factory)
        runtime, errors = _source_runtime(payload, tmp_path, "completed")
        async with f.factory() as session:
            authority = PreparedPreSubmitMaterializationAuthorization(
                session, request_id=new_record_id(), correlation_id=new_record_id())
            service = SelectedPreSubmitExecutionService(
                session=session, coordinator=selected_pre_submit_coordinator(session),
                authority=selected_pre_submit_authority(session),
                source_reads=SelectedPreSubmitSourceReads(session=session,
                    sources=submission_intake_pre_source_port(session), authority=authority, store=store),
                execution=SelectedPreSubmitCheckerExecutionAdapter(external_execution=runtime))
            result = await service.execute(reservation=request)
        assert not errors, "\n".join(errors)
        assert result.terminal.execution is not None and result.terminal.execution.eligible
        return owner, request, result.terminal
    finally:
        store.close()


async def wait_foreground_expired(session, operation_id):
    """Observe the database deadline, rather than infer expiry from a host sleep."""
    import asyncio
    from sqlalchemy import text
    async with asyncio.timeout(10):
        while True:
            remaining = float(await session.scalar(text("SELECT extract(epoch FROM "
                "(lease_expires_at-clock_timestamp())) FROM submission_intake_operations WHERE id=:id"),
                {"id": operation_id}))
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining + 0.02, 0.25))
