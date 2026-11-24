"""Current selected PRE revision binding and retained admission publisher proofs."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.artifacts import selected_pre_submit_source_contracts
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.artifacts.selected_pre_submit_admission import (
    bind_selected_pre_submit_admission,
    build_selected_pre_submit_reservation,
    selected_pre_submit_attempt_request_digest,
)
from app.modules.artifacts.submission_admission import (
    SubmissionBundleAdmissionPublicationError,
    SubmissionBundleAdmissionPublisher,
)
from app.modules.artifacts.submission_manifest import SubmissionCanonicalPredecessor
from app.modules.checkers.api.external import (
    PRE_SUBMIT_INPUT_SCHEMA_ID,
    ExternalCheckerRegistryEntry,
    ExternalCheckerSchema,
    external_checker_json_hash,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerBinding,
    LockedExternalCheckerPolicies,
    LockedExternalPostSubmitPolicy,
    LockedExternalPreSubmitPolicy,
    LockedWorkstreamDefault,
)
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
)
from app.modules.tasks.api.submission_context import require_revision_acknowledgement
from app.modules.tasks.api import TaskSubmissionContextUnavailable
from tests.checkers.external.support import SHA, registry_entry

def _hex_sha(character: str) -> str:
    return "sha256:" + character * 64


def test_revision_acknowledgement_changes_selected_request_and_retains_old_bytes() -> None:
    """A new acknowledgement is frozen; old selected requests keep their digest."""
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation
    from app.modules.checkers.api.default_checker import WorkstreamDefaultPredecessor

    retained = _source_reservation()
    old_body = retained.canonical_body()
    assert SelectedPreSubmitReservationFacts.from_canonical_body(old_body, source_contracts=selected_pre_submit_source_contracts()).canonical_body() == old_body
    assert "revision_preparation_id" not in old_body["admission_lineage"]

    predecessor_id, manifest_id, preparation_id = (
        new_record_id(), new_record_id(), new_record_id()
    )
    acknowledged = replace(
        retained.admission_lineage,
        predecessor_submission_id=predecessor_id,
        predecessor_submission_version=1,
        checker_remediation_manifest_id=manifest_id,
        revision_preparation_id=preparation_id,
        revision_preparation_sha256=_hex_sha("b"),
    )
    predecessor = WorkstreamDefaultPredecessor(predecessor_id, 1, retained.source.raw_sha256, SHA)
    selected = replace(retained, admission_lineage=acknowledged,
        default_context=replace(retained.default_context, predecessor=predecessor,
            current_predecessor=predecessor, predecessor_exists=True,
            predecessor_rules_sha256=retained.default_context.current_rules_sha256),
        source_contracts=selected_pre_submit_source_contracts())
    assert retained.canonical_body() == old_body
    assert selected.request_digest != retained.request_digest
    body = selected.canonical_body()
    assert body["admission_lineage"]["revision_preparation_id"] == str(preparation_id)
    assert body["admission_lineage"]["revision_preparation_sha256"] == _hex_sha("b")
    assert SelectedPreSubmitReservationFacts.from_canonical_body(body, source_contracts=selected_pre_submit_source_contracts()).request_digest == selected.request_digest
    null_ack = dict(body)
    null_ack["admission_lineage"] = dict(body["admission_lineage"])
    null_ack["admission_lineage"]["revision_preparation_id"] = None
    with pytest.raises(ValueError, match="selected PRE admission lineage is invalid"):
        SelectedPreSubmitReservationFacts.from_canonical_body(null_ack, source_contracts=selected_pre_submit_source_contracts())

    request = dict(
        actor_profile_id=selected.actor_profile_id,
        identity_link_id=selected.identity_link_id,
        task_id=selected.task_id,
        assignment_id=selected.assignment_id,
        predecessor_submission_id=predecessor_id,
        idempotency_key=selected.idempotency_key,
        archive_sha256=selected.archive_sha256,
        archive_byte_count=selected.archive_byte_count,
        packet_sha256=acknowledged.packet_sha256,
    )
    without_ack = selected_pre_submit_attempt_request_digest(**request)
    with_ack = selected_pre_submit_attempt_request_digest(
        **request, revision_preparation_id=preparation_id,
        revision_preparation_sha256=_hex_sha("b"),
    )
    assert without_ack != with_ack
    with pytest.raises(ValueError, match="incomplete"):
        selected_pre_submit_attempt_request_digest(
            **request, revision_preparation_id=preparation_id,
        )
    with pytest.raises(ValueError, match="selected PRE admission lineage is invalid"):
        replace(retained.admission_lineage, revision_preparation_id=preparation_id,
                revision_preparation_sha256=_hex_sha("b"))


def test_revision_acknowledgement_requires_exact_current_preparation() -> None:
    """The explicit pair is required for revisions and forbidden on initial intake."""
    predecessor_id, manifest_id, preparation_id = (
        new_record_id(), new_record_id(), new_record_id()
    )
    revision = SimpleNamespace(
        preparation_id=preparation_id,
        preparation_sha256=_hex_sha("c"),
        source_submission_id=predecessor_id,
        source_routing_manifest_id=manifest_id,
    )
    task = SimpleNamespace(
        predecessor=SimpleNamespace(submission_id=predecessor_id),
        checker_remediation_manifest_id=manifest_id,
        revision_context=revision,
    )
    require_revision_acknowledgement(task, str(preparation_id), _hex_sha("c"))
    for acknowledged_id, acknowledged_hash, code in (
        (str(new_record_id()), _hex_sha("c"), "revision_context_changed"),
        (None, None, "revision_acknowledgement_required"),
        (str(preparation_id), _hex_sha("d"), "revision_context_changed"),
    ):
        with pytest.raises(TaskSubmissionContextUnavailable) as refused:
            require_revision_acknowledgement(task, acknowledged_id, acknowledged_hash)
        assert refused.value.code == code
    with pytest.raises(TaskSubmissionContextUnavailable) as refused:
        require_revision_acknowledgement(
            SimpleNamespace(predecessor=None), str(preparation_id), _hex_sha("c")
        )
    assert refused.value.code == "revision_acknowledgement_invalid"


def _retained_admission_reservation():
    from app.modules.checkers.api.historical_selected_pre_submit import HistoricalSelectedPreSubmitReservation
    from tests.checkers.external.test_selected_pre_submit_coordination import _retained_v1

    selected = HistoricalSelectedPreSubmitReservation.from_canonical_body(
        _retained_v1("selected_pre_v1_completed")["request"])
    lineage = selected.admission_lineage
    return lineage.semantic_manifest_body, lineage.post_submit_policy_body, selected


def _selected_admission_publisher_fixture(selected):
    from tests.checkers.external.test_selected_pre_submit_coordination import _retained_v1

    terminal = _retained_v1("selected_pre_v1_completed")["terminal"] | {
        "reservation": selected.canonical_body(), "request_digest": selected.request_digest,
    }
    attempt = SimpleNamespace(
        id=str(new_record_id()),
        producer_request_type="submission_bundle",
        producer_ref=str(selected.actor_profile_id),
        project_id=str(selected.project_id),
        task_id=str(selected.task_id),
        sha256=selected.archive_sha256,
        byte_count=selected.archive_byte_count,
        media_type="application/zip",
        replica_id=str(new_record_id()),
        receipt_id=str(new_record_id()),
    )
    job = SimpleNamespace(
        id=str(new_record_id()),
        originating_put_attempt_id=attempt.id,
        replica_id=attempt.replica_id,
        execution_generation=2,
    )
    intent = SimpleNamespace(
        id=str(new_record_id()),
        pre_submit_evidence_set_id=None,
        selected_pre_submit_run_id=str(selected.attempt_id),
        selected_request_json=selected.canonical_body(),
        selected_request_digest=selected.request_digest,
        selected_terminal_json=terminal,
        selected_terminal_digest=canonical_json_hash(terminal),
    )
    replica = SimpleNamespace(
        id=attempt.replica_id,
        content_id=str(new_record_id()),
        verification_state="verified",
        availability_state="available",
        integrity_state="valid",
    )
    content = SimpleNamespace(
        id=replica.content_id,
        sha256=attempt.sha256,
        byte_count=attempt.byte_count,
    )
    verification = SimpleNamespace(
        id=str(new_record_id()),
        verification_job_id=job.id,
        execution_generation=job.execution_generation,
        outcome="verified",
        observed_sha256=attempt.sha256,
        observed_byte_count=attempt.byte_count,
    )
    session = SimpleNamespace(
        no_autoflush=nullcontext(),
        execute=AsyncMock(
            return_value=SimpleNamespace(
                one_or_none=lambda: SimpleNamespace(
                    producer_request_type="submission_bundle",
                    selected_request_json=selected.canonical_body(),
                )
            )
        ),
        scalar=AsyncMock(
            side_effect=[
                job,
                attempt,
                intent,
                None,
                replica,
                verification,
                content,
                SimpleNamespace(id=attempt.receipt_id),
                datetime.now(UTC),
            ]
        ),
        add=Mock(),
        flush=AsyncMock(),
    )
    return session, job, verification, intent


def _open_input_schema() -> ExternalCheckerSchema:
    document = {"type": "object"}
    return ExternalCheckerSchema(
        schema_id=PRE_SUBMIT_INPUT_SCHEMA_ID,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def _policy() -> LockedExternalPreSubmitPolicy:
    values = registry_entry().model_dump()
    values["input_schema"] = _open_input_schema()
    # The immutable entry digest includes the input schema.
    spec = {
        key: value
        for key, value in values.items()
        if key
        not in {
            "registry_entry_id",
            "entry_digest",
            "registration_operation_id",
            "registered_by_actor_profile_id",
            "authorization_decision_event_id",
            "created_at",
        }
    }
    spec["input_schema"] = values["input_schema"].model_dump(mode="json")
    values["entry_digest"] = external_checker_json_hash(spec)
    registry = ExternalCheckerRegistryEntry.model_validate(values)
    binding = LockedExternalCheckerBinding(
        requirement_id="project.archive_rules",
        stage="pre_submit",
        registry=registry,
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
    )
    default = LockedWorkstreamDefault()
    body = {
        "schema_version": "external_pre_submit_policy.v1",
        "workstream_default": default.model_dump(mode="json"),
        "entries": [binding.model_dump(mode="json")],
    }
    return LockedExternalPreSubmitPolicy(
        workstream_default=default,
        entries=(binding,),
        policy_sha256=canonical_json_hash(body),
    )


def _empty_policy() -> LockedExternalPreSubmitPolicy:
    default = LockedWorkstreamDefault()
    body = {
        "schema_version": "external_pre_submit_policy.v1",
        "workstream_default": default.model_dump(mode="json"),
        "entries": [],
    }
    return LockedExternalPreSubmitPolicy(
        workstream_default=default,
        entries=(),
        policy_sha256=canonical_json_hash(body),
    )


def _policies() -> LockedExternalCheckerPolicies:
    pre = _policy()
    post_body = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [],
    }
    post = LockedExternalPostSubmitPolicy(
        entries=(),
        policy_sha256=canonical_json_hash(post_body),
    )
    body = {
        "schema_version": "external_checker_policies.v1",
        "pre_submit": pre.model_dump(mode="json"),
        "post_submit": post.model_dump(mode="json"),
    }
    return LockedExternalCheckerPolicies(
        pre_submit=pre,
        post_submit=post,
        policies_sha256=canonical_json_hash(body),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [False, True])
async def test_selected_pre_terminal_publishes_self_contained_ready_admission(
    replacement: bool,
) -> None:
    manifest, post_policy, selected = _retained_admission_reservation()
    if replacement:
        selected = replace(
            selected,
            admission_lineage=replace(
                selected.admission_lineage,
                predecessor_submission_id=new_record_id(),
                predecessor_submission_version=1,
                checker_remediation_manifest_id=new_record_id(),
            ),
        )
    lineage = selected.admission_lineage
    assert (
        type(lineage).from_canonical_body(lineage.canonical_body()) == lineage
    )
    session, job, verification, _ = _selected_admission_publisher_fixture(selected)
    task_contexts = SimpleNamespace(lock_retained_submission_parents=AsyncMock())
    publisher = SubmissionBundleAdmissionPublisher(session)
    retained_parents = await publisher.lock_retained_submission_parents(
        verification_job_id=job.id,
        task_contexts=task_contexts,
    )

    admission = await publisher.publish_verified(
        verification_job_id=job.id,
        verification_receipt_id=verification.id,
        retained_parents=retained_parents,
    )

    task_contexts.lock_retained_submission_parents.assert_awaited_once_with(
        retained_parents
    )
    assert retained_parents is not None
    assert retained_parents.project_id == selected.project_id
    assert retained_parents.task_id == selected.task_id
    assert retained_parents.assignment_id == selected.assignment_id
    assert retained_parents.contributor_id == selected.actor_profile_id
    assert admission.checker_remediation_manifest_id == (
        str(lineage.checker_remediation_manifest_id) if replacement else None
    )
    assert admission.pre_submit_evidence_set_id is None
    assert admission.selected_pre_submit_run_id == str(selected.attempt_id)
    assert admission.packet_sha256 == selected.admission_lineage.packet_sha256
    assert admission.semantic_manifest_body == manifest
    assert (
        admission.selected_post_submit_policy_sha256
        == selected.admission_lineage.post_submit_policy_sha256
    )
    assert admission.selected_post_submit_policy_body == post_policy


@pytest.mark.asyncio
async def test_selected_pre_publication_requires_exact_retained_task_identity() -> None:
    _, _, selected = _retained_admission_reservation()
    session, job, verification, intent = _selected_admission_publisher_fixture(selected)
    task_contexts = SimpleNamespace(lock_retained_submission_parents=AsyncMock())
    publisher = SubmissionBundleAdmissionPublisher(session)
    retained_parents = await publisher.lock_retained_submission_parents(
        verification_job_id=job.id,
        task_contexts=task_contexts,
    )
    assert retained_parents is not None
    intent.selected_request_json = replace(
        selected,
        actor_profile_id=new_record_id(),
    ).canonical_body()

    with pytest.raises(
        SubmissionBundleAdmissionPublicationError,
        match="retained TASK identity changed",
    ):
        await publisher.publish_verified(
            verification_job_id=job.id,
            verification_receipt_id=verification.id,
            retained_parents=retained_parents,
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_selected_pre_publication_requires_task_port_before_terminal_reads() -> None:
    _, _, selected = _retained_admission_reservation()
    session, job, _, _ = _selected_admission_publisher_fixture(selected)

    with pytest.raises(RuntimeError, match="TASK composition is unavailable"):
        await SubmissionBundleAdmissionPublisher(
            session
        ).lock_retained_submission_parents(
            verification_job_id=job.id,
            task_contexts=None,
        )

    session.scalar.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_selected_pre_task_lock_failure_propagates_before_terminal_reads() -> None:
    _, _, selected = _retained_admission_reservation()
    session, job, _, _ = _selected_admission_publisher_fixture(selected)
    task_contexts = SimpleNamespace(
        lock_retained_submission_parents=AsyncMock(
            side_effect=RuntimeError("injected TASK database failure")
        )
    )

    with pytest.raises(RuntimeError, match="injected TASK database failure"):
        await SubmissionBundleAdmissionPublisher(
            session
        ).lock_retained_submission_parents(
            verification_job_id=job.id,
            task_contexts=task_contexts,
        )

    session.scalar.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_selected_admission_binds_unchanged_work_to_current_task_rules() -> None:
    """Bind prior content/rules before inspection, then derive unchanged input in PRE."""
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
    from app.modules.checkers.api.selected_pre_submit import derive_selected_pre_submit_default_input
    from tests.checkers.external.test_selected_pre_submit_coordination import (
        _source_reservation, _source_guard, _source_completed_execution,
    )

    original = _source_reservation()
    derived = _source_completed_execution(original)
    policies = _policies()
    lineage = original.admission_lineage
    predecessor = SubmissionCanonicalPredecessor(
        submission_id=new_record_id(), submission_version=1,
        archive_sha256=original.source.raw_sha256,
        semantic_manifest_sha256=derived.manifest_sha256,
    )
    references = SimpleNamespace(
        project_id=original.project_id, guide_version=lineage.guide_version,
        source_snapshot_id=lineage.source_snapshot_id, source_snapshot_hash=lineage.source_snapshot_sha256,
        effective_policy_id=lineage.effective_policy_id, effective_policy_hash=lineage.effective_policy_sha256,
        pre_submit_policy_id=lineage.pre_submit_policy_id, pre_submit_policy_bundle_hash=lineage.pre_submit_policy_sha256,
    )
    task = SimpleNamespace(
        contributor_id=original.actor_profile_id, task_id=original.task_id,
        assignment_id=original.assignment_id, checker_remediation_manifest_id=new_record_id(),
        revision_context=SimpleNamespace(preparation_id=new_record_id(), preparation_sha256=SHA),
        predecessor=SimpleNamespace(submission_id=predecessor.submission_id, version=1),
        locked_project_context=references,
        locked_policy=SimpleNamespace(model_dump=lambda **kwargs: {
            "locked_guide_version": lineage.guide_version, "locked_pre_submit_checker_bundle_hash": SHA,
        }),
    )
    project = SimpleNamespace(**vars(references), guide_id=lineage.guide_id,
        external_checker_policies=SimpleNamespace(value=policies.model_dump_json()))
    packet = original.default_context.packet
    metadata = SubmissionIntakeMetadata(
        task_id=task.task_id, assignment_id=task.assignment_id,
        predecessor_submission_id=predecessor.submission_id,
        summary=packet.summary, contributor_attestation=packet.contributor_attestation,
        revision_preparation_id=task.revision_context.preparation_id,
        revision_preparation_sha256=task.revision_context.preparation_sha256,
    )
    source = _source_guard(original).lock_pre_source.return_value.model_copy(update={
        "metadata_sha256": metadata.metadata_sha256(),
    })
    bound = bind_selected_pre_submit_admission(
        task=task, project=project, predecessor=predecessor,
        predecessor_rules_sha256="sha256:" + "d" * 64, predecessor_exists=True, packet=packet,
    )
    assert bound.default_context.predecessor.submission_id == predecessor.submission_id
    assert bound.default_context.predecessor_rules_sha256 == "sha256:" + "d" * 64
    assert bound.default_context.current_rules_sha256 == bound.rules_sha256
    assert bound.policy.policy_sha256 == policies.pre_submit.policy_sha256
    reservation = build_selected_pre_submit_reservation(
        source=source, metadata=metadata, task=task, project=project,
        attempt_id=new_record_id(), idempotency_key=new_record_id(), selected=bound,
        runtime_profile=original.runtime_profile,
    )
    assert "semantic_manifest_body" not in reservation.admission_lineage.canonical_body()
    assert reservation.admission_lineage.packet_sha256 == packet.sha256
    assert reservation.admission_lineage.revision_preparation_id == task.revision_context.preparation_id
    assert reservation.admission_lineage.revision_preparation_sha256 == task.revision_context.preparation_sha256
    assert reservation.admission_lineage.checker_remediation_manifest_id == task.checker_remediation_manifest_id
    assert reservation.admission_lineage.predecessor_submission_id == predecessor.submission_id
    lease = SelectedPreSubmitLeaseFacts(reservation, new_record_id(), 1, reservation.pre_deadline_at)
    default_input = derive_selected_pre_submit_default_input(
        lease, manifest_body=derived.manifest_body, manifest_sha256=derived.manifest_sha256,
        source_contracts=selected_pre_submit_source_contracts(),
    )
    from app.modules.artifacts.sources import ArtifactCommitment
    from app.modules.artifacts.api.submission_manifest import SubmissionManifest
    from app.modules.artifacts.submission_manifest import bind_submission_change

    comparison = bind_submission_change(
        commitment=ArtifactCommitment(default_input.archive_sha256, default_input.archive_byte_count,
                                      default_input.archive_media_type),
        manifest=SubmissionManifest.from_dict(derived.manifest_body, sha256=default_input.semantic_manifest_sha256),
        predecessor=predecessor, predecessor_exists=default_input.predecessor_exists,
        current_predecessor=predecessor,
    )
    assert comparison.outcome.value == "unchanged"
    assert default_input.current_rules_sha256 == bound.rules_sha256
    assert default_input.predecessor_rules_sha256 == "sha256:" + "d" * 64
    from app.modules.checkers.default_checker import _change_failure

    assert _change_failure(default_input) is None
    assert _change_failure(replace(default_input,
        predecessor_rules_sha256=default_input.current_rules_sha256)) == "submission_archive_unchanged"
