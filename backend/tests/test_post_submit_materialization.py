"""Verified exact Submission input, async lifetime and fail-closed composition."""

import asyncio
import json
import pickle
from dataclasses import asdict

import pytest
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.checkers.api.materialization import (
    PostSubmissionMaterializationUnavailable, PostSubmissionMaterializationFailure,
)
from tests.checkers.post_submit.support import change_request
from tests.checkers.execution.support import selected_result as result
from tests.post_submit_materialization_helpers import material_fixture
from tests.checkers.execution.support import material_execution, service_link_state
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.preparation import ArtifactScratchIntegrityError
from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry,
    PostSubmitExternalCheckerIdentity,
    external_checker_json_hash,
    make_external_checker_execution_request,
)
from tests.checkers.external.support import registry_entry


class Consumer:
    def __init__(self, files):
        self.files, self.view, self.calls = files, None, 0
        self.entered, self.release = asyncio.Event(), None
        self.failure = None

    async def evaluate(self, request, view):
        self.calls += 1
        self.view = view
        self.entered.set()
        await asyncio.sleep(0)  # The view must remain usable across real async work.
        assert {e.normalized_path for e in view.entries if e.entry_type == "file"} == set(self.files)
        flags = {entry.normalized_path: entry.executable for entry in view.entries}
        assert flags["run.sh"] is True
        assert flags["notes.txt"] is False
        for path, data in self.files.items():
            assert view.read_file(path, maximum_bytes=len(data)) == data
        if self.release is not None:
            await self.release.wait()
        if self.failure:
            raise self.failure
        return result(request)


class ExternalGrantConsumer(Consumer):
    """Exercise the real POST lineage through ART's callback-scoped grant."""

    def __init__(self, files, execution, scratch):
        super().__init__(files)
        self.execution = execution
        self.scratch = scratch
        self.grant_path = None
        self.manifest = None

    def external_request(self, material, *, identity=None, terminal=False):
        source, lease = self.execution.request, self.execution.lease
        reservation = lease.reservation
        identity = identity or PostSubmitExternalCheckerIdentity(
            project_id=source.project_id,
            task_id=source.task_id,
            assignment_id=source.assignment_id,
            submission_id=source.submission_id,
            submission_version=source.submission_version,
            evaluation_request_id=source.evaluation_request_id,
            evaluation_request_digest=source.request_sha256,
            evaluation_generation=source.evaluation_generation,
            attempt_id=reservation.attempt_id,
            result_id=reservation.result_id,
            lease_id=lease.lease_id,
            lease_generation=lease.lease_generation,
            lease_expires_at=lease.expires_at,
        )
        registry = registry_entry("post_submit")
        if terminal:
            values = registry.model_dump(mode="json")
            values["capability_id"] = "workstream.terminal_benchmark_project"
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
            values["entry_digest"] = external_checker_json_hash(spec)
            registry = ExternalCheckerRegistryEntry.model_validate_json(
                json.dumps(values, separators=(",", ":"), sort_keys=True)
            )
        return make_external_checker_execution_request(
            registry=registry,
            identity=identity,
            configuration={},
            configuration_sha256=external_checker_json_hash({}),
            input={"task_version": "v1"},
            input_sha256=external_checker_json_hash({"task_version": "v1"}),
            materials=(material,),
        )

    async def evaluate(self, request, view):
        await super().evaluate(request, view)
        external_request = self.external_request(view.external_checker_material)
        with view.external_checker_grant(external_request) as grant:
            self.grant_path = self.scratch / "workspaces" / grant.grant_id
            self.manifest = json.loads(
                (self.grant_path / ".external-checker-grant.json").read_text()
            )
            assert self.manifest["phase"] == "post_submit"
            assert self.manifest["submission_id"] == str(request.submission_id)
            assert self.manifest["request_digest"] == external_request.request_digest
            assert self.manifest["binding_digest"] == grant.binding_digest
            assert "runtime_scratch" not in self.manifest
            assert not (self.grant_path / "runtime").exists()
        # Revocation removes the service grant immediately; the outer material
        # callback still owns its workspace until materialization completes.
        assert self.grant_path.is_dir()
        assert not (self.grant_path / ".external-checker-grant.json").exists()

        terminal_request = self.external_request(
            view.external_checker_material, terminal=True
        )
        with view.external_checker_grant(terminal_request) as grant:
            terminal_root = self.scratch / "workspaces" / grant.grant_id
            terminal_manifest = json.loads(
                (terminal_root / ".external-checker-grant.json").read_text()
            )
            assert terminal_manifest["runtime_scratch"]["byte_allowance"] > 0
            assert (terminal_root / "runtime").is_dir()

        changed = view.external_checker_material.model_copy(
            update={"binding_id": new_record_id()}
        )
        with pytest.raises(ArtifactScratchIntegrityError, match="material identity differs"):
            with view.external_checker_grant(self.external_request(changed)):
                pytest.fail("substituted material acquired an external grant")
        return result(request)


def assert_closed(h, consumer):
    with pytest.raises(RuntimeError, match="closed"):
        _ = consumer.view.entries
    with pytest.raises(RuntimeError, match="closed"):
        consumer.view.read_file(next(iter(h.files)), maximum_bytes=1024)
    with pytest.raises(TypeError, match="process-local"):
        pickle.dumps(consumer.view)
    assert list((h.scratch / "workspaces").iterdir()) == []
    assert not h.preparation._active


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_exact_materialization_reads_verified_original_and_revokes_view(tmp_path, isolated_database_env, provider):
    if provider == "minio":
        from tests.test_s3_artifact_store import provision_minio_bucket
        await provision_minio_bucket.__wrapped__()
    async with material_fixture(tmp_path, isolated_database_env, provider=provider) as h:
        execution = await material_execution(h)
        consumer = Consumer(h.files)
        material = await h.service.materialize(execution, consumer)
        assert material.submission_id == h.created.submission_id
        assert material.submission_version == h.created.submission_version
        assert material.admission_id == h.created.admission_id
        assert material.binding_id == h.created.artifact_binding_id
        assert material.content_id == h.created.artifact_content_id
        assert material.content_sha256 == h.request.content_sha256
        assert material.byte_count == len(h.data)
        assert material.semantic_manifest_sha256 == h.manifest.sha256
        assert consumer.calls == len(h.store.opens) == 1
        material.evaluation.validate_request(h.request)
        assert_closed(h, consumer)
        async with h.factory() as session:
            replica = (await session.execute(text(
                "select verified_replica_id,archive_sha256,archive_byte_count,semantic_manifest_sha256 "
                "from submission_bundle_admissions where id=:id"
            ), {"id": str(material.admission_id)})).one()
            actual_receipt = await session.scalar(text(
                "select id from audit_events where action_id='artifact.post_submit.checker_input.materialize' "
                "and resource_id=:run_id"
            ), {"run_id": str(execution.lease.reservation.attempt_id)})
        assert str(material.input_materialization_evidence_id) == str(actual_receipt)
        assert str(material.replica_id) == str(replica[0])
        assert (material.content_sha256, material.byte_count, material.semantic_manifest_sha256) == tuple(replica[1:])
        assert set(asdict(material)) == {"submission_id", "submission_version", "admission_id", "binding_id",
                                        "content_id", "replica_id", "content_sha256", "byte_count",
                                        "semantic_manifest_sha256", "evaluation",
                                        "input_materialization_evidence_id"}


async def test_post_external_grant_binds_native_submission_art_and_lease(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        consumer = ExternalGrantConsumer(h.files, execution, h.scratch)
        material = await h.service.materialize(execution, consumer)
        assert material.evaluation.outcome == "completed"
        assert consumer.manifest["lease_id"] == str(execution.lease.lease_id)
        assert consumer.manifest["content_id"] == str(material.content_id)
        assert consumer.grant_path is not None and not consumer.grant_path.exists()
        assert_closed(h, consumer)


async def test_revoked_materializer_denies_before_provider_or_scratch(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        await service_link_state(h.factory, ServiceIdentity.ARTIFACT_MATERIALIZER, active=False)
        consumer = Consumer(h.files)
        with pytest.raises(PostSubmissionMaterializationUnavailable, match="authority_unavailable"):
            await h.service.materialize(execution, consumer)
        assert h.store.opens == [] and consumer.calls == 0 and not h.preparation._active


async def test_foreign_or_changed_request_denies_before_provider(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        consumer = Consumer(h.files)
        for field in ("task_id", "assignment_id", "submission_id", "binding_id", "content_id", "submission_version", "byte_count", "content_sha256"):
            value = (2 if field == "submission_version" else h.request.byte_count + 1 if field == "byte_count"
                     else "sha256:" + "0" * 64 if field == "content_sha256" else new_record_id())
            with pytest.raises(PostSubmissionMaterializationUnavailable):
                await h.service.materialize(execution.model_copy(update={"request": change_request(h.request, **{field: value})}), consumer)
        assert h.store.opens == [] and consumer.calls == 0
        assert not h.preparation._active
        # A valid control reaches the same consumer through the real stored selection.
        await h.service.materialize(execution, consumer)
        assert consumer.calls == 1


@pytest.mark.parametrize("outcome", ["failure", "cancel", "replica_drift", "status_drift"])
async def test_async_exit_and_concurrent_drift_never_return_stale_material(tmp_path, isolated_database_env, outcome):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        consumer = Consumer(h.files)
        consumer.release = asyncio.Event()
        operation = asyncio.create_task(h.service.materialize(execution, consumer))
        await asyncio.wait_for(consumer.entered.wait(), 10)
        if outcome == "failure":
            consumer.failure = ValueError("controlled consumer failure")
            expected = ValueError
        elif outcome == "cancel":
            operation.cancel()
            expected = asyncio.CancelledError
        else:
            # An independent transaction must finish while material is in use:
            # no row lock may block a change during the callback.
            async with h.factory() as session, session.begin():
                await session.execute(text("set local lock_timeout='300ms'"))
                if outcome == "replica_drift":
                    await session.execute(text("update artifact_replicas set availability_state='unavailable' where id=:id"),
                                          {"id": str(h.replica_id)})
                else:
                    await session.execute(text("update submissions set status='checks_failed' where id=:id"),
                                          {"id": str(h.created.submission_id)})
            expected = PostSubmissionMaterializationUnavailable
        consumer.release.set()
        with pytest.raises(expected):
            await asyncio.wait_for(operation, 10)
        assert_closed(h, consumer)


async def test_wrong_provider_bytes_never_reach_consumer(tmp_path, isolated_database_env):
    from tests.archive_fixtures import byte_source as _bytes
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        consumer = Consumer(h.files)
        original = h.store.open
        h.store.open = lambda _: _bytes(h.data[:-1] + bytes([h.data[-1] ^ 1]))
        with pytest.raises(PostSubmissionMaterializationFailure, match="material_unavailable"):
            await h.service.materialize(execution, consumer)
        h.store.open = original
        assert consumer.calls == 0 and not h.preparation._active


async def test_abort_during_projection_prevents_consumer_entry(tmp_path, isolated_database_env, monkeypatch):
    from contextlib import contextmanager
    from threading import Event
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        entered, release = Event(), Event()
        original = h.inspector._projected_tree
        @contextmanager
        def paused_projection(*args, **kwargs):
            with original(*args, **kwargs) as tree:
                entered.set()
                assert release.wait(10)
                yield tree
        monkeypatch.setattr(h.inspector, "_projected_tree", paused_projection)
        consumer = Consumer(h.files)
        operation = asyncio.create_task(h.service.materialize(execution, consumer))
        assert await asyncio.to_thread(entered.wait, 10)
        operation.cancel()
        await asyncio.sleep(0.05)
        assert not operation.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(operation, 10)
        assert consumer.calls == 0 and not h.preparation._active
        assert list((h.scratch / "workspaces").iterdir()) == []


async def test_consumer_deadline_revokes_material_and_releases_scratch(tmp_path, isolated_database_env):
    from tests.test_checker_materialization import _limits
    async with material_fixture(tmp_path, isolated_database_env, scratch_limits=_limits(total_deadline_seconds=2)) as h:
        execution = await material_execution(h)
        consumer = Consumer(h.files)
        consumer.release = asyncio.Event()
        with pytest.raises(PostSubmissionMaterializationFailure, match="material_unavailable"):
            await asyncio.wait_for(h.service.materialize(execution, consumer), 10)
        assert consumer.calls == 1
        assert_closed(h, consumer)


async def test_post_submit_expansion_cannot_bypass_aggregate_quota(tmp_path, isolated_database_env):
    from app.modules.artifacts.preparation import HARD_MAXIMUM_ARTIFACT_BYTES
    from tests.test_checker_materialization import _limits
    async with material_fixture(tmp_path, isolated_database_env, scratch_limits=_limits(
        aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
    )) as h:
        execution = await material_execution(h)
        consumer = Consumer(h.files)
        with pytest.raises(PostSubmissionMaterializationFailure, match="material_unavailable"):
            await h.service.materialize(execution, consumer)
        assert consumer.calls == 0
        assert not h.preparation._active
        assert list((h.scratch / "workspaces").iterdir()) == []


async def test_stored_manifest_mismatch_never_reaches_consumer(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        consumer = Consumer(h.files)
        # Deliberately corrupt retained custody in this isolated database. Normal
        # database guards forbid these writes; exercise ART's independent byte check.
        async with h.factory() as session, session.begin():
            for table in ("submission_bundle_admissions", "pre_submit_evidence_sets"):
                await session.execute(text(f"alter table {table} disable trigger user"))
            await session.execute(text(
                "update pre_submit_evidence_sets set semantic_manifest_sha256=:bad where id="
                "(select pre_submit_evidence_set_id from submission_bundle_admissions where id=:id)"
            ), {"id": str(h.created.admission_id), "bad": "sha256:" + "0" * 64})
            await session.execute(text(
                "update submission_bundle_admissions set semantic_manifest_sha256=:bad where id=:id"
            ), {"id": str(h.created.admission_id), "bad": "sha256:" + "0" * 64})
            for table in ("submission_bundle_admissions", "pre_submit_evidence_sets"):
                await session.execute(text(f"alter table {table} enable trigger user"))
        with pytest.raises(PostSubmissionMaterializationFailure, match="manifest_mismatch"):
            await h.service.materialize(execution, consumer)
        assert len(h.store.opens) == 1 and consumer.calls == 0
        assert not h.preparation._active
        assert list((h.scratch / "workspaces").iterdir()) == []


async def test_foreign_consumer_result_is_rejected_and_cleaned(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        class WrongResult(Consumer):
            async def evaluate(self, request, view):
                await super().evaluate(request, view)
                return result(request, evaluation_generation=request.evaluation_generation + 1)
        consumer = WrongResult(h.files)
        with pytest.raises(ValueError, match="request mismatch"):
            await h.service.materialize(execution, consumer)
        assert consumer.calls == 1
        assert_closed(h, consumer)


async def test_provider_stream_has_no_selection_transaction_and_rejects_drift(tmp_path, isolated_database_env):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        # Tag only selection connections so pg_stat_activity can observe the
        # actual materializer session, independently of fixture/observer traffic.
        tag = "material-selection-" + str(new_record_id())
        selection_engine = create_async_engine(isolated_database_env, connect_args={
            "server_settings": {"application_name": tag},
        })
        h.service._sessions = async_sessionmaker(selection_engine)
        entered, release = asyncio.Event(), asyncio.Event()
        original = h.store.open
        async def paused_stream(reference):
            async for chunk in original(reference):
                entered.set()
                await release.wait()
                yield chunk
        h.store.open = paused_stream
        consumer = Consumer(h.files)
        operation = asyncio.create_task(h.service.materialize(execution, consumer))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            assert consumer.calls == 0
            async with h.factory() as session, session.begin():
                rows = (await session.execute(text(
                    "select pid, state, xact_start from pg_stat_activity where application_name=:tag"
                ), {"tag": tag})).all()
                assert rows and all(row.state == "idle" and row.xact_start is None for row in rows)
                locks = await session.scalar(text(
                    "select count(*) from pg_locks where pid in "
                    "(select pid from pg_stat_activity where application_name=:tag) "
                    "and locktype in ('relation', 'tuple', 'transactionid')"
                ), {"tag": tag})
                assert locks == 0
                await session.execute(text("set local lock_timeout='300ms'"))
                await session.execute(text(
                    "update artifact_replicas set availability_state='unavailable' where id=:id"
                ), {"id": str(h.replica_id)})
            release.set()
            with pytest.raises(PostSubmissionMaterializationUnavailable):
                await asyncio.wait_for(operation, 10)
            assert_closed(h, consumer)
        finally:
            release.set()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            await selection_engine.dispose()


async def test_consumption_retains_inspected_manifest_and_replays_without_provider_reads(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.adapters.artifacts.local import LocalStorageAdapter
    from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService

    consume = SubmissionAdmissionConsumptionService.consume
    observed = []

    def forbidden_read(*args, **kwargs):
        raise AssertionError("admission consumption must not read object bytes")

    async def capture(service, request):
        with monkeypatch.context() as patch:
            patch.setattr(LocalStorageAdapter, "open", forbidden_read)
            first = await consume(service, request)
        assert not first.replayed
        observed.append((request, first))
        return first

    monkeypatch.setattr(SubmissionAdmissionConsumptionService, "consume", capture)
    async with material_fixture(tmp_path, isolated_database_env) as h:
        assert len(observed) == 1
        request, first = observed[0]
        material = first.material
        from tests.test_artifact_bindings import _replay_request
        from app.modules.artifacts.authorization import PreparedSubmissionBindingAuthorization
        async with h.factory() as session, session.begin():
            with monkeypatch.context() as patch:
                patch.setattr(LocalStorageAdapter, "open", forbidden_read)
                replay = await SubmissionAdmissionConsumptionService(session, PreparedSubmissionBindingAuthorization(
                    session, request_id=new_record_id(), correlation_id=new_record_id(),
                )).read_consumed(_replay_request(request))
        assert replay.replayed and replay.material == material
        assert material.archive_sha256 == h.request.content_sha256
        assert material.archive_byte_count == len(h.data)
        assert material.semantic_manifest_sha256 == h.manifest.sha256
        assert [(item.normalized_path, item.sha256, item.byte_count) for item in material.files] == [
            (entry.normalized_path, entry.sha256, entry.byte_count)
            for entry in h.manifest.entries if entry.sha256 is not None
        ]
        async with h.factory() as session:
            body = await session.scalar(text(
                "select semantic_manifest_body from submission_bundle_admissions where id=:id"
            ), {"id": str(h.created.admission_id)})
        assert body == h.manifest.as_dict()
