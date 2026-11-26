"""Proof of the live 0091 writer handing its accepted command to the 0092 reader.

Run this test from a 0091 checkout with the 0092 candidate backend path supplied
in WORKSTREAM_SUBMISSION_FEEDBACK_CANDIDATE. The candidate process uses the same
isolated PostgreSQL database and private local source as the predecessor.
"""

import asyncio
import base64
from dataclasses import asdict
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata, SubmissionSourceCapacityLimits
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.authorization.runtime import HumanAuthorizationContext
from tests.artifacts.test_submission_foreground_command import configure_source_http
from tests.artifacts.test_submission_intake_admission import (
    admin_access as admin_access,
    admission_intake as admission_intake,
    admit_new,
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    intake_admission,
    rsa_signing_material as rsa_signing_material,
    signed_access as signed_access,
)
from tests.retained_material_fixtures import finalize_retained_intake
from tests.test_artifact_admission import _local_store, _settings
from tests.test_trusted_intake import _archive

_PREDECESSOR = "0091_qualified_aws_source"
_CANDIDATE = "0092_submission_feedback"
_CANDIDATE_ENV = "WORKSTREAM_SUBMISSION_FEEDBACK_CANDIDATE"
_FROZEN = text("""
    SELECT o.command_metadata,o.metadata_sha256,o.accepted_context_sha256,o.acceptance_receipt_sha256,
           r.request_digest,r.terminal_digest,r.request_json->'default_context'->'packet' AS packet
    FROM submission_intake_operations o
    JOIN selected_pre_submit_runs r ON r.id=o.selected_pre_submit_run_id WHERE o.id=:id
""")
_AUDIT_CONSTRAINT = text("""
    SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint
    WHERE conrelid='public.audit_events'::regclass AND conname='ck_audit_events_authorization_action_evidence'
""")
_ROW_IDENTITY = text("""
    SELECT ctid::text,xmin::text FROM submission_intake_operations WHERE id=:id
""")


def _candidate_command(candidate, args):
    env = os.environ | {"PYTHONPATH": os.pathsep.join((str(candidate), str(candidate / "tests")))}
    return subprocess.run([sys.executable, *args], cwd=candidate, env=env,
                          capture_output=True, text=True, check=False)


@pytest.mark.postgres_schema_contract
@pytest.mark.skipif(not os.environ.get(_CANDIDATE_ENV), reason="requires the predecessor and candidate checkouts")
async def test_feedback_upgrade_preserves_accepted_operation(admission_intake, tmp_path, monkeypatch):  # noqa: F811
    candidate = Path(os.environ[_CANDIDATE_ENV]).resolve(strict=True)
    f = admission_intake
    async with f.factory() as session:
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == _PREDECESSOR
    route = f"/api/v1/tasks/{f.task}/submissions"
    headers = f.access.target.headers | {
        "Content-Type": "application/zip", "X-Task-Assignment-Id": str(f.assignment),
    }
    malformed = _archive("../escape")
    client, _, errors, rejected_calls = await configure_source_http(
        f.factory, f.access.signed.client, tmp_path, monkeypatch, malformed, "rejected",
    )
    nonempty_key = str(new_record_id())
    rejected = await client.post(route, headers=headers | {
        "Idempotency-Key": nonempty_key, "X-Submission-Summary": "Original retained text",
    }, content=malformed)
    assert rejected.status_code == 422 and len(rejected_calls) == 1 and not errors, rejected.text

    f.admission._capacity = SubmissionSourceCapacityLimits(maximum_total_bytes=4 * 1024**2)
    receiving = await admit_new(f)
    upgrade = ["-m", "alembic", "upgrade", _CANDIDATE]
    refused = await asyncio.to_thread(_candidate_command, candidate, upgrade)
    assert refused.returncode != 0
    assert "wait for active submission uploads and PRE checks to end" in refused.stderr, refused.stderr
    async with f.factory() as session:
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == _PREDECESSOR
        assert await session.scalar(text("""
            SELECT count(*) FROM information_schema.columns
            WHERE table_schema='public' AND table_name='submissions' AND column_name='feedback'
        """)) == 0
    assert await f.admission.finish(receiving, state="failed", failure_code="submission_upload_timeout")

    payload = _archive()
    client, _, errors, calls = await configure_source_http(
        f.factory, client, tmp_path, monkeypatch, payload, "completed",
    )
    key = str(new_record_id())
    accepted = await client.post(route, headers=headers | {"Idempotency-Key": key}, content=payload)
    assert accepted.status_code == 202 and len(calls) == 1 and not errors, accepted.text
    receipt = accepted.json()
    operation = UUID(receipt["operation_id"])
    async with f.factory() as session:
        frozen = (await session.execute(_FROZEN, {"id": operation})).mappings().one()
        assert frozen["packet"] == {"summary": "", "contributor_attestation": ""}
        row_identity = (await session.execute(_ROW_IDENTITY, {"id": operation})).one()
        constraint = await session.scalar(_AUDIT_CONSTRAINT)
    seed = tmp_path / "upgrade-seed.json"
    seed.write_text(json.dumps({
        "actor": f.actor.model_dump(mode="json"), "task": str(f.task), "assignment": str(f.assignment),
        "key": key, "nonempty_key": nonempty_key, "receipt": receipt, "namespace": asdict(f.namespace),
        "frozen": dict(frozen), "data": base64.b64encode(payload).decode(), "directory": str(tmp_path),
        "row_identity": list(row_identity), "audit_constraint": constraint,
    }))
    migrated = await asyncio.to_thread(_candidate_command, candidate, upgrade)
    assert migrated.returncode == 0, migrated.stderr
    checked = await asyncio.to_thread(_candidate_command, candidate, [str(Path(__file__).resolve()), str(seed)])
    assert checked.returncode == 0, checked.stderr
    assert f"{_CANDIDATE}: accepted receipt, packet digest and one finalization verified" in checked.stdout


async def _verify_candidate(seed_path):
    from app.modules.checkers.api.pre_submit_material import SubmissionPacketView

    seed = json.loads(seed_path.read_text())
    context = HumanAuthorizationContext.model_validate_json(json.dumps(seed["actor"]))
    settings = _settings(Path(seed["directory"]))
    namespace = ArtifactStorageNamespaceSpec(**seed["namespace"])
    engine = create_async_engine(os.environ["WORKSTREAM_DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bootstrap, store = _local_store(settings, namespace)
    operation = UUID(seed["receipt"]["operation_id"])
    try:
        async with factory() as session:
            assert await session.scalar(text("SELECT version_num FROM alembic_version")) == _CANDIDATE
            assert list((await session.execute(_ROW_IDENTITY, {"id": operation})).one()) == seed["row_identity"]
            constraint = await session.scalar(_AUDIT_CONSTRAINT)
        for action in ("task.assignment.read", "project.contributor_guide.read"):
            added = (f" OR (((action_id)::text = '{action}'::text) AND "
                     "((permission_id)::text = 'submission.read_own'::text))")
            assert constraint.count(added) == 2
            constraint = constraint.replace(added, "")
        assert constraint == seed["audit_constraint"]
        metadata = SubmissionIntakeMetadata(task_id=UUID(seed["task"]), assignment_id=UUID(seed["assignment"]))
        admission = intake_admission(factory, context, namespace)

        async def body():
            yield base64.b64decode(seed["data"])

        replay = await admission.replay(
            metadata, body(), actor_id=context.actor_profile_id, idempotency_key=UUID(seed["key"]),
            declared_raw_bytes=None, idle_timeout_seconds=1, replay_duration=timedelta(seconds=30),
        )
        assert replay.acceptance_receipt == dict(seed["receipt"], replayed=True)
        with pytest.raises(IntakeCustodyConflict, match="^submission_idempotency_conflict$"):
            await admission.admit(
                metadata, actor_id=context.actor_profile_id, identity_link_id=context.identity_link_id,
                idempotency_key=UUID(seed["nonempty_key"]), declared_raw_bytes=None,
            )
        submission_id = await finalize_retained_intake(factory, SimpleNamespace(
            operation_id=operation, store=store, settings=settings, namespace=namespace,
        ))
        async with factory() as session:
            frozen = (await session.execute(_FROZEN, {"id": operation})).mappings().one()
            assert dict(frozen) == seed["frozen"]
            stored = (await session.execute(text("""
                SELECT s.summary,s.worker_attestation,s.feedback,
                       public.submission_dispatch_valid(d),a.packet_sha256
                FROM submissions s JOIN submission_dispatches d ON d.submission_id=s.id
                JOIN submission_bundle_admissions a ON a.id=s.submission_bundle_admission_id
                WHERE s.id=:id
            """), {"id": UUID(submission_id)})).one()
            assert stored == ("", "", None, True, SubmissionPacketView("", "").sha256)
            assert await session.scalar(text("SELECT count(*) FROM selected_pre_submit_runs")) == 2
            assert await session.scalar(text("SELECT count(*) FROM submissions")) == 1
        print(f"{_CANDIDATE}: accepted receipt, packet digest and one finalization verified")
    finally:
        bootstrap.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_verify_candidate(Path(sys.argv[1])))
