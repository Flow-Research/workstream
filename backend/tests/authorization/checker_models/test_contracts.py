"""Discriminating pure contracts for checker model and output authority."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api.checker_output_authority import (
    CheckerOutputCommitmentAuthorityFacts,
)
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.checker_output_authorization import (
    PreparedCheckerOutputWriteAuthorization,
)
from app.modules.authorization.domain.audit import (
    AuthorizationDecisionResourceType,
    CONTEXT_DIGEST_RESOURCE_TYPES,
)
from app.modules.authorization.model_usage_authorization import CheckerModelAuthorization
from app.modules.authorization.domain.model_usage import (
    GRANT,
    RECOVER,
    SETUP_PREPARE,
    ModelCallGrantAuthorityFacts,
    ModelCallRecoverAuthorityFacts,
    SetupModelPrepareAuthorityFacts,
    checker_model_call_resource,
    setup_model_usage_resource,
)
from app.modules.authorization.domain.checker_outputs import (
    BIND,
    WRITE,
    checker_output_prepare_matches,
    checker_output_prepare_resource,
    checker_output_stored_resource,
    parse_checker_output_prepare,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationDecision,
    IdentityLinkStatus,
    MatchedAuthorityKind,
    ServiceAuthorizationContext,
)
from app.modules.model_usage.api import (
    ModelCallEffectAuthorityFacts,
    ModelCallExecutionFacts,
    ModelCallUnavailable,
    ModelPaidSlotKey,
    SetupModelOutputReservation,
    SetupModelOutputSelector,
    SetupModelOutputSlot,
    SetupModelUsageSlotKey,
)
from app.modules.checkers.api.output_custody import (
    CheckerOutputReservation,
    CheckerOutputSelector,
    CheckerOutputSlot,
    generated_output_subject,
)
from app.modules.checkers.api.trial_evidence import (
    TrialEvidenceOrigin,
    TrialEvidenceReservation,
    TrialEvidenceSelector,
    TrialEvidenceSlot,
    TrialEvidenceStableSubject,
)


def sha(label: str) -> str:
    return canonical_json_hash({"label": label})


def execution(*, project_id=None, task_id=None) -> ModelCallExecutionFacts:
    return ModelCallExecutionFacts(
        project_id=project_id or new_record_id(),
        task_id=task_id or new_record_id(),
        assignment_id=new_record_id(),
        submission_id=new_record_id(),
        submission_version=1,
        evaluation_request_id=new_record_id(),
        evaluation_generation=1,
        checker_run_id=new_record_id(),
        worker_lease_id=new_record_id(),
        worker_lease_generation=1,
        worker_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def paid_slot(current: ModelCallExecutionFacts) -> ModelPaidSlotKey:
    return ModelPaidSlotKey(
        project_id=current.project_id,
        assignment_id=current.assignment_id,
        submission_id=current.submission_id,
        submission_version=current.submission_version,
        requirement_id="model_quality",
        registry_entry_digest=sha("registry"),
        configuration_sha256=sha("configuration"),
        profile_id=new_record_id(),
        profile_version=1,
        profile_digest=sha("profile"),
    )


def effect(current: ModelCallExecutionFacts, slot: ModelPaidSlotKey):
    return ModelCallEffectAuthorityFacts(
        project_id=current.project_id,
        task_id=current.task_id,
        slot_id=new_record_id(),
        slot_key=slot,
        attempt_id=new_record_id(),
        internal_call_request_id=new_record_id(),
    )


def selector(current: ModelCallExecutionFacts, slot: ModelPaidSlotKey, *, role="model_request"):
    return CheckerOutputSelector(
        paid_slot=slot,
        task_id=current.task_id,
        model_call_slot_id=new_record_id(),
        model_call_attempt_id=new_record_id(),
        slot_key=role,
        content_sha256=sha(role),
        execution=current if role == "model_request" else None,
    )


def trial_reservation() -> TrialEvidenceReservation:
    project_id = new_record_id()
    selected = TrialEvidenceSelector(
        trial_evidence_id=new_record_id(),
        project_id=project_id,
        content_sha256=sha("trial receipt"),
    )
    return TrialEvidenceReservation(
        selector=selected,
        subject=TrialEvidenceStableSubject(
            project_id=project_id,
            task_id=new_record_id(),
            assignment_id=new_record_id(),
            submission_id=new_record_id(),
            submission_version=2,
            requirement_id="terminal_systems",
            registry_entry_id=new_record_id(),
            registry_entry_digest=sha("trial registry"),
            configuration_sha256=sha("trial configuration"),
            trial_kind="reference_cases",
            slot_index=0,
            plan_sha256=sha("trial plan"),
            input_digest=sha("trial input"),
            materials_digest=sha("trial materials"),
        ),
        origin=TrialEvidenceOrigin(
            checker_run_id=new_record_id(),
            worker_lease_id=new_record_id(),
            worker_lease_generation=1,
            worker_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            external_request_digest=sha("external request"),
        ),
        slot=TrialEvidenceSlot(maximum_bytes=2048),
    )


def test_recovery_resource_rejects_substituted_effect_scope() -> None:
    current = execution()
    slot = paid_slot(current)
    altered = effect(current, slot).model_copy(update={"task_id": new_record_id()})

    with pytest.raises(ValueError, match="recovery effect mismatch"):
        checker_model_call_resource(
            RECOVER,
            ModelCallRecoverAuthorityFacts(execution=current, effect=altered),
        )


def test_grant_resource_binds_opaque_digests_and_exact_slot() -> None:
    current = execution()
    slot = paid_slot(current)
    facts = ModelCallGrantAuthorityFacts(
        execution=current,
        slot=slot,
        external_request_digest=sha("external request"),
        token_hash=sha("opaque token"),
    )
    resource = checker_model_call_resource(GRANT, facts)

    assert resource.scope_project_id == current.project_id
    assert resource.resource_id == current.evaluation_request_id
    assert "token" not in resource.model_dump(mode="json")["facts"]
    assert resource.facts.token_hash == sha("opaque token")


@pytest.mark.parametrize("action", [WRITE, BIND])
def test_output_prepare_accepts_its_json_packet_without_coercing_integers(action) -> None:
    """Prepared AUTH receives JSON values, including nested UUIDs and timestamps."""
    current = execution()
    prepared = checker_output_prepare_resource(action, selector(current, paid_slot(current)))
    packet = prepared.model_dump(mode="json")
    assert parse_checker_output_prepare(action, packet, RuntimeError) == prepared

    packet["selector"]["paid_slot"]["submission_version"] = "1"
    with pytest.raises(RuntimeError) as rejected:
        parse_checker_output_prepare(action, packet, RuntimeError)
    assert isinstance(rejected.value.__cause__, ValidationError)
    assert any(
        error["loc"][-1] == "submission_version" and error["type"] == "int_type"
        for error in rejected.value.__cause__.errors()
    )


def setup_selector(*, role="model_request") -> SetupModelOutputSelector:
    key = SetupModelUsageSlotKey(
        compilation_attempt_id=new_record_id(),
        project_id=new_record_id(),
        guide_id=new_record_id(),
        source_snapshot_id=new_record_id(),
        setup_run_id=new_record_id(),
        setup_generation=1,
        runtime_configuration_hash=sha("runtime configuration"),
        profile_id=new_record_id(),
        profile_version=1,
        profile_digest=sha("setup profile"),
        phase="draft",
        call_index=0,
    )
    return SetupModelOutputSelector(
        slot_key=key,
        model_call_slot_id=new_record_id(),
        model_call_attempt_id=new_record_id(),
        role=role,
        content_sha256=sha(role),
    )


def test_setup_usage_resource_is_admitted_by_decision_and_audit_vocabularies() -> None:
    slot = setup_selector().slot_key
    resource = setup_model_usage_resource(
        SETUP_PREPARE,
        SetupModelPrepareAuthorityFacts(
            slot=slot,
            request_sha256=sha("setup request"),
        ),
    )

    assert resource.resource_type == "setup_model_usage"
    assert (
        TypeAdapter(AuthorizationDecisionResourceType).validate_python(
            resource.resource_type
        )
        == resource.resource_type
    )
    assert resource.resource_type in CONTEXT_DIGEST_RESOURCE_TYPES


@pytest.mark.parametrize("action", [WRITE, BIND])
def test_setup_output_resource_is_closed_to_exact_effect_and_project(action) -> None:
    selected = setup_selector()
    reservation = SetupModelOutputReservation(
        selector=selected,
        slot=SetupModelOutputSlot(key="model_request", maximum_bytes=2048),
    )
    prepared = checker_output_prepare_resource(action, selected)

    assert prepared.resource_type == "setup_model_call"
    assert prepared.resource_id == selected.model_call_attempt_id
    assert prepared.scope_project_id == selected.slot_key.project_id
    subject = generated_output_subject(reservation)
    assert subject.operation_identity == canonical_json_hash(
        {
            "request_type": "setup_model_output",
            "model_call_attempt_id": str(selected.model_call_attempt_id),
            "logical_role": "model_request",
        }
    )
    assert subject.request_digest_facts == {
        "slot_key": selected.slot_key.model_dump(mode="json"),
        "model_call_slot_id": str(selected.model_call_slot_id),
        "model_call_attempt_id": str(selected.model_call_attempt_id),
        "content_sha256": selected.content_sha256,
        "role": "model_request",
        "media_type": "application/json",
        "maximum_bytes": 2048,
    }
    assert parse_checker_output_prepare(
        action, prepared.model_dump(mode="json"), RuntimeError
    ) == prepared

    substituted = selected.model_copy(
        update={"model_call_attempt_id": new_record_id()}
    )
    with pytest.raises(ValueError, match="differs from selector"):
        checker_output_stored_resource(
            action,
            substituted,
            reservation,
            SimpleNamespace(
                put_attempt_id=new_record_id(),
                checker_request_digest=sha("custody"),
                sha256=substituted.content_sha256,
                byte_count=100,
                media_type="application/json",
                status="object_confirmed",
                content_id=None,
                replica_id=None,
                verification_receipt_id=None,
            ),
        )


def test_output_final_facts_cannot_substitute_selector_or_unverified_binding() -> None:
    current = execution()
    slot = paid_slot(current)
    selected = selector(current, slot)
    reservation = CheckerOutputReservation(
        selector=selected,
        slot=CheckerOutputSlot(key="model_request", maximum_bytes=1024),
    )
    request_digest = canonical_json_hash(
        {
            "model_call_slot_id": str(selected.model_call_slot_id),
            "model_call_attempt_id": str(selected.model_call_attempt_id),
            "paid_slot": selected.paid_slot.model_dump(mode="json"),
            "task_id": str(selected.task_id),
            "content_sha256": selected.content_sha256,
            "slot_key": "model_request",
            "media_type": "application/json",
            "maximum_bytes": 1024,
        }
    )
    stored = SimpleNamespace(
        put_attempt_id=new_record_id(),
        checker_request_digest=request_digest,
        sha256=selected.content_sha256,
        byte_count=100,
        media_type="application/json",
        status="verified",
        content_id=new_record_id(),
        replica_id=new_record_id(),
        verification_receipt_id=new_record_id(),
    )
    prepared = checker_output_prepare_resource(BIND, selected)
    final = checker_output_stored_resource(BIND, selected, reservation, stored)

    assert checker_output_prepare_matches(prepared, final)
    substituted = selected.model_copy(update={"model_call_attempt_id": new_record_id()})
    assert not checker_output_prepare_matches(
        prepared,
        final.model_copy(
            update={
                "resource_id": substituted.model_call_attempt_id,
                "selector": substituted,
            }
        ),
    )
    unverified = SimpleNamespace(
        **{
            **stored.__dict__,
            "status": "object_confirmed",
            "content_id": None,
            "replica_id": None,
            "verification_receipt_id": None,
        }
    )
    assert checker_output_prepare_matches(
        checker_output_prepare_resource(WRITE, selected),
        checker_output_stored_resource(WRITE, selected, reservation, unverified),
    )
    with pytest.raises(ValidationError, match="binding requires verified ancestry"):
        checker_output_stored_resource(
            BIND,
            selected,
            reservation,
            unverified,
        )


def test_trial_output_uses_closed_resource_and_owner_digest() -> None:
    reservation = trial_reservation()
    selected = reservation.selector
    prepared = checker_output_prepare_resource(WRITE, selected)
    assert (
        parse_checker_output_prepare(WRITE, prepared.model_dump(mode="json"), RuntimeError)
        == prepared
    )
    stored = SimpleNamespace(
        put_attempt_id=new_record_id(),
        checker_request_digest=reservation.owner_digest,
        sha256=selected.content_sha256,
        byte_count=100,
        media_type="application/json",
        status="verified",
        content_id=new_record_id(),
        replica_id=new_record_id(),
        verification_receipt_id=new_record_id(),
    )
    final = checker_output_stored_resource(BIND, selected, reservation, stored)

    assert prepared.resource_type == "checker_trial_evidence"
    assert prepared.resource_id == selected.trial_evidence_id
    assert prepared.scope_project_id == selected.project_id
    assert final.resource_type == "checker_trial_evidence"
    assert checker_output_prepare_matches(checker_output_prepare_resource(BIND, selected), final)
    assert (
        canonical_json_hash(generated_output_subject(reservation).request_digest_facts)
        == reservation.owner_digest
    )

    current = execution()
    model = selector(current, paid_slot(current))
    with pytest.raises(ValidationError, match="reservation differs"):
        checker_output_stored_resource(BIND, model, reservation, stored)


def test_trial_output_rejects_substituted_project_and_digest() -> None:
    reservation = trial_reservation()
    selected = reservation.selector
    stored = SimpleNamespace(
        put_attempt_id=new_record_id(),
        checker_request_digest=sha("substituted owner"),
        sha256=selected.content_sha256,
        byte_count=100,
        media_type="application/json",
        status="verified",
        content_id=new_record_id(),
        replica_id=new_record_id(),
        verification_receipt_id=new_record_id(),
    )
    with pytest.raises(ValidationError, match="differs from its reservation"):
        checker_output_stored_resource(BIND, selected, reservation, stored)

    substituted = selected.model_copy(update={"project_id": new_record_id()})
    with pytest.raises(ValidationError, match="reservation differs"):
        checker_output_stored_resource(BIND, substituted, reservation, stored)


@pytest.mark.asyncio
async def test_trial_write_authority_derives_slot_from_reservation() -> None:
    reservation = trial_reservation()

    class CapturingAuthority(PreparedCheckerOutputWriteAuthorization):
        resource = None

        async def _consume(self, resource) -> None:
            self.resource = resource

    authority = CapturingAuthority(object())
    authority._selector = reservation.selector
    await authority.consume(
        CheckerOutputCommitmentAuthorityFacts(
            reservation=reservation,
            slot_key="trial_receipt",
            sha256=reservation.selector.content_sha256,
            byte_count=100,
            media_type="application/json",
        )
    )

    assert authority.resource.resource_type == "checker_trial_evidence"
    assert authority.resource.reservation == reservation


class _Prepared:
    def __init__(self, authorization) -> None:
        self._authorization = authorization
        self._context = authorization._context
        self.resource = None

    async def prepare(self, action, caller_input, scope):
        self.action, self.input, self.scope = action, caller_input, scope
        return object.__new__(PreparedAuthorizationHandle)

    async def consume(self, handle, action, caller_input, resource):
        self.resource = resource
        return AuthorizationDecision(
            decision_id=new_record_id(),
            allowed=True,
            action_id=action,
            permission_id=PermissionId.CHECKER_MODEL_CALL_GRANT,
            resource_type=resource.resource_type,
            resource_id=resource.resource_id,
            resource_context_digest=sha("decision resource"),
            matched_authority_kind=MatchedAuthorityKind.FIXED_SERVICE,
            matched_grant_id=None,
            matched_scope_project_id=None,
            request_id=self._context.request_id,
            correlation_id=self._context.correlation_id,
            revalidated=True,
            denial_code=None,
        )


class _Authorization:
    def __init__(self, context) -> None:
        self._context = context


@pytest.mark.asyncio
async def test_grant_adapter_emits_exact_resource_and_rejects_wrong_service() -> None:
    current = execution()
    slot = paid_slot(current)
    context = ServiceAuthorizationContext(
        actor_profile_id=new_record_id(),
        actor_kind=ActorKind.SERVICE,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=new_record_id(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        service_identity=ServiceIdentity.CHECKER_POST_SUBMIT,
        request_id=new_record_id(),
        correlation_id=new_record_id(),
    )
    authorization = _Authorization(context)
    prepared = _Prepared(authorization)
    adapter = CheckerModelAuthorization(authorization, prepared)

    evidence = await adapter.authorize_grant(
        current, slot, sha("external request"), sha("opaque token")
    )

    assert prepared.action is ActionId.CHECKER_MODEL_CALL_GRANT
    assert prepared.resource.facts.execution == current
    assert prepared.resource.facts.slot == slot
    assert evidence.facts_digest == canonical_json_hash(
        {
            "action": "grant",
            "facts": prepared.resource.facts.model_dump(mode="json"),
        }
    )

    wrong_context = context.model_copy(
        update={"service_identity": ServiceIdentity.ARTIFACT_CHECKER_OUTPUT}
    )
    wrong_authorization = _Authorization(wrong_context)
    with pytest.raises(ModelCallUnavailable, match="authority_unavailable"):
        await CheckerModelAuthorization(
            wrong_authorization, _Prepared(wrong_authorization)
        ).authorize_grant(current, slot, sha("external request"), sha("opaque token"))
