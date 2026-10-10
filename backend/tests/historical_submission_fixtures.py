"""Explicit predecessor storage for migration proofs, never a current intake writer.

Only migration tests call this seeder. It writes the pre-0025 row shape with all
then-installed constraints enabled; it does not invent current AUTH or dispatch
receipts. Preparation and verification still use real ART owners and ZIP bytes.
"""

from contextlib import AsyncExitStack, asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select, func

from app.core.identifiers import new_record_id
from app.modules.artifacts.models import ArtifactBinding, SubmissionBundleAdmission
from app.modules.checkers.api.post_submit import make_post_submit_request
from app.modules.tasks.api import TaskSubmissionContextRequest
from app.modules.tasks.models import Submission
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.submission_composition import build_submission
from tests.post_submit_materialization_helpers import _material_fixture, _archive_facts
from tests.migration_fixtures import current_art_attempt_seed_schema


async def write_historical_submission(factory, context, request):
    """Seed only an actual predecessor schema; never bypass current constraints."""
    from sqlalchemy import text
    async with factory() as session, session.begin():
        revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
        assert revision in {
            "0007_checker_output_custody", "0008_checker_execution", "0009_checker_material_lineage",
            "0010_post_submit_authority", "0011_task_routing_source", "0012_review_packet",
            "0013_review_source", "0014_final_acceptance", "0015_contribution_awards",
            "0017_acceptance_source_contracts", "0018_task_routing_request",
            "0020_review_admission_lock_order", "0021_submission_manifest",
            "0022_submission_packet_custody", "0023_remove_task_payment_policy",
            "0024_require_second_review_false",
        }, "historical seeder cannot write the current schema"
        repository = TaskRepository(session)
        facts = await repository.lock_submission_context(TaskSubmissionContextRequest(
            request.task_id, request.assignment_id, request.contributor_id, request.predecessor_submission_id,
        ))
        task = await repository.get_task(str(request.task_id))
        admission = await session.get(SubmissionBundleAdmission, str(request.admission_id))
        assert admission.status == "ready" and admission.actor_profile_id == str(context.actor_profile_id)
        version = 1 if facts.predecessor is None else facts.predecessor.version + 1
        submission_id, binding_id = new_record_id(), new_record_id()
        submission = build_submission(
            submission_id=str(submission_id), task=task, contributor_id=str(request.contributor_id),
            version=version, summary=request.summary, worker_attestation=request.contributor_attestation,
            supersedes_submission_id=str(request.predecessor_submission_id) if request.predecessor_submission_id else None,
            contribution_policy_version_id=facts.submitter_contribution_policy_version_id,
            task_assignment_id=str(request.assignment_id),
        )
        session.add(submission)
        await session.flush()
        session.add(ArtifactBinding(
            id=str(binding_id), content_id=admission.artifact_content_id, project_id=admission.project_id,
            resource_type="submission", resource_id=str(submission_id), logical_role="submission_bundle_original",
            scope_version=1, actor_id=admission.actor_profile_id, attribution_type="contributor",
        ))
        consumed_at = await session.scalar(select(func.now()))
        admission.status = "consumed"
        admission.consumed_at = consumed_at
        admission.consumed_by_submission_id = str(submission_id)
        admission.consumed_by_submission_version = version
        submission.submission_bundle_admission_id = admission.id
        submission.artifact_binding_id = str(binding_id)
        submission.artifact_content_id = admission.artifact_content_id
        task.status = "submitted"
        await session.flush()
        return SimpleNamespace(submission_id=submission_id, submission_version=version,
            admission_id=request.admission_id, artifact_binding_id=binding_id,
            artifact_content_id=UUID(admission.artifact_content_id), task_context=facts)


async def _historical_request(session, facts, created, data):
    """Project genuine historical inputs without creating a future reservation."""
    from app.adapters.tasks import task_service
    from app.adapters.checkers import submission_evaluation_content
    from app.core.config import get_settings
    from app.modules.checkers.api import SubmissionPacketView
    from app.modules.tasks.models import WorkstreamTask
    submission = await session.get(Submission, str(created.submission_id))
    task = await session.get(WorkstreamTask, submission.task_id)
    project = await task_service(session, settings=get_settings())._load_locked_task_context(task)
    _, manifest, _, digest = _archive_facts(data)
    content = submission_evaluation_content(
        created.task_context, project.facts,
        SubmissionPacketView(submission.summary, submission.worker_attestation),
        manifest.file_facts(), digest,
    )
    return make_post_submit_request(
        **content.model_dump(), evaluation_request_id=new_record_id(), evaluation_generation=1,
        task_id=facts.task_id, assignment_id=facts.assignment_id,
        submission_id=created.submission_id, submission_version=created.submission_version,
        content_id=created.artifact_content_id, binding_id=created.artifact_binding_id,
        content_sha256=digest, byte_count=len(data),
    )


@asynccontextmanager
async def historical_material_fixture(tmp_path, database_url, **options):
    async with AsyncExitStack() as stack:
        async with current_art_attempt_seed_schema(database_url):
            material = await stack.enter_async_context(_material_fixture(
                tmp_path, database_url, write_submission=write_historical_submission,
                read_request=_historical_request, **options,
            ))
        yield material
