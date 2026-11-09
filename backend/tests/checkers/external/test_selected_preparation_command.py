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
    case.runtime.preparation.prepare.assert_awaited_once_with(
        request.byte_source, media_type="application/zip", maximum_bytes=524_288_000,
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
async def test_intake_prepares_after_sealing_with_exact_size_and_remaining_deadline(monkeypatch):
    import asyncio
    from dataclasses import replace
    from tests.trusted_intake_fixtures import LocalIntakeSession

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    events = []
    session = LocalIntakeSession()

    async def prepare_vm(value):
        assert events == ["upload_started", "upload_sealed"]
        assert value.phase == "pre_submit" and value.archive_byte_count == prepared.commitment.byte_count
        assert 0 < value.deadline_ms < 1990
        events.append("vm_ready")
        return session

    async def upload(*args, **kwargs):
        events.append("upload_started")
        await asyncio.sleep(0.02)
        case.coordinator.reserve.assert_not_awaited()
        events.append("upload_sealed")
        return prepared

    runtime = replace(case.runtime, intake=SimpleNamespace(prepare=prepare_vm),
                      preparation=SimpleNamespace(prepare=upload), artifact_deadline_ms=2000)
    command = _command(runtime, actor)
    _patch_selected_owners(monkeypatch, case)
    await command.prepare(request)
    assert events == ["upload_started", "upload_sealed", "vm_ready"]
    prepared.close.assert_awaited_once()
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
async def test_upload_failure_does_not_allocate_intake_or_reserve_attempt(monkeypatch):
    from dataclasses import replace

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    intake = SimpleNamespace(prepare=AsyncMock())
    runtime = replace(case.runtime, intake=intake,
                      preparation=SimpleNamespace(prepare=AsyncMock(side_effect=OSError("upload interrupted"))))
    command = _command(runtime, actor)
    _patch_selected_owners(monkeypatch, case)
    with pytest.raises(OSError, match="upload interrupted"):
        await command.prepare(request)
    intake.prepare.assert_not_awaited()
    prepared.close.assert_not_awaited()
    case.coordinator.reserve.assert_not_awaited()
    case.durable.admit_in_transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_vm_preparation_closes_already_sealed_source(monkeypatch):
    from dataclasses import replace
    from app.interfaces.external_services import ExternalServiceUnavailableError
    from app.modules.artifacts.api import SubmissionBundlePreparationInfrastructureUnavailable

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    intake = SimpleNamespace(prepare=AsyncMock(side_effect=ExternalServiceUnavailableError()))
    command = _command(replace(case.runtime, intake=intake), actor)
    _patch_selected_owners(monkeypatch, case)
    with pytest.raises(SubmissionBundlePreparationInfrastructureUnavailable):
        await command.prepare(request)
    prepared.close.assert_awaited_once()
    case.coordinator.reserve.assert_not_awaited()
    case.durable.admit_in_transaction.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["upload", "boot", "inspection"])
async def test_caller_cancellation_drains_current_stage_and_sealed_source(monkeypatch, stage):
    import asyncio
    from dataclasses import replace
    from tests.trusted_intake_fixtures import LocalIntakeSession

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    entered, drained = asyncio.Event(), asyncio.Event()
    session = LocalIntakeSession()

    async def blocked():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            drained.set()

    async def prepare_vm(value):
        if stage == "boot":
            await blocked()
        return session

    async def upload(*args, **kwargs):
        if stage == "upload":
            await blocked()
        return prepared

    async def inspect(*args, **kwargs):
        await blocked()

    intake = SimpleNamespace(prepare=AsyncMock(side_effect=prepare_vm))
    prepared.inspect = AsyncMock(side_effect=inspect)
    runtime = replace(case.runtime, intake=intake, preparation=SimpleNamespace(prepare=upload))
    command = _command(runtime, actor)
    _patch_selected_owners(monkeypatch, case)
    pending = asyncio.create_task(command.prepare(request))
    await asyncio.wait_for(entered.wait(), 2)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pending, 2)
    assert drained.is_set()
    if stage == "upload":
        intake.prepare.assert_not_awaited()
        prepared.close.assert_not_awaited()
    else:
        prepared.close.assert_awaited_once()
    assert session.closed is (stage == "inspection")
    assert session.aborted is (stage == "inspection")
    assert session.default_bindings == []
    case.coordinator.reserve.assert_not_awaited()
    case.selected_execution.execute.assert_not_awaited()
    case.durable.admit_in_transaction.assert_not_awaited()
    case.durable.publish_after_commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_slow_upload_expires_original_deadline_before_vm_allocation(monkeypatch):
    import asyncio
    from dataclasses import replace
    from app.modules.artifacts.api import SubmissionBundlePreparationInfrastructureUnavailable

    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    drained = asyncio.Event()

    async def upload(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            drained.set()

    intake = SimpleNamespace(prepare=AsyncMock())
    runtime = replace(case.runtime, intake=intake, preparation=SimpleNamespace(prepare=upload), artifact_deadline_ms=20)
    command = _command(runtime, actor)
    _patch_selected_owners(monkeypatch, case)
    with pytest.raises(SubmissionBundlePreparationInfrastructureUnavailable):
        await asyncio.wait_for(command.prepare(request), 2)
    assert drained.is_set()
    intake.prepare.assert_not_awaited()
    case.coordinator.reserve.assert_not_awaited()
    case.durable.admit_in_transaction.assert_not_awaited()


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
