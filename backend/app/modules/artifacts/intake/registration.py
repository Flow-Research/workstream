"""Register accepted source bytes in the existing retained ART identities."""
from uuid import UUID
from sqlalchemy import func, select

from app.core.identifiers import new_record_id
from app.interfaces.artifacts import SealedSourceObservation
from app.modules.artifacts.intake.repository import IntakeCustodyConflict, SubmissionIntakeRepository
from app.modules.artifacts.models import ArtifactContent, ArtifactReplica, ArtifactStorageNamespace, SubmissionBundleAdmission
from app.modules.artifacts.repository import ArtifactRepository


async def register_accepted_source(session, row, observation, terminal):
    """Caller holds accepted operation and continuation fence; never copy/upload bytes."""
    source = SubmissionIntakeRepository._sealed_source(row)
    if type(observation) is not SealedSourceObservation or observation != SealedSourceObservation(
        source.location, source.provider_generation, source.raw_byte_count, source.sealed_upload_fence,
    ):
        raise IntakeCustodyConflict("finalization_source_observation_mismatch")
    namespace = await session.get(ArtifactStorageNamespace, row.namespace_id)
    if namespace is None or namespace.namespace_fingerprint != row.namespace_fingerprint:
        raise IntakeCustodyConflict("finalization_source_unavailable")
    content = await ArtifactRepository(session).get_or_create_content(ArtifactContent(
        id=str(new_record_id()), sha256=row.raw_sha256, byte_count=row.raw_byte_count,
        media_type="application/zip", normalized_display_name="submission.zip",
    ))
    if content.media_type != "application/zip":
        raise IntakeCustodyConflict("finalization_content_type_mismatch")
    replica = ArtifactReplica(
        id=str(new_record_id()), content_id=content.id, source_operation_id=row.id,
        storage_namespace_id=row.namespace_id, namespace_fingerprint=row.namespace_fingerprint,
        adapter=namespace.adapter, provider_profile=row.provider_profile, provider_object_ref=row.object_ref,
        verification_state="verified", availability_state="available", integrity_state="valid",
    )
    session.add(replica)
    await session.flush()
    lineage = terminal.lease.reservation.admission_lineage.canonical_body()
    admission = SubmissionBundleAdmission(
        id=str(new_record_id()), source_operation_id=row.id, durable_intent_id=None, put_attempt_id=None,
        verification_receipt_id=None, pre_submit_evidence_set_id=None,
        selected_pre_submit_run_id=row.selected_pre_submit_run_id, artifact_content_id=content.id, verified_replica_id=replica.id,
        actor_profile_id=row.actor_profile_id, identity_link_id=row.identity_link_id,
        project_id=row.project_id, task_id=row.task_id, assignment_id=row.assignment_id,
        semantic_manifest_id=str(new_record_id()), semantic_manifest_sha256=row.accepted_manifest_sha256,
        semantic_manifest_body=terminal.execution.manifest_body,
        archive_sha256=row.raw_sha256, archive_byte_count=row.raw_byte_count,
        status="ready", ready_at=await session.scalar(select(func.clock_timestamp())),
        revision_preparation_id=(UUID(row.command_metadata["revision_preparation_id"])
                                 if row.command_metadata["revision_preparation_id"] else None),
        revision_preparation_sha256=row.command_metadata["revision_preparation_sha256"],
    )
    for name in ("predecessor_submission_id", "predecessor_submission_version", "guide_id", "guide_version",
                 "source_snapshot_id", "source_snapshot_sha256", "effective_policy_id", "effective_policy_sha256",
                 "pre_submit_policy_id", "pre_submit_policy_sha256", "effective_plan_sha256",
                 "locked_policy_context_hash", "packet_sha256"):
        setattr(admission, name, lineage[name])
    admission.checker_remediation_manifest_id = (
        UUID(lineage["checker_remediation_manifest_id"]) if lineage["checker_remediation_manifest_id"] else None)
    admission.selected_rules_sha256 = lineage["rules_sha256"]
    admission.selected_post_submit_policy_sha256 = lineage["post_submit_policy_sha256"]
    admission.selected_post_submit_policy_body = lineage["post_submit_policy_body"]
    session.add(admission)
    await session.flush()
    return UUID(admission.id)
