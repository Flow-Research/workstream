"""Real source intake/OUTBOX finalization fixtures and controlled POST authority."""

from tests.checkers.external.support import pre_registry_spec, post_registry_spec
from tests.trusted_intake_fixtures import LocalIntakeAdapter

from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID
import zipfile

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import create_artifact_store_bootstrap, post_submission_materialization
from app.adapters.tasks import submitted_bundle_port
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import (
    ArtifactByteRange,
    ArtifactStoreNamespaceClaim,
)
from app.modules.artifacts.models import SubmissionBundleAdmission
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
from app.modules.artifacts.service import artifact_storage_namespace_spec
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
)
from app.modules.artifacts.api.submission_manifest import (
    build_submission_manifest,
)
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.models import SubmissionDispatch
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
from tests.retained_material_fixtures import _foreground, finalize_retained_intake
from tests.artifacts.test_submission_pre_source import _source_runtime
from app.modules.tasks.api.submitted_bundle import SubmittedBundleRequest
from tests.artifact_store_helpers import artifact_admission_limit_settings
from tests.selected_policy_fixtures import approved_selected_policy_fixture
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.test_artifact_admission import _settings, _context, _seed_human_actor
from tests.test_checker_materialization import _limits
from tests.archive_fixtures import byte_source as _bytes, submission_archive as _archive


class CountedStore:
    def __init__(self, store):
        self.wrapped, self.opens = store, []
        self.identity = store.identity

    def open(
        self,
        reference: str,
        byte_range: ArtifactByteRange | None = None,
    ):
        self.opens.append(reference)
        return self.wrapped.open(
            reference,
            byte_range,
        )


    def open_source(self, source, **kwargs):
        self.opens.append(source.location.object_ref)
        return self.wrapped.open_source(source, **kwargs)


def archive_with_modes(evidence_path, project_id):
    """Build a valid packet with independently known executable/plain members."""
    data = _archive(evidence_path=evidence_path)
    # Preserve the valid governed packet and add both Unix file-mode cases.
    archive_bytes = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as source, zipfile.ZipFile(archive_bytes, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item))
        for name, mode in (("run.sh", 0o100755), ("notes.txt", 0o100644)):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = mode << 16
            target.writestr(entry, f"project {project_id}\n".encode())
    return archive_bytes.getvalue()


async def provision_material_services(factory, *, artifacts, checker):
    """Provision only the fixed identities present in the schema under test."""
    from tests.checkers.execution.support import provision_post_submit_service

    if artifacts:
        for identity in (ServiceIdentity.ARTIFACT_MATERIALIZER, ServiceIdentity.ARTIFACT_BINDING,
                         ServiceIdentity.CHECKER_PRE_SUBMIT, ServiceIdentity.OUTBOX_DISPATCHER):
            await provision_post_submit_service(factory, identity)
    if checker:
        await provision_post_submit_service(factory)


def _archive_facts(data):
    """Inspect the exact admitted ZIP used by the execution fixture."""
    inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
    manifest = build_submission_manifest(inspector.inspect(BytesIO(data)))
    with zipfile.ZipFile(BytesIO(data)) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    import hashlib

    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    return inspector, manifest, files, digest


async def _submit_current_source(factory, context, command, metadata, data):
    return await command.submit(
        metadata, _bytes(data), actor_id=context.actor_profile_id,
        identity_link_id=context.identity_link_id, idempotency_key=new_record_id(),
        declared_raw_bytes=len(data),
    )


async def _read_current_request(session, facts, created, data):
    from app.adapters.checkers import evaluation_coordinator

    stored = await evaluation_coordinator(session).read_reserved_evaluation(
        project_id=facts.project_id,
        task_id=facts.task_id,
        submission_id=created.submission_id,
        request_id=created.evaluation_request_id,
    )
    return stored.request


@asynccontextmanager
async def material_fixture(tmp_path, database_url, **options):
    """Current canonical creation always commits its own exact initial request."""
    async with _material_fixture(
        tmp_path,
        database_url,
        submit_source=_submit_current_source,
        read_request=_read_current_request,
        **options,
    ) as material:
        yield material


def _material_storage(tmp_path, provider, storage_settings, scratch_limits, post_scratch_root):
    if storage_settings is not None:
        settings = storage_settings
    elif provider == "minio":
        from tests.test_s3_artifact_store import minio_settings

        settings = minio_settings(private_prefix=f"material/{new_record_id()}", buffer_bytes=65536).model_copy(
            update={
                **artifact_admission_limit_settings(1024 * 1024),
                "artifact_scratch_root": tmp_path / "intake-scratch",
                "artifact_scratch_minimum_free_bytes": 0,
            }
        )
    else:
        settings = _settings(tmp_path, maximum_bytes=1024 * 1024).model_copy(
            update={
                "external_checker_service_socket": tmp_path / "checker.sock",
                "external_checker_material_root": tmp_path / "scratch",
            }
        )
    bootstrap = create_artifact_store_bootstrap(settings)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            bootstrap.identity,
            bootstrap.namespace_identity,
            namespace.namespace_fingerprint,
        )
    )
    scratch = post_scratch_root or tmp_path / "post-scratch"
    manager = ArtifactScratchManager(
        root=scratch,
        limits=scratch_limits if scratch_limits is not None else _limits(),
    )
    return settings, bootstrap, namespace, store, scratch, manager


async def create_source_submission(factory, context, store, namespace, settings, metadata, data,
                                   *, submit_source=_submit_current_source):
    """Commit exact archive bytes through foreground acceptance and durable T5."""
    runtime_root = settings.artifact_scratch_root.parent / f"source-pre-{new_record_id()}"
    runtime_root.mkdir(parents=True)
    runtime, errors = _source_runtime(data, runtime_root, "completed")
    command = _foreground(factory, context, namespace, store, runtime)
    receipt = await submit_source(factory, context, command, metadata, data)
    assert not errors, "\n".join(errors)
    intake = SimpleNamespace(operation_id=UUID(receipt["operation_id"]), store=store,
                             namespace=namespace, settings=settings)
    submission_id = await finalize_retained_intake(factory, intake)
    async with factory() as session:
        dispatch = await session.get(SubmissionDispatch, submission_id)
        return dispatch.result()


async def _create_material_submission(
    factory,
    engine,
    plan,
    policy,
    store,
    namespace,
    settings,
    submit_source,
    *,
    provision_services,
    provision_checker,
):
    context = _context()
    await provision_material_services(
        factory, artifacts=provision_services, checker=provision_checker
    )
    task_id, assignment_id = new_record_id(), new_record_id()
    async with factory.begin() as session:
        await _seed_human_actor(session, context)
    params = dict(
        task=str(task_id),
        assignment=str(assignment_id),
        project=str(plan.lineage.project_id),
        actor=str(context.actor_profile_id),
    )
    async with engine.begin() as connection:
        await seed_started_task_for_artifact_test(connection, params)
        await install_submitter_grant(connection, params)
    data = archive_with_modes(policy["evidence_path"], plan.lineage.project_id)
    metadata = SubmissionIntakeMetadata(
        task_id=task_id, assignment_id=assignment_id,
        feedback="Completed the required project work and included evidence.",
    )
    created = await create_source_submission(factory, context, store, namespace, settings, metadata, data,
                                             submit_source=submit_source)
    admission_id = created.admission_id
    creation_request = SubmissionCreationRequest(
        task_id=task_id, assignment_id=assignment_id, contributor_id=context.actor_profile_id,
        predecessor_submission_id=None, admission_id=admission_id,
        feedback=metadata.feedback,
    )
    return context, task_id, data, admission_id, creation_request, created


@asynccontextmanager
async def _material_fixture(
    tmp_path,
    database_url,
    *,
    submit_source,
    read_request,
    provider="local",
    scratch_limits=None,
    storage_settings=None,
    provision_services=True,
    provision_checker=True,
    contribution_awards=(),
    human_review_required=True,
    max_revision_rounds=2,
    pre_submit_registry_spec=pre_registry_spec(),
    post_submit_registry_spec=post_registry_spec(),
    post_submit_configuration_setup=None,
    post_submit_configurations_setup=None,
    post_submit_specification=None,
    post_scratch_root=None,
    artifact_deadline_ms=120_000,
):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings, bootstrap, namespace, store, scratch, manager = _material_storage(
        tmp_path, provider, storage_settings, scratch_limits, post_scratch_root)
    try:
        if namespace.provider_profile == "minio-v1":
            async with store._client() as client:
                await client.put_bucket_versioning(
                    Bucket=settings.artifact_s3_bucket, VersioningConfiguration={"Status": "Enabled"},
                )
        plan, policy = await approved_selected_policy_fixture(
            factory,
            namespace,
            guide_version="v1",
            contribution_awards=contribution_awards,
            human_review_required=human_review_required,
            max_revision_rounds=max_revision_rounds,
            pre_submit_registry_spec=pre_submit_registry_spec,
            post_submit_registry_spec=post_submit_registry_spec,
            post_submit_configuration_setup=post_submit_configuration_setup,
            post_submit_configurations_setup=post_submit_configurations_setup,
            post_submit_specification=post_submit_specification,
        )
        context, task_id, data, admission_id, creation_request, created = await _create_material_submission(
            factory,
            engine,
            plan,
            policy,
            store,
            namespace,
            settings,
            submit_source,
            provision_services=provision_services,
            provision_checker=provision_checker,
        )
        async with factory() as session:
            facts = await submitted_bundle_port(session).read(
                SubmittedBundleRequest(
                    plan.lineage.project_id,
                    task_id,
                    created.submission_id,
                )
            )
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            replica_id = UUID(admission.verified_replica_id)
            request = await read_request(session, facts, created, data)
        inspector, manifest, files, digest = _archive_facts(data)
        counted = CountedStore(store)
        preparation = ArtifactPreparationService(manager)
        service = post_submission_materialization(
            sessions=factory,
            store=counted,
            namespace=namespace,
            preparation=preparation,
            intake=LocalIntakeAdapter(inspector), archive_limits=SubmissionArchiveLimits(), artifact_deadline_ms=artifact_deadline_ms,
        )
        yield SimpleNamespace(
            replica_id=replica_id,
            service=service,
            factory=factory,
            engine=engine,
            request=request,
            created=created,
            facts=facts,
            files=files,
            data=data,
            manifest=manifest,
            actor_context=context,
            creation_request=creation_request,
            settings=settings,
            store=counted,
            namespace=namespace,
            preparation=preparation,
            manager=manager,
            inspector=inspector,
            scratch=scratch,
        )
    finally:
        manager.close()
        bootstrap.close()
        await engine.dispose()
