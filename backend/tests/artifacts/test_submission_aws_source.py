"""Qualified AWS profile joins the existing T1 and selected PRE source custody."""
from datetime import timedelta

import pytest

from app.adapters.tasks import task_submission_context_port
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from tests.artifacts.test_submission_intake_custody import repository
from tests.artifacts.test_submission_intake_admission import (
    admission_intake as admission_intake, admin_access as admin_access, admit_new,
    auth_database_env as auth_database_env, clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material, signed_access as signed_access,
    record_intake_eof,
)


@pytest.mark.parametrize("admission_intake", ["aws"], indirect=True)
async def test_t1_qualified_aws_reserves_exact_source_custody(admission_intake):
    from sqlalchemy import select
    from app.modules.artifacts.intake.foreground_admission import IntakeReservationOwner, IntakeReplay
    from app.modules.artifacts.intake.models import SubmissionSourceCharge
    from app.modules.tasks.models import AuditEvent, WorkstreamTask
    f = admission_intake
    assert f.source_store_factory is None  # T1 has no provider or body capability.
    key = new_record_id()
    owner = await admit_new(f, key=key)
    assert isinstance(owner, IntakeReservationOwner)
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        charge = await session.get(SubmissionSourceCharge, row.id)
        task = await session.get(WorkstreamTask, str(f.task))
        assert row.provider_profile == "aws-s3-v1"
        assert row.namespace_id == "primary" and row.namespace_fingerprint == f.namespace.namespace_fingerprint
        assert row.state == "receiving" and row.raw_sha256 is None
        assert row.idempotency_key == str(key) and row.identity_link_id == str(f.actor.identity_link_id)
        assert charge.accounted_bytes == 1024 and charge.state == "reserved"
        assert task.active_submission_operation_id == row.id
        events = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == "submission.intake.reserve", AuditEvent.resource_id == row.id,
        )))
        assert len(events) == 1 and events[0].after_facts["allowed"] is True
    replay = await admit_new(f, key=key)
    assert isinstance(replay, IntakeReplay) and replay.operation_id == owner.operation_id


def test_unknown_source_profile_has_no_namespace_identity():
    from app.interfaces.artifacts import ArtifactStoreNamespaceIdentity
    with pytest.raises(ValueError, match="artifact provider profile is unsupported"):
        ArtifactStoreNamespaceIdentity("unqualified-v1", ())


@pytest.mark.parametrize("admission_intake", ["aws"], indirect=True)
async def test_qualified_aws_pre_source_matches_locked_sql(admission_intake):
    """A database-only source binds the qualified profile; provider I/O is separate proof."""
    import json
    from datetime import UTC, datetime
    from uuid import UUID

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app.adapters.artifacts import submission_intake_pre_source_port
    from app.adapters.projects import project_locked_policy_context_port
    from app.core.hashing import canonical_json_hash
    from app.modules.artifacts.selected_pre_submit_admission import (
        bind_selected_pre_submit_admission, build_selected_pre_submit_reservation,
    )
    from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
    from app.modules.projects.api.locked_policy import ProjectLockedPolicyContextRequest
    from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation

    f = admission_intake
    owner = await admit_new(f)
    await record_intake_eof(f, owner, b"aws-profile-source")
    async with f.factory.begin() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        source = await repository(session).seal(
            owner.operation_id, owner.lease_id, owner.generation,
            provider_generation="opaque-aws-version", pre_deadline_at=deadline,
            lease_expires_at=deadline,
        )
    async with f.factory.begin() as session:
        task = await task_submission_context_port(session).lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=f.task, assignment_id=f.assignment,
                contributor_id=f.actor.actor_profile_id, predecessor_submission_id=None,
            ),
        )
        references = task.locked_project_context
        project = await project_locked_policy_context_port(session).lock_locked_policy_context(
            ProjectLockedPolicyContextRequest(**{
                name: getattr(references, name) for name in (
                    "project_id", "guide_version", "source_snapshot_id", "source_snapshot_hash",
                    "effective_policy_id", "effective_policy_hash", "pre_submit_policy_id",
                    "pre_submit_policy_bundle_hash",
                )
            }),
        )
        guarded = await submission_intake_pre_source_port(session).lock_pre_source(
            source=source, lease_id=owner.lease_id, generation=owner.generation,
        )
        metadata = SubmissionIntakeMetadata(task_id=UUID(row.task_id), assignment_id=UUID(row.assignment_id),
                                            feedback=row.command_metadata["feedback"])
        selected = bind_selected_pre_submit_admission(
            task=task, project=project, predecessor=None, predecessor_rules_sha256=None,
            predecessor_exists=False,
            packet=SubmissionPacketView(),
        )
        request = build_selected_pre_submit_reservation(
            source=guarded, metadata=metadata, task=task, project=project,
            attempt_id=new_record_id(), idempotency_key=UUID(row.idempotency_key),
            selected=selected, runtime_profile=_source_reservation().runtime_profile,
        )
        assert request.admission_lineage.storage_scheme == "s3"
        body = request.canonical_body()
        value = {
            "source_operation_id": str(owner.operation_id), "task_id": str(f.task),
            "project_id": row.project_id, "assignment_id": str(f.assignment),
            "actor_profile_id": row.actor_profile_id, "identity_link_id": row.identity_link_id,
            "idempotency_key": row.idempotency_key, "request_json": body,
            "request_digest": canonical_json_hash(body),
            "archive_sha256": source.raw_sha256, "archive_byte_count": source.raw_byte_count,
            "policy_sha256": request.policy_sha256,
        }
    statement = text("""SELECT public.require_selected_pre_source(
        jsonb_populate_record(NULL::public.selected_pre_submit_runs, CAST(:value AS jsonb)))""")
    async with f.factory.begin() as session:
        await session.execute(statement, {"value": json.dumps(value)})
    for changed in ("storage_scheme", "provider_profile"):
        forged = json.loads(json.dumps(body))
        if changed == "storage_scheme":
            forged["admission_lineage"]["storage_scheme"] = "local"
        else:
            forged["source"]["location"]["provider_profile"] = "minio-v1"
            forged["source_sha256"] = canonical_json_hash({
                "schema_version": "workstream.sealed_submission_source.v1", **forged["source"],
            })
        with pytest.raises(DBAPIError, match="selected PRE source descriptor mismatch"):
            async with f.factory.begin() as session:
                await session.execute(statement, {"value": json.dumps(value | {
                    "request_json": forged, "request_digest": canonical_json_hash(forged),
                })})
