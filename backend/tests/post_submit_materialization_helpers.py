"""Real verified admission/Submission fixtures and controlled post-submit authority."""

from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID
import zipfile

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import create_artifact_store_bootstrap, post_submission_materialization
from app.adapters.tasks import submitted_bundle_port
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import ArtifactStoreNamespaceClaim
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.models import SubmissionBundleAdmission
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
from app.modules.artifacts.service import artifact_storage_namespace_spec
from app.modules.artifacts.submission_archive import SubmissionArchiveInspector, SubmissionArchiveLimits
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.api.submitted_bundle import SubmittedBundleRequest
from tests.artifact_store_helpers import artifact_admission_limit_settings
from tests.pre_submit_test_helpers import approved_pre_submit_fixture
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.tasks.submission_lineage_support import _seed_services, _verified_admission
from tests.test_artifact_admission import _settings, _context, _seed_human_actor
from tests.test_checker_materialization import _limits
from tests.test_default_pre_submit_execution import _archive, _bytes


class CountedStore:
    def __init__(self, store):
        self.wrapped, self.opens = store, []
        self.identity = store.identity

    def open(self, reference):
        self.opens.append(reference)
        return self.wrapped.open(reference)


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
        await _seed_services(factory)
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


async def _write_current_submission(factory, context, request):
    async with factory() as session:
        return await compose_hidden_submission_creation_command(
            session, context, request_id=new_record_id(), correlation_id=new_record_id(),
        ).create(request)


async def _read_current_request(session, facts, created, data):
    from app.adapters.checkers import evaluation_coordinator
    stored = await evaluation_coordinator(session).read_reserved_evaluation(
        project_id=facts.project_id, task_id=facts.task_id, submission_id=created.submission_id,
        request_id=created.evaluation_request_id,
    )
    return stored.request


@asynccontextmanager
async def material_fixture(tmp_path, database_url, **options):
    """Current canonical creation always commits its own exact initial request."""
    async with _material_fixture(
        tmp_path, database_url, write_submission=_write_current_submission,
        read_request=_read_current_request, **options,
    ) as material:
        yield material


@asynccontextmanager
async def _material_fixture(
    tmp_path,
    database_url,
    *,
    write_submission,
    read_request,
    provider="local",
    scratch_limits=None,
    storage_settings=None,
    provision_services=True,
    provision_checker=True,
    contribution_awards=(),
    human_review_required=True,
):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    if storage_settings is not None:
        settings = storage_settings
    elif provider == "minio":
        from tests.test_s3_artifact_store import minio_settings
        settings = minio_settings(private_prefix=f"material/{new_record_id()}").model_copy(update={
            **artifact_admission_limit_settings(1024 * 1024),
            "artifact_scratch_root": tmp_path / "intake-scratch",
            "artifact_scratch_minimum_free_bytes": 0,
        })
    else:
        settings = _settings(tmp_path, maximum_bytes=1024 * 1024)
    bootstrap = create_artifact_store_bootstrap(settings)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    store = bootstrap.initialize_after_namespace_claim(ArtifactStoreNamespaceClaim(
        bootstrap.identity, bootstrap.namespace_identity, namespace.namespace_fingerprint,
    ))
    manager = ArtifactScratchManager(root=tmp_path / "post-scratch", limits=scratch_limits if scratch_limits is not None else _limits())
    try:
        plan, policy = await approved_pre_submit_fixture(
            factory,
            namespace,
            guide_version="v1",
            contribution_awards=contribution_awards,
            human_review_required=human_review_required,
        )
        context = _context()
        await provision_material_services(factory, artifacts=provision_services, checker=provision_checker)
        task_id, assignment_id = new_record_id(), new_record_id()
        async with factory.begin() as session:
            await _seed_human_actor(session, context)
        async with engine.begin() as connection:
            params = dict(task=str(task_id), assignment=str(assignment_id),
                          project=str(plan.lineage.project_id), actor=str(context.actor_profile_id))
            await seed_started_task_for_artifact_test(connection, params)
            await install_submitter_grant(connection, params)
        data = archive_with_modes(policy["evidence_path"], plan.lineage.project_id)
        preparation_request = SubmissionBundlePreparationRequest(
            actor=ActorIdentityFacts(context.actor_profile_id, context.identity_link_id, ActorKind.HUMAN),
            request_id=context.request_id, correlation_id=context.correlation_id,
            task_id=task_id, assignment_id=assignment_id, predecessor_submission_id=None,
            idempotency_key=new_record_id(), summary="Completed the required project work and included evidence.",
            contributor_attestation="I confirm no confidential client data, credentials, or copied source material is included in this submission; rights_confirmed. " + " ".join(policy["attestation_terms"]),
            media_type="application/zip", byte_source=_bytes(data),
        )
        admission_id = await _verified_admission(factory, store, namespace, settings, context, preparation_request)
        creation_request = SubmissionCreationRequest(
            task_id=task_id, assignment_id=assignment_id, contributor_id=context.actor_profile_id,
            predecessor_submission_id=None, admission_id=admission_id,
            summary=preparation_request.summary,
            contributor_attestation=preparation_request.contributor_attestation,
        )
        created = await write_submission(factory, context, creation_request)
        async with factory() as session:
            facts = await submitted_bundle_port(session).read(SubmittedBundleRequest(
                plan.lineage.project_id, task_id, created.submission_id,
            ))
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            replica_id = UUID(admission.verified_replica_id)
            request = await read_request(session, facts, created, data)
        inspector, manifest, files, digest = _archive_facts(data)
        counted = CountedStore(store)
        preparation = ArtifactPreparationService(manager)
        service = post_submission_materialization(
            sessions=factory, store=counted, namespace=namespace,
            preparation=preparation, inspector=inspector,
        )
        yield SimpleNamespace(replica_id=replica_id, service=service, factory=factory, engine=engine, request=request,
                              created=created, facts=facts, files=files, data=data, manifest=manifest,
                              actor_context=context, creation_request=creation_request,
                              settings=settings,
                              store=counted, namespace=namespace, preparation=preparation,
                              manager=manager, inspector=inspector,
                              scratch=tmp_path / "post-scratch")
    finally:
        manager.close()
        bootstrap.close()
        await engine.dispose()
