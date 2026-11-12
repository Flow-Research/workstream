"""Real PostgreSQL PRE source, SQL fence, and authorized execution custody."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.tasks import task_submission_context_port
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from app.modules.tasks.api.submission_context import TaskSubmissionContextUnavailable
from tests.artifacts.test_submission_intake_custody import (
    SHA, capacity_limits as capacity_limits, intake as intake,
    foreground_bytes, foreground_limits, foreground_upload,
    record_eof, repository, reserve,
)


def _assert_pre_reservation_rejects_substitution(build_values, guarded, metadata, selected):
    """Keep source/context substitution proof separate from SQL row custody."""
    from dataclasses import replace
    from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
    from app.modules.artifacts.selected_pre_submit_admission import build_selected_pre_submit_reservation
    substitutions = (
        {"metadata": metadata.model_copy(update={"summary": "substituted"})},
        {"source": guarded.model_copy(update={"actor_profile_id": new_record_id()})},
        {"source": guarded.model_copy(update={"metadata_sha256": "sha256:" + "f" * 64})},
        {"selected": replace(selected, rules_sha256="sha256:" + "f" * 64)},
        {"selected": replace(selected, default_context=replace(
            selected.default_context, packet=SubmissionPacketView("substituted", ""),
        ))},
    )
    for replacement in substitutions:
        with pytest.raises(ValueError, match="selected PRE .* context differs"):
            build_selected_pre_submit_reservation(**(build_values | replacement))
    from app.modules.artifacts.api.submission_intake import SealedSubmissionSource, SubmissionIntakePreSourceFacts
    unsupported_source = SealedSubmissionSource.model_validate(guarded.source.model_copy(update={
        "location": guarded.source.location.model_copy(update={"provider_profile": "aws-s3-v1"}),
    }))
    unsupported_facts = SubmissionIntakePreSourceFacts.model_validate(
        guarded.model_copy(update={"source": unsupported_source})
    )
    with pytest.raises(ValueError, match="selected PRE source profile is unavailable"):
        build_selected_pre_submit_reservation(**(build_values | {"source": unsupported_facts}))


def _substitute_pre_source_request(body, changed, deadline):
    """Alter one locked request fact before exercising the SQL guard."""
    from app.core.hashing import canonical_json_hash
    if changed == "source":
        body["source"]["provider_generation"] = "substituted"
        body["source_sha256"] = canonical_json_hash({
            "schema_version": "workstream.sealed_submission_source.v1", **body["source"],
        })
    elif changed == "packet":
        body["default_context"]["packet"]["summary"] = "substituted"
        body["admission_lineage"]["packet_sha256"] = canonical_json_hash(body["default_context"]["packet"])
    elif changed == "policy":
        body["policy"]["entries"] = []
    elif changed == "post_policy":
        body["admission_lineage"]["post_submit_policy_body"] = {}
    elif changed == "fence":
        body["foreground_lease_generation"] += 1
    elif changed == "deadline":
        body["pre_deadline_at"] = (deadline + timedelta(seconds=1)).isoformat()
    elif changed == "storage_scheme":
        body["admission_lineage"]["storage_scheme"] = "s3"
    elif changed == "rules":
        body["default_context"]["current_rules_sha256"] = "sha256:" + "f" * 64
        body["admission_lineage"]["rules_sha256"] = "sha256:" + "f" * 64
    elif changed == "predecessor":
        body["default_context"]["predecessor_exists"] = True
    elif changed == "predecessor_identity":
        body["admission_lineage"]["predecessor_submission_id"] = str(new_record_id())
        body["admission_lineage"]["predecessor_submission_version"] = 1
        body["admission_lineage"]["checker_remediation_manifest_id"] = str(new_record_id())


async def test_pre_source_custody_returns_exact_locked_facts(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        source = await repository(session).seal(
            operation, lease, 1, provider_generation="pre-source-generation",
            pre_deadline_at=deadline, lease_expires_at=deadline,
        )
    async with intake.factory.begin() as session:
        facts = await repository(session).lock_pre_source(source=source, lease_id=lease, generation=1)
        assert facts.source == source
        assert facts.task_id == intake.task and facts.assignment_id == intake.assignment
        assert facts.actor_profile_id == intake.actor.actor_profile_id
        assert facts.identity_link_id == intake.actor.identity_link_id
        assert facts.lease_id == lease and facts.lease_generation == 1
        assert facts.lease_expires_at == facts.pre_deadline_at == deadline
        assert facts.metadata_sha256 == row.metadata_sha256
        assert facts.locked_context_sha256 == row.locked_context_sha256


@pytest.mark.parametrize("changed", [
    "generation", "raw_sha", "raw_count", "namespace", "profile", "lease", "fence",
    "cleared_pointer", "foreign_pointer", "expired", "terminal", "unsealed",
])
async def test_pre_source_custody_rejects_substitution_or_stale_owner(intake, changed):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        if changed == "unsealed":
            from app.modules.artifacts.api.submission_intake import SealedSubmissionSource, SubmissionSourceLocation
            source = SealedSubmissionSource(
                location=SubmissionSourceLocation(
                    operation_id=operation, namespace_id=row.namespace_id,
                    namespace_fingerprint=row.namespace_fingerprint, provider_profile=row.provider_profile,
                ), provider_generation="pre-source-generation", raw_sha256=SHA,
                raw_byte_count=100, sealed_upload_fence=1,
            )
        else:
            source = await repository(session).seal(
                operation, lease, 1, provider_generation="pre-source-generation",
                pre_deadline_at=deadline, lease_expires_at=deadline,
            )
    values = source.model_dump(mode="python")
    if changed == "generation":
        values["provider_generation"] = "another-generation"
    elif changed == "raw_sha":
        values["raw_sha256"] = "sha256:" + "b" * 64
    elif changed == "raw_count":
        values["raw_byte_count"] += 1
    elif changed == "namespace":
        values["location"]["namespace_fingerprint"] = "sha256:" + "b" * 64
    elif changed == "profile":
        values["location"]["provider_profile"] = "unqualified-profile"
    supplied = type(source).model_validate(values)
    async with intake.factory() as session:
        await session.begin()
        try:
            if changed in {"cleared_pointer", "foreign_pointer"}:
                # Deferrable SQL constraints do not replace the in-root owner
                # check before another participant can consume custody.
                await session.execute(text(
                    "UPDATE workstream_tasks SET active_submission_operation_id=:active WHERE id=:task"
                ), {"active": None if changed == "cleared_pointer" else new_record_id(), "task": intake.task})
            elif changed == "expired":
                await session.execute(text(
                    "UPDATE submission_intake_operations SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"
                ), {"id": operation})
            elif changed == "terminal":
                await repository(session).terminalize(operation, lease, 1, state="rejected", failure_code="pre_failed")
            with pytest.raises((IntakeCustodyConflict, TaskSubmissionContextUnavailable)):
                await repository(session).lock_pre_source(
                    source=supplied, lease_id=new_record_id() if changed == "lease" else lease,
                    generation=2 if changed == "fence" else 1,
                )
        finally:
            await session.rollback()


@pytest.mark.parametrize("intake", [True], indirect=True)
@pytest.mark.parametrize("changed", [None, "source", "packet", "policy", "post_policy", "fence", "deadline", "actor", "rules", "predecessor", "predecessor_identity", "storage_scheme"])
async def test_selected_pre_sql_requires_exact_live_source(intake, changed):
    """Exercise the SQL source participant; not full PRE execution or T4 proof."""
    from app.core.hashing import canonical_json_hash
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation
    from app.adapters.projects import project_locked_policy_context_port
    from app.adapters.artifacts import submission_intake_pre_source_port
    from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest
    from app.modules.projects.api.locked_policy import ProjectLockedPolicyContextRequest
    from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
    from app.modules.artifacts.selected_pre_submit_admission import (
        bind_selected_pre_submit_admission, build_selected_pre_submit_reservation,
    )

    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        source = await repository(session).seal(
            operation, lease, 1, provider_generation="pre-source-generation",
            pre_deadline_at=deadline, lease_expires_at=deadline,
        )
    async with intake.factory.begin() as session:
        task = await task_submission_context_port(session).lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=intake.task, assignment_id=intake.assignment,
                contributor_id=intake.actor.actor_profile_id, predecessor_submission_id=None,
            )
        )
        references = task.locked_project_context
        project = await project_locked_policy_context_port(session).lock_locked_policy_context(
            ProjectLockedPolicyContextRequest(**{
                name: getattr(references, name) for name in (
                    "project_id", "guide_version", "source_snapshot_id", "source_snapshot_hash",
                    "effective_policy_id", "effective_policy_hash", "pre_submit_policy_id",
                    "pre_submit_policy_bundle_hash",
                )
            })
        )
        guarded = await submission_intake_pre_source_port(session).lock_pre_source(
            source=source, lease_id=lease, generation=1,
        )
        metadata = SubmissionIntakeMetadata.model_validate_json(json.dumps(row.command_metadata))
        selected = bind_selected_pre_submit_admission(
            task=task, project=project, predecessor=None, predecessor_rules_sha256=None,
            predecessor_exists=False,
            packet=SubmissionPacketView(metadata.summary, metadata.contributor_attestation),
        )
        build_values = dict(
            source=guarded, metadata=metadata, task=task, project=project,
            attempt_id=new_record_id(), idempotency_key=UUID(row.idempotency_key),
            selected=selected, runtime_profile=_source_reservation().runtime_profile,
        )
        request = build_selected_pre_submit_reservation(**build_values)
        assert request.admission_lineage.storage_scheme == "local"
        if changed is None:
            _assert_pre_reservation_rejects_substitution(build_values, guarded, metadata, selected)
        body = request.canonical_body()
        _substitute_pre_source_request(body, changed, deadline)
        value = {
            "source_operation_id": str(operation), "task_id": str(intake.task),
            "project_id": row.project_id, "assignment_id": str(intake.assignment),
            "actor_profile_id": str(new_record_id()) if changed == "actor" else row.actor_profile_id,
            "identity_link_id": row.identity_link_id, "idempotency_key": row.idempotency_key,
            "request_json": body, "archive_sha256": source.raw_sha256,
            "archive_byte_count": source.raw_byte_count, "policy_sha256": request.policy_sha256,
        }
    async with intake.factory.begin() as session:
        statement = text("""SELECT public.require_selected_pre_source(
            jsonb_populate_record(NULL::public.selected_pre_submit_runs, CAST(:value AS jsonb)))""")
        if changed is None:
            await session.execute(statement, {"value": json.dumps(value)})
        else:
            with pytest.raises(DBAPIError, match="selected PRE"):
                await session.execute(statement, {"value": json.dumps(value)})
            await session.rollback()
    from app.modules.checkers.models import SelectedPreSubmitRun
    async with intake.factory.begin() as session:
        session.add(SelectedPreSubmitRun(
            id=str(request.attempt_id), source_operation_id=str(operation),
            actor_profile_id=value["actor_profile_id"], identity_link_id=row.identity_link_id,
            project_id=row.project_id, task_id=str(intake.task), assignment_id=str(intake.assignment),
            idempotency_key=row.idempotency_key, request_json=body,
            request_digest=canonical_json_hash(body), policy_sha256=request.policy_sha256,
            default_behavior_sha256=request.default_behavior_sha256,
            archive_sha256=source.raw_sha256, archive_byte_count=source.raw_byte_count,
            execution_budget_ms=request.execution_budget_ms, status="queued", lease_generation=0,
        ))
        if changed is None:
            await session.flush()
        else:
            with pytest.raises(DBAPIError, match="selected PRE"):
                await session.flush()
            await session.rollback()
    if changed is None:
        await _assert_pre_terminal_guards(intake, request)


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
async def test_selected_pre_sql_audit_digest_keeps_versioned_custody(isolated_database_env, version):
    from app.core.hashing import canonical_json_hash
    from tests.checkers.external.test_selected_pre_submit_coordination import _retained_v1, _source_reservation

    retained = _retained_v1()
    request = retained["request"] if version == "v1" else _source_reservation().canonical_body()
    terminal = dict(retained["terminal"])
    if version == "v3":
        terminal["schema_version"] = "workstream.selected_pre_submit_terminal.v3"
        # Digest parity is independent of receipt validation, tested by the write guards.
        terminal["invocation_receipt"] = {"provider_invocation_id": "digest-sensitivity-probe"}
    execute = {
        "schema_version": f"workstream.selected_pre_submit_execute.{'v1' if version == 'v1' else 'v2'}",
        "reservation": request, "lease_id": terminal["lease_id"],
        "lease_generation": terminal["lease_generation"], "lease_expires_at": terminal["lease_expires_at"],
    }
    expected_execute = canonical_json_hash(execute)
    expected_finalize = canonical_json_hash({
        "schema_version": f"workstream.selected_pre_submit_finalize.{version}",
        "execute_facts_digest": expected_execute,
        "execution": terminal["execution"],
        "infrastructure_failure_code": terminal["infrastructure_failure_code"],
    } | ({"invocation_receipt": terminal["invocation_receipt"]} if version == "v3" else {}))
    value = {
        "request_json": request, "lease_id": execute["lease_id"],
        "lease_generation": execute["lease_generation"], "lease_expires_at": execute["lease_expires_at"],
        "terminal_json": terminal,
    }
    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.connect() as connection:
            for phase, expected in (("execute", expected_execute), ("finalize", expected_finalize)):
                actual = await connection.scalar(text("""SELECT public.selected_pre_submit_facts_digest(
                    jsonb_populate_record(NULL::public.selected_pre_submit_runs, CAST(:value AS jsonb)),
                    :phase)"""), {"value": json.dumps(value), "phase": phase})
                assert actual == expected
    finally:
        await engine.dispose()


async def _assert_receipt_migration_refuses_inflight(intake, request, expected_status):
    """Run the actual migration entry before its DDL over an existing live run."""
    from pathlib import Path
    import runpy
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    def upgrade(connection):
        migration = runpy.run_path(str(Path(__file__).resolve().parents[2] /
                                      "alembic/versions/0072_pre_invocation_receipts.py"))
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()

    async with intake.factory.begin() as session:
        before = await session.scalar(text("SELECT to_jsonb(r) FROM selected_pre_submit_runs r WHERE id=:id"),
                                      {"id": request.attempt_id})
        assert before["status"] == expected_status
        with pytest.raises(DBAPIError, match="drain source PRE runs"):
            async with session.begin_nested():
                connection = await session.connection()
                await connection.run_sync(upgrade)
        after = await session.scalar(text("SELECT to_jsonb(r) FROM selected_pre_submit_runs r WHERE id=:id"),
                                     {"id": request.attempt_id})
        assert after == before


async def _assert_pre_terminal_guards(intake, request):
    """Claim with real AUTH, reject rebound terminal updates, then finalize once."""
    from app.modules.actors.api import ServiceIdentity
    from tests.checkers.execution.support import provision_post_submit_service
    from app.adapters.auth import selected_pre_submit_authority
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.core.hashing import canonical_json_hash
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitFinalizeFacts, SelectedPreSubmitTerminalFacts
    from app.modules.checkers.models import SelectedPreSubmitRun

    await provision_post_submit_service(intake.factory, ServiceIdentity.CHECKER_PRE_SUBMIT)
    await _assert_receipt_migration_refuses_inflight(intake, request, "queued")
    async with intake.factory.begin() as session:
        async with selected_pre_submit_authority(session).prepare_execution(request) as authority:
            lease = await selected_pre_submit_coordinator(session).claim(
                run_id=request.attempt_id, facts=request, authority=authority,
            )
    await _assert_receipt_migration_refuses_inflight(intake, request, "running")
    finalize = SelectedPreSubmitFinalizeFacts(
        lease=lease, execution=None, invocation_receipt=None, infrastructure_failure_code="capacity_exceeded",
    )
    for changed in ("lease_id", "lease_expires_at", "started_at", "execute_evidence_id",
                    "schema_version", "reservation", "request_digest", "outcome", "terminal_digest", "extra"):
        async with intake.factory.begin() as session:
            async with selected_pre_submit_authority(session).prepare_finalization(finalize) as authority:
                evidence = await authority.consume(finalize)
                row = await session.get(SelectedPreSubmitRun, str(request.attempt_id))
                now = await session.scalar(text("select clock_timestamp()"))
                terminal = SelectedPreSubmitTerminalFacts(
                    lease=lease, outcome="infrastructure_failed", execution=None, invocation_receipt=None,
                    infrastructure_failure_code="capacity_exceeded", queued_at=row.queued_at,
                    started_at=row.started_at, completed_at=now,
                ).canonical_body()
                values = dict(
                    id=request.attempt_id, lease_id=lease.lease_id,
                    lease_expires_at=lease.lease_expires_at, started_at=row.started_at,
                    execute_evidence_id=UUID(row.execute_evidence_id), completed_at=now,
                    finalize_evidence_id=evidence.evidence_id,
                )
                claim_change = changed in {"lease_id", "lease_expires_at", "started_at", "execute_evidence_id"}
                if changed in {"lease_id", "execute_evidence_id"}:
                    values[changed] = new_record_id()
                    if changed == "lease_id":
                        terminal[changed] = str(values[changed])
                elif changed in {"lease_expires_at", "started_at"}:
                    values[changed] -= timedelta(microseconds=1)
                    terminal[changed] = values[changed].isoformat()
                elif changed == "schema_version":
                    terminal[changed] = "workstream.selected_pre_submit_terminal.v1"
                elif changed == "reservation":
                    terminal[changed] = terminal[changed] | {"metadata_sha256": "sha256:" + "f" * 64}
                elif changed == "request_digest":
                    terminal[changed] = "sha256:" + "f" * 64
                elif changed == "outcome":
                    terminal[changed] = "completed"
                elif changed == "extra":
                    terminal["unexpected"] = True
                values["terminal_json"] = json.dumps(terminal)
                values["terminal_digest"] = ("sha256:" + "f" * 64 if changed == "terminal_digest"
                                             else canonical_json_hash(terminal))
                message = "committed claim is immutable" if claim_change else "terminal binding mismatch"
                with pytest.raises(DBAPIError, match=message):
                    await session.execute(text("""UPDATE selected_pre_submit_runs SET
                        status='infrastructure_failed', lease_id=:lease_id, lease_expires_at=:lease_expires_at,
                        started_at=:started_at, execute_evidence_id=:execute_evidence_id,
                        completed_at=:completed_at, finalize_evidence_id=:finalize_evidence_id,
                        terminal_json=CAST(:terminal_json AS jsonb), terminal_digest=:terminal_digest
                        WHERE id=:id"""), values)
                await session.rollback()
    async with intake.factory.begin() as session:
        async with selected_pre_submit_authority(session).prepare_finalization(finalize) as authority:
            completion = await selected_pre_submit_coordinator(session).finalize(
                run_id=request.attempt_id, lease=lease, authority=authority,
                execution=None, invocation_receipt=None, infrastructure_failure_code="capacity_exceeded",
            )
            assert completion.terminal.outcome == "infrastructure_failed"
            assert completion.capability is None


async def _assert_stored_receipt(factory, run_id, terminal):
    from app.modules.checkers.models import SelectedPreSubmitRun
    async with factory() as verify:
        stored = await verify.get(SelectedPreSubmitRun, str(run_id))
        assert stored.terminal_json == terminal.canonical_body()
        assert stored.terminal_digest == terminal.terminal_digest
        assert stored.finalize_evidence_id is not None


def _source_runtime(payload, tmp_path, runtime_outcome):
    """Real intake worker with an explicit simulated project reply or capacity failure."""
    from contextlib import aclosing
    from app.interfaces.external_services import ExternalServiceAdapterIdentity
    from app.modules.checkers.api.selected_pre_submit import (
        SelectedPreSubmitInfrastructureUnavailable, SelectedPreSubmitInvocationResult,
    )
    from tests.checkers.external.test_pre_invocation import receipt_body
    from tests.test_trusted_intake import _pre_worker, _read

    runtime_errors = []
    class SourceRuntime:
        @property
        def pre_runtime_provider(self):
            return "smolvm"

        identity = ExternalServiceAdapterIdentity(capability_key="external_checker_execution", provider_key="unix_socket")
        async def execute_pre(self, lease, grant):
            try:
                return await self.run(lease, grant)
            except Exception:
                if runtime_outcome == "completed":
                    import traceback
                    runtime_errors.append(traceback.format_exc())
                raise

        async def run(self, lease, grant):
            async with aclosing(grant.open_source(lease=lease)) as reader:
                assert b"".join([chunk async for chunk in reader]) == payload
            if runtime_outcome == "received_failure":
                body = receipt_body(lease, outcome="infrastructure_failure", reason="capacity_exceeded")
                body["cleanup"]["disposition"] = "pending"
                return SelectedPreSubmitInvocationResult.from_canonical_body(body | {"execution": None})
            if runtime_outcome == "completed":
                worker, output, reply, actual_lease = _pre_worker(
                    tmp_path, payload, lease=lease,
                    isolation_override={"runtime": "smolvm", "isolation_mode": "smol-microvm"},
                )
                assert actual_lease is lease
                worker.run()
                output.seek(0)
                project_frame, completion = _read(output), _read(output)
                assert project_frame["operation"] == "project" and reply.calls == 1
                assert completion["operation"] == "completed" and output.read() == b""
                response = receipt_body(lease) | {"execution": completion["payload"]}
                return SelectedPreSubmitInvocationResult.from_canonical_body(response)
            raise SelectedPreSubmitInfrastructureUnavailable("capacity_exceeded")
    return SourceRuntime(), runtime_errors


@pytest.mark.parametrize("intake", [True], indirect=True)
@pytest.mark.parametrize("materializer_enabled", [True, False])
@pytest.mark.parametrize("runtime_outcome", ["transport_failure", "completed", "received_failure"])
async def test_source_pre_execution_uses_committed_authorized_local_read(intake, materializer_enabled, runtime_outcome, tmp_path):
    """Real source/SQL/AUTH composition with a worker and simulated project runtime."""
    from contextlib import aclosing
    from app.adapters.artifacts import submission_intake_pre_source_port
    from app.adapters.auth import selected_pre_submit_authority
    from app.adapters.checkers import selected_pre_submit_coordinator, SelectedPreSubmitCheckerExecutionAdapter
    from app.adapters.projects import project_locked_policy_context_port
    from app.modules.actors.api import ServiceIdentity
    from app.modules.artifacts.authorization import PreparedPreSubmitMaterializationAuthorization
    from app.modules.artifacts.selected_pre_submit_admission import (
        bind_selected_pre_submit_admission, build_selected_pre_submit_reservation,
    )
    from app.modules.artifacts.selected_pre_submit_execution import (
        SelectedPreSubmitSourceReads, SelectedPreSubmitExecutionService,
    )
    from app.modules.authorization.catalogue import ActionId
    from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
    from app.modules.projects.api.locked_policy import ProjectLockedPolicyContextRequest
    from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest
    from tests.artifact_store_helpers import initialize_local_store
    from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer
    from tests.checkers.execution.support import provision_post_submit_service
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation

    from tests.test_trusted_intake import _archive

    payload = _archive() if runtime_outcome == "completed" else b"original source bytes"
    async def upload_bytes():
        yield payload

    store = initialize_local_store(root=intake.durable_root, buffer_bytes=256 * 1024)
    async with intake.factory.begin() as session:
        row = await reserve(intake, session, with_upload=False)
        operation, foreground_lease = UUID(row.id), UUID(row.lease_id)
        metadata = SubmissionIntakeMetadata.model_validate_json(json.dumps(row.command_metadata))
        key = UUID(row.idempotency_key)
    source = await foreground_upload(intake, store).receive(
        operation, foreground_lease, 1, upload_bytes(), **foreground_limits(),
    )
    async with intake.factory.begin() as session:
        task = await task_submission_context_port(session).lock_submission_context(
            TaskSubmissionContextRequest(intake.task, intake.assignment, intake.actor.actor_profile_id, None),
        )
        references = task.locked_project_context
        project = await project_locked_policy_context_port(session).lock_locked_policy_context(
            ProjectLockedPolicyContextRequest(**{name: getattr(references, name) for name in (
                "project_id", "guide_version", "source_snapshot_id", "source_snapshot_hash",
                "effective_policy_id", "effective_policy_hash", "pre_submit_policy_id", "pre_submit_policy_bundle_hash",
            )}),
        )
        custody = await submission_intake_pre_source_port(session).lock_pre_source(
            source=source, lease_id=foreground_lease, generation=1,
        )
        selected = bind_selected_pre_submit_admission(
            task=task, project=project, predecessor=None, predecessor_rules_sha256=None,
            predecessor_exists=False, packet=SubmissionPacketView(metadata.summary, metadata.contributor_attestation),
        )
        request = build_selected_pre_submit_reservation(
            source=custody, metadata=metadata, task=task, project=project,
            attempt_id=new_record_id(), idempotency_key=key, selected=selected,
            runtime_profile=_source_reservation().runtime_profile,
        )
        await selected_pre_submit_coordinator(session).reserve(request)
    await provision_post_submit_service(intake.factory, ServiceIdentity.CHECKER_PRE_SUBMIT)
    if materializer_enabled:
        await _seed_materializer(intake.factory)
    observed = []
    async with intake.factory() as session:
        class ObservedStore:
            def open_source(self, actual, *, maximum_chunk_bytes):
                assert actual == source and not session.in_transaction()
                assert maximum_chunk_bytes == 64 * 1024
                async def chunks():
                    async with intake.factory.begin() as probe:
                        # Independent NOWAIT locks prove provider reads do not
                        # retain TASK or intake locks from either AUTH root.
                        for sql, params in (
                            ("SELECT id FROM workstream_tasks WHERE id=:id FOR UPDATE NOWAIT", {"id": intake.task}),
                            ("SELECT id FROM submission_intake_operations WHERE id=:id FOR UPDATE NOWAIT", {"id": operation}),
                        ):
                            assert (await probe.execute(text(sql), params)).one()
                        assert await probe.scalar(text(
                            "SELECT count(*) FROM audit_events WHERE action_id=:action AND resource_id=:id"
                        ), {"action": ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE.value, "id": str(operation)}) == 1
                    async with aclosing(store.open_source(actual, maximum_chunk_bytes=maximum_chunk_bytes)) as reader:
                        async for chunk in reader:
                            observed.append(chunk)
                            yield chunk
                return chunks()
        runtime, runtime_errors = _source_runtime(payload, tmp_path, runtime_outcome)
        authority = PreparedPreSubmitMaterializationAuthorization(
            session, request_id=new_record_id(), correlation_id=new_record_id(),
        )
        service = SelectedPreSubmitExecutionService(
            session=session, coordinator=selected_pre_submit_coordinator(session),
            authority=selected_pre_submit_authority(session),
            source_reads=SelectedPreSubmitSourceReads(
                session=session, sources=submission_intake_pre_source_port(session),
                authority=authority, store=ObservedStore(),
            ), execution=SelectedPreSubmitCheckerExecutionAdapter(external_execution=runtime),
        )
        result = await service.execute(reservation=request)
        assert not runtime_errors, "\n".join(runtime_errors)
        if runtime_outcome == "completed" and materializer_enabled:
            assert result.terminal.outcome == "completed", result.terminal.infrastructure_failure_code
            # Source receipt retention does not issue the removed prepared-bundle handoff.
            assert result.capability is None
            assert result.terminal.execution.eligible
            assert result.terminal.invocation_receipt is not None
            await _assert_stored_receipt(intake.factory, request.attempt_id, result.terminal)
        else:
            assert result.capability is None and result.terminal.outcome == "infrastructure_failed"
            assert result.terminal.infrastructure_failure_code == (
                "capacity_exceeded" if materializer_enabled else "material_unavailable"
            )
            if runtime_outcome == "received_failure" and materializer_enabled:
                assert result.terminal.invocation_receipt.cleanup.disposition == "pending"
                await _assert_stored_receipt(intake.factory, request.attempt_id, result.terminal)
    assert bool(observed) == materializer_enabled
    store.close()


@pytest.mark.parametrize("changed", [None, "source", "fence", "profile", "outcome", "timing", "cleanup", "extra", "missing"])
async def test_selected_pre_sql_validates_received_failure_receipt(isolated_database_env, changed):
    """Exercise the SQL receipt guard directly; this is not a real worker proof."""
    from app.core.identifiers import new_record_id
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitLeaseFacts
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation
    from tests.checkers.external.test_pre_invocation import receipt_body

    request = _source_reservation()
    lease = SelectedPreSubmitLeaseFacts(request, new_record_id(), 1, request.pre_deadline_at)
    receipt = receipt_body(lease, outcome="infrastructure_failure", reason="capacity_exceeded")
    if changed == "source":
        receipt["invocation"]["source_sha256"] = "sha256:" + "f" * 64
    elif changed == "fence":
        receipt["invocation"]["lease_generation"] = 2
    elif changed == "profile":
        receipt["runtime"]["profile"]["aggregate_deadline_ms"] += 1
    elif changed == "outcome":
        receipt["outcome"] = None
    elif changed == "timing":
        receipt["timings_ms"]["total"] = 9
    elif changed == "cleanup":
        receipt["cleanup"]["obligation_id"] = "other-invocation"
    elif changed == "extra":
        receipt["cleanup"]["host_path"] = "/private"
    terminal = {"invocation_receipt": receipt, "infrastructure_failure_code": "capacity_exceeded"}
    if changed == "missing":
        terminal.pop("invocation_receipt")
    value = {
        "id": str(request.attempt_id), "source_operation_id": str(request.source.location.operation_id),
        "request_json": request.canonical_body(), "request_digest": request.request_digest,
        "lease_id": str(lease.lease_id), "lease_generation": lease.lease_generation,
        "status": "infrastructure_failed", "terminal_json": terminal,
    }
    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.connect() as connection:
            async def invoke():
                await connection.execute(text("""SELECT public.require_selected_pre_invocation(
                    jsonb_populate_record(NULL::public.selected_pre_submit_runs, CAST(:value AS jsonb)))"""),
                    {"value": json.dumps(value)})
            if changed is None:
                await invoke()
            else:
                with pytest.raises(DBAPIError, match="selected PRE invocation"):
                    await invoke()
    finally:
        await engine.dispose()
