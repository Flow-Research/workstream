"""Trusted intake cleanup gates ordered PRE execution and deadline finalization."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from tests.trusted_intake_fixtures import assert_sealed_export

from app.adapters.checkers import SelectedPreSubmitCheckerExecutionAdapter
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationService, _PreSubmitExternalGrantIssuer, _SelectedGrantClaim,
)
from app.modules.checkers.api.external_policy import LockedExternalPreSubmitPolicy
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitInfrastructureUnavailable, SelectedPreSubmitLeaseFacts,
)
from tests.checkers.external.test_selected_pre_submit import (
    _request, _policy, _execution_context, _processor, _Execution, _GrantIssuer,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_confirmed", [True, False])
async def test_intake_cleanup_precedes_both_project_bindings(tmp_path, cleanup_confirmed):
    from app.interfaces.external_services import ExternalServiceUnavailableError

    request, _, manager, preparation = await _request(tmp_path)
    first = _policy()
    bindings = (first.entries[0], first.entries[0].model_copy(update={"requirement_id": "project.second_rule"}))
    body = {"schema_version": "external_pre_submit_policy.v1",
            "workstream_default": first.workstream_default.model_dump(mode="json"),
            "entries": [binding.model_dump(mode="json") for binding in bindings]}
    policy = LockedExternalPreSubmitPolicy(workstream_default=first.workstream_default,
                                          entries=bindings, policy_sha256=canonical_json_hash(body))
    identity, material, default_input = _execution_context(request, policy)
    binding = {"attempt_id": request.selected_reservation.attempt_id,
               "attempt_request_digest": request.selected_reservation.request_digest}
    identity, material = identity.model_copy(update=binding), material.model_copy(update=binding)
    events = []
    close = request.intake.close

    async def confirm_cleanup():
        assert request.intake.events[-1] == "default"
        events.append("cleanup")
        if not cleanup_confirmed:
            raise ExternalServiceUnavailableError()
        await close()

    request.intake.close = confirm_cleanup

    class OrderedExecution(_Execution):
        async def execute(self, command, grant):
            assert request.intake.closed
            assert events[0] == "cleanup"
            events.append(command.input["requirement_id"])
            return await super().execute(command, grant)

    issuer = _PreSubmitExternalGrantIssuer(
        preparation=preparation, prepared=request.prepared_artifact, request=request,
        claim=_SelectedGrantClaim(request.selected_reservation.attempt_id,
                                  request.selected_reservation.request_digest),
    )

    class RealGrants(_GrantIssuer):
        @contextmanager
        def issue(self, command, workspace):
            self.requests.append(command)
            with issuer.issue(command, workspace) as grant:
                yield grant
            assert_sealed_export(workspace)

    grants, execution = RealGrants(), OrderedExecution("passed")
    processor = _processor(request=request, policy=policy, default_input=default_input,
                           identity=identity, material=material, grants=grants, execution=execution)
    try:
        operation = preparation._process_prepared_submission(
            request.prepared_artifact, processor, reserved_bytes=request.manifest.total_expanded_bytes,
            maximum_entries=request.manifest.entry_count)
        if cleanup_confirmed:
            result = await operation
            assert result.eligible
            assert [member.requirement_id for member in result.external_members] == [binding.requirement_id for binding in bindings]
            assert events == ["cleanup", "project.archive_rules", "project.second_rule"]
        else:
            with pytest.raises(SelectedPreSubmitInfrastructureUnavailable):
                await operation
            assert events == ["cleanup"]
            assert grants.requests == execution.requests == []
        assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    finally:
        await request.prepared_artifact.close()
        await close()
        manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("intake_cleanup_confirmed", [False, True])
async def test_preparation_deadline_finalizes_only_after_intake_cleanup(tmp_path, intake_cleanup_confirmed):
    import asyncio
    from app.modules.artifacts.preparation import ArtifactPreparationDeadlineError
    from app.modules.artifacts.selected_pre_submit_execution import SelectedPreSubmitExecutionService
    from tests.checkers.external.test_selected_pre_submit_service import _Session, _Authority, _Coordinator

    request, _, manager, preparation = await _request(tmp_path)
    reservation = request.selected_reservation
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation, lease_id=new_record_id(), lease_generation=1,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    entered, drained = asyncio.Event(), asyncio.Event()

    async def blocked(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            drained.set()

    execution = _Execution("passed")
    if intake_cleanup_confirmed:
        execution.execute = blocked
    else:
        request.intake.evaluate_default = blocked
    order = []
    session = _Session(order)

    class Coordinator(_Coordinator):
        async def committed_execution(self, **values):
            await super().committed_execution(**values)
            return SimpleNamespace(consume=lambda **kwargs: lease)

    materialization = PreparedBundleMaterializationService(
        session=session, authorization=SimpleNamespace(), preparation=preparation,
        checker_execution=SelectedPreSubmitCheckerExecutionAdapter(external_execution=execution),
        storage_scheme="s3", archive_limits=SubmissionArchiveLimits(),
    )
    service = SelectedPreSubmitExecutionService(
        session=session, coordinator=Coordinator(session, order, lease),
        authority=_Authority(session, order), materialization=materialization,
    )
    # Exercise ART's actual absolute-deadline cancellation and scratch drain.
    preparation._active[request.prepared_artifact._binding].deadline = asyncio.get_running_loop().time() + 2
    session.in_transaction = lambda: session.active
    try:
        operation = service.execute(reservation=reservation, materialization=request)
        if intake_cleanup_confirmed:
            completion = await operation
            assert completion.terminal.infrastructure_failure_code == "deadline_exceeded"
            assert completion.terminal.execution is None
            assert order.count("finalize") == 1
            assert request.intake.closed
        else:
            with pytest.raises(ArtifactPreparationDeadlineError):
                await operation
            assert "finalize" not in order
        assert entered.is_set() and drained.is_set()
        assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    finally:
        await request.intake.close()
        await request.prepared_artifact.close()
        manager.close()
