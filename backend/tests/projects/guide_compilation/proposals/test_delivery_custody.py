"""Delivery selection requires an exact immutable request, never an attempt alone."""

from types import SimpleNamespace
from uuid import uuid4, uuid5

import pytest

from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDeliveryError
from app.core.identifiers import new_record_id
from app.modules.projects.guide_compilation.correction_request import correction_request_selector
from app.modules.projects.guide_compilation.delivery_request import manual_delivery_attempt


def delivery_case():
    setup = SimpleNamespace(id=str(new_record_id()), project_id=str(new_record_id()), guide_id=str(new_record_id()),
                            source_snapshot_id=str(new_record_id()), setup_generation=2)
    values = {key:getattr(setup,key) for key in ("project_id","guide_id","source_snapshot_id","setup_generation")}
    attempt = SimpleNamespace(**values, id=new_record_id(), setup_run_id=setup.id, runtime_configuration={"saved":True})
    correction = SimpleNamespace(operation_id=new_record_id(), compilation_id=new_record_id(),
                                 project_id=setup.project_id, guide_id=setup.guide_id,
                                 successor_setup_generation=2, target_json={"source_snapshot_id":setup.source_snapshot_id})
    selector = correction_request_selector(correction.operation_id)
    operation = SimpleNamespace(**values, attempt_id=attempt.id, setup_run_id=setup.id,
                                operation_id=new_record_id(), request_id=uuid5(selector, "request"),
                                idempotency_key=uuid5(selector, "idempotency"),
                                request_trigger="project_manager", expected_predecessor_compilation_id=correction.compilation_id,
                                source_mutation_operation_id=None, source_authorization_decision_event_id=None)
    class Session:
        async def execute(self, statement):
            return SimpleNamespace(scalar_one_or_none=lambda:self.correction)
        async def scalars(self, statement):
            return SimpleNamespace(all=lambda:self.operations)
    session = Session()
    session.correction = correction
    session.operations = [operation]
    return session,setup,attempt,operation,correction


@pytest.mark.parametrize("fault", ["no_attempt","no_operation","duplicate","no_correction","trigger","project","guide", "generation","source", "setup", "operation", "predecessor","origin", "configuration"])
async def test_exact_manual_request_required(fault):
    session,setup,attempt,operation,correction = delivery_case()
    assert await manual_delivery_attempt(session,setup,attempt) == attempt.id
    if fault == "no_attempt":
        attempt = None
    elif fault == "no_operation":
        session.operations = []
    elif fault == "duplicate":
        session.operations.append(operation)
    elif fault == "no_correction":
        session.correction = None
    elif fault == "trigger":
        operation.request_trigger = "unsupported"
    elif fault == "configuration":
        attempt.runtime_configuration = None
    else:
        field = {"project":"project_id","guide":"guide_id","generation":"setup_generation", "source":"source_snapshot_id", "setup":"setup_run_id", "operation":"operation_id", "predecessor":"expected_predecessor_compilation_id", "origin":"source_mutation_operation_id"}[fault]
        setattr(operation,field,uuid4())
    with pytest.raises(ProjectGuideCompilationDeliveryError):
        await manual_delivery_attempt(session,setup,attempt)


async def test_initial_delivery_requires_explicit_request_and_cannot_use_historical_automatic_authority():
    session, setup, attempt, operation, _ = delivery_case()
    session.correction = None
    with pytest.raises(ProjectGuideCompilationDeliveryError):
        await manual_delivery_attempt(session, setup, None)
    operation.expected_predecessor_compilation_id = None
    operation.request_id = uuid5(operation.idempotency_key, "guide-compilation-request")
    assert await manual_delivery_attempt(session, setup, attempt) == attempt.id
    operation.request_trigger = "automatic_source_ready"
    with pytest.raises(ProjectGuideCompilationDeliveryError):
        await manual_delivery_attempt(session, setup, attempt)


@pytest.mark.parametrize("failure,expected", [
    ("storage", "storage_unavailable"),
    ("database", "storage_unavailable"),
    ("integrity", "operation_conflict"),
])
async def test_correction_dispatch_distinguishes_storage_from_conflict(monkeypatch, failure, expected):
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy.exc import SQLAlchemyError
    from app.modules.projects.api.guide_proposals import GuideProposalError, GuideProposalSelection
    from app.modules.projects.guide_compilation import correction_dispatch
    from app.modules.projects.guide_compilation.repository import (
        GuideCompilationIntegrityError, GuideCompilationStorageError,
    )

    session = MagicMock()
    session.begin.return_value = AsyncMock()
    session.scalar = AsyncMock(return_value=SimpleNamespace(
        successor_setup_run_id=str(uuid4()), successor_setup_generation=2,
        target_json={"source_snapshot_id": str(uuid4())},
    ))
    errors = {"storage": GuideCompilationStorageError, "database": SQLAlchemyError,
              "integrity": GuideCompilationIntegrityError}
    request = AsyncMock(side_effect=errors[failure]("private database details"))
    monkeypatch.setattr(correction_dispatch.GuideCompilationService, "request_correction", request)
    publish = AsyncMock()
    monkeypatch.setattr(correction_dispatch, "dispatch_project_guide_compilation_after_commit", publish)
    service = correction_dispatch.GuideCompilationDispatchService(
        session, object(), object(), profiles=object()
    )
    monkeypatch.setattr(service, "_selected_inputs", AsyncMock(return_value=object()))
    selection = GuideProposalSelection(project_id=uuid4(), guide_id=uuid4(), compilation_id=uuid4())
    actor, operation = object(), uuid4()
    with pytest.raises(GuideProposalError) as error:
        await service.dispatch(selection, operation, actor=actor)
    assert error.value.code == expected
    assert "private database details" not in str(error.value)
    request.assert_awaited_once_with(actor=actor, correction_operation_id=operation)
    publish.assert_not_awaited()
