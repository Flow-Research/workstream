"""The hidden contributor command selects the durable PRE owner exclusively."""

from tests.trusted_intake_fixtures import LocalIntakeAdapter
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.artifacts.submission_admission as owner
from app.core.identifiers import new_record_id
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationStatus,
)
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand,
    SubmissionBundleDurablePutResult,
    SubmissionBundlePreparationRuntime,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitCompletion
from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
from tests.test_submission_bundle_preparation_recovery import _feedback_facts


@asynccontextmanager
async def _root():
    yield


def _request_case():
    actor = ActorIdentityFacts(
        actor_profile_id=new_record_id(),
        identity_link_id=new_record_id(),
        actor_kind=ActorKind.HUMAN,
    )
    task_id, assignment_id, attempt_id = (new_record_id() for _ in range(3))
    request = SubmissionBundlePreparationRequest(
        actor=actor,
        request_id=new_record_id(),
        correlation_id=new_record_id(),
        task_id=task_id,
        assignment_id=assignment_id,
        predecessor_submission_id=None,
        idempotency_key=new_record_id(),
        summary="",
        contributor_attestation="",
        media_type="application/zip",
        byte_source=SimpleNamespace(),
    )
    prepared = SimpleNamespace(
        generation_id=new_record_id(),
        commitment=SimpleNamespace(sha256="sha256:" + "1" * 64, byte_count=100),
        inspect=AsyncMock(return_value=object()),
        close=AsyncMock(),
    )
    return actor, request, prepared, attempt_id


def _runtime_case(prepared, attempt_id):
    policy = SimpleNamespace(policy_sha256="sha256:" + "a" * 64)
    selected = SimpleNamespace(policy=policy, default_input=object(), change_gate=object())
    reservation = SimpleNamespace(attempt_id=attempt_id)
    completion = SelectedPreSubmitCompletion(
        terminal=SimpleNamespace(
            outcome="completed",
            execution=_feedback_facts(eligible=True),
            infrastructure_failure_code=None,
        ),
        capability=object(),
    )
    materialization = SimpleNamespace(
        prepare_selected_authorization=AsyncMock(return_value=object()),
        authorize_inspected=AsyncMock(),
    )
    coordinator = SimpleNamespace(
        read_current=AsyncMock(return_value=None),
        reserve=AsyncMock(return_value=attempt_id),
    )
    selected_execution = SimpleNamespace(execute=AsyncMock(return_value=completion))
    durable = SimpleNamespace(
        admit_in_transaction=AsyncMock(return_value=(prepared, attempt_id, SimpleNamespace())),
        publish_after_commit=AsyncMock(
            return_value=SubmissionBundleDurablePutResult(
                put_attempt_id=new_record_id(),
                operation_identity="sha256:" + "2" * 64,
                status="prepared",
                replayed=False,
                admission_id=None,
                selected_pre_submit_run_id=attempt_id,
            )
        ),
    )
    runtime = SubmissionBundlePreparationRuntime(
        preparation=SimpleNamespace(prepare=AsyncMock(return_value=prepared)),
        intake=LocalIntakeAdapter(), archive_limits=SubmissionArchiveLimits(),
        materialization=materialization,
        durable_put=durable,
        selected_coordinator=coordinator,
        selected_execution=selected_execution,
        storage_scheme="s3",
        artifact_deadline_ms=120_000,
    )
    return SimpleNamespace(
        runtime=runtime,
        policy=policy,
        selected=selected,
        reservation=reservation,
        completion=completion,
        materialization=materialization,
        coordinator=coordinator,
        selected_execution=selected_execution,
        durable=durable,
    )


def _command(runtime, actor):
    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    authority = SimpleNamespace(preflight=AsyncMock(), transaction=_root, close=Mock())
    command = PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(begin=_root),
        authority=authority,
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
        runtime_factory=runtime_factory,
    )
    project = SimpleNamespace(
        effective_policy_id=new_record_id(),
        pre_submit_policy_id=new_record_id(),
        external_checker_policies=SimpleNamespace(value="{}"),
    )
    command._lock_authorized_context = AsyncMock(
        return_value=(SimpleNamespace(predecessor=None, checker_remediation_manifest_id=None, revision_context=None), project)
    )
    command._load_predecessor = AsyncMock(return_value=None)
    command._load_predecessor_rules = AsyncMock(return_value=None)
    return command


def _patch_selected_owners(monkeypatch, case):
    monkeypatch.setattr(
        owner,
        "LockedExternalCheckerPolicies",
        SimpleNamespace(
            model_validate_json=Mock(return_value=SimpleNamespace(pre_submit=case.policy))
        ),
    )
    monkeypatch.setattr(owner, "build_submission_manifest", Mock(return_value=object()))
    monkeypatch.setattr(
        owner, "bind_selected_pre_submit_admission", Mock(return_value=case.selected)
    )
    monkeypatch.setattr(
        owner,
        "build_selected_pre_submit_reservation",
        Mock(return_value=case.reservation),
    )
    monkeypatch.setattr(
        owner,
        "selected_pre_submit_attempt_request_digest",
        Mock(return_value="sha256:" + "3" * 64),
    )
    monkeypatch.setattr(owner, "selected_pre_submit_execution_budget_ms", Mock(return_value=60_000))


@pytest.mark.asyncio
async def test_hidden_preparation_uses_selected_pre_before_durable_admission(
    monkeypatch,
) -> None:
    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    command = _command(case.runtime, actor)
    _patch_selected_owners(monkeypatch, case)

    result = await command.prepare(request)

    assert result.submission_bundle_preparation_status is (
        SubmissionBundlePreparationStatus.PREPARED
    )
    # The admitted attempt returns its intake feedback from the executed facts.
    assert result.pre_submission_results == tuple(
        public_pre_submission_results(case.completion.terminal.execution)
    )
    case.materialization.prepare_selected_authorization.assert_awaited_once()
    case.materialization.authorize_inspected.assert_awaited_once()
    case.coordinator.read_current.assert_awaited_once_with(case.reservation)
    case.coordinator.reserve.assert_awaited_once_with(case.reservation)
    case.selected_execution.execute.assert_awaited_once()
    admitted = case.durable.admit_in_transaction.await_args.args[0]
    assert admitted.selected_completion is case.completion
    case.durable.publish_after_commit.assert_awaited_once_with(
        prepared,
        attempt_id,
        case.durable.admit_in_transaction.return_value[2],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("upload_failure", [False, True])
async def test_intake_prepares_during_upload_before_any_reservation(monkeypatch, upload_failure):
    import asyncio
    from dataclasses import replace
    from tests.trusted_intake_fixtures import LocalIntakeSession

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    upload_entered = asyncio.Event()
    vm_ready = asyncio.Event()
    events = []
    session = LocalIntakeSession()

    async def prepare_vm(value):
        await upload_entered.wait()
        assert value.phase == "pre_submit"
        events.append("vm_ready")
        vm_ready.set()
        return session

    async def upload(*args, **kwargs):
        events.append("upload_started")
        upload_entered.set()
        await asyncio.wait_for(vm_ready.wait(), 2)
        case.coordinator.reserve.assert_not_awaited()
        case.selected_execution.execute.assert_not_awaited()
        events.append("upload_finished")
        if upload_failure:
            raise OSError("upload interrupted")
        return prepared

    runtime = replace(case.runtime, intake=SimpleNamespace(prepare=prepare_vm),
                      preparation=SimpleNamespace(prepare=upload))
    command = _command(runtime, actor)
    _patch_selected_owners(monkeypatch, case)
    if upload_failure:
        with pytest.raises(OSError, match="upload interrupted"):
            await command.prepare(request)
        case.coordinator.reserve.assert_not_awaited()
        case.durable.admit_in_transaction.assert_not_awaited()
    else:
        await command.prepare(request)
        case.coordinator.reserve.assert_awaited_once()
    assert events == ["upload_started", "vm_ready", "upload_finished"]
    assert session.closed


@pytest.mark.asyncio
async def test_unauthorized_upload_does_not_prepare_vm_or_consume_bytes(monkeypatch):
    from dataclasses import replace
    from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
    from app.modules.artifacts.api import SubmissionBundlePreparationUnavailable

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    intake = SimpleNamespace(prepare=AsyncMock())
    runtime = replace(case.runtime, intake=intake)
    command = _command(runtime, actor)
    command._lock_authorized_context = AsyncMock(side_effect=ArtifactAuthorityDeniedError("denied"))
    _patch_selected_owners(monkeypatch, case)
    with pytest.raises(SubmissionBundlePreparationUnavailable):
        await command.prepare(request)
    intake.prepare.assert_not_awaited()
    runtime.preparation.prepare.assert_not_awaited()
    case.coordinator.reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_intake_failure_interrupts_blocked_upload_without_reservation(monkeypatch):
    import asyncio
    from dataclasses import replace
    from app.interfaces.external_services import ExternalServiceUnavailableError
    from app.modules.artifacts.api import SubmissionBundlePreparationInfrastructureUnavailable

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    upload_entered = asyncio.Event()
    upload_drained = asyncio.Event()

    async def unavailable(value):
        await upload_entered.wait()
        raise ExternalServiceUnavailableError()

    async def upload(*args, **kwargs):
        upload_entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            upload_drained.set()

    runtime = replace(case.runtime, intake=SimpleNamespace(prepare=unavailable),
                      preparation=SimpleNamespace(prepare=upload))
    command = _command(runtime, actor)
    _patch_selected_owners(monkeypatch, case)
    with pytest.raises(SubmissionBundlePreparationInfrastructureUnavailable):
        await asyncio.wait_for(command.prepare(request), 2)
    assert upload_drained.is_set()
    case.coordinator.reserve.assert_not_awaited()
    case.durable.admit_in_transaction.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("session_ready_first", [False, True])
async def test_caller_cancellation_drains_upload_and_intake(monkeypatch, session_ready_first):
    import asyncio
    from dataclasses import replace
    from tests.trusted_intake_fixtures import LocalIntakeSession

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    upload_entered, prepare_entered = asyncio.Event(), asyncio.Event()
    upload_drained, prepare_drained = asyncio.Event(), asyncio.Event()
    session = LocalIntakeSession()

    async def prepare_vm(value):
        await upload_entered.wait()
        prepare_entered.set()
        try:
            if session_ready_first:
                return session
            await asyncio.Event().wait()
        finally:
            prepare_drained.set()

    async def upload(*args, **kwargs):
        upload_entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            upload_drained.set()

    runtime = replace(case.runtime, intake=SimpleNamespace(prepare=prepare_vm),
                      preparation=SimpleNamespace(prepare=upload))
    command = _command(runtime, actor)
    _patch_selected_owners(monkeypatch, case)
    pending = asyncio.create_task(command.prepare(request))
    await asyncio.wait_for(prepare_entered.wait(), 2)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pending, 2)
    assert upload_drained.is_set() and prepare_drained.is_set()
    assert session.closed is session_ready_first
    assert session.aborted is session_ready_first
    assert session.default_bindings == []
    prepared.inspect.assert_not_awaited()
    case.coordinator.reserve.assert_not_awaited()
    case.selected_execution.execute.assert_not_awaited()
    case.durable.admit_in_transaction.assert_not_awaited()
    case.durable.publish_after_commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unconfirmed_intake_deadline_returns_recoverable_failure(monkeypatch):
    from app.modules.artifacts.preparation import ArtifactPreparationDeadlineError
    from app.modules.artifacts.api import SubmissionBundlePreparationInfrastructureUnavailable

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    case.selected_execution.execute.side_effect = ArtifactPreparationDeadlineError("expired")
    command = _command(case.runtime, actor)
    _patch_selected_owners(monkeypatch, case)
    with pytest.raises(SubmissionBundlePreparationInfrastructureUnavailable) as failure:
        await command.prepare(request)
    assert str(failure.value) == "pre_submission_attempt_outcome_unresolved"
    case.durable.admit_in_transaction.assert_not_awaited()
    case.durable.publish_after_commit.assert_not_awaited()
