"""Real compiled/projected parents; finalization authority stays a strict test port."""

from app.modules.authorization.api import ProjectGuideCompilationRequestOrigin
from dataclasses import asdict
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.adapters.auth import (
    artifact_policy_projection_authorization,
    guide_sufficiency_projection_authorization,
)
from app.adapters.artifacts import (
    guide_document_manifest_port,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    ProjectGuideCompilationRequestFacts,
)
from app.modules.authorization.guide_compilation import ProjectGuideCompilationAuthorizationAdapter
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.projects.api import (
    ProjectGuideProjectionCommand,
    ProjectGuideSetupFinalizationCommand,
)
from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService
from app.modules.projects.guide_compilation.service import GuideCompilationService
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from app.modules.projects.setup_queue import dispatch_project_guide_compilation_after_commit
from ..helpers import (
    context,
    generated_result,
    identity,
    persistence_facts,
)


async def request_compilation(factory, values, compilation_context, predecessor_id):
    """Exercise real human request authority using a narrowly seeded project manager."""
    human, link = new_record_id(), new_record_id()
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "insert into actor_profiles(id,actor_kind,status,provisioning_method,created_by) "
                "values(:id,'human','active','automatic_first_access','test')"
            ),
            {"id": str(human)},
        )
        await session.execute(
            text(
                "insert into actor_identity_links(id,actor_profile_id,issuer,subject,subject_kind,"
                "status,linked_by,last_verified_at) values(:id,:actor,'https://identity.flowresearch.tech',:subject,"
                "'human','active','test',:now)"
            ),
            {"id": str(link), "actor": str(human), "subject": str(human), "now": datetime.now(UTC)},
        )
        from project_create_fixtures import grant_fixture_admin_role
        await grant_fixture_admin_role(session, human, project_id=values["project"])
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    ctx = HumanAuthorizationContext(
        actor_profile_id=human,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=link,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    attempt_identity = identity(compilation_context)
    all_facts = asdict(
        persistence_facts(
            values, new_record_id(), attempt_identity, predecessor_id=predecessor_id
        )
    )
    facts = ProjectGuideCompilationRequestFacts(
        **{
            name: all_facts[name]
            for name in ProjectGuideCompilationRequestFacts.__dataclass_fields__
        }
    )
    async with factory() as session:
        repository = AdminAuthorizationRepository(session)
        kernel = AuthorizationService(session, ctx, admin_repository=repository)
        prepared = PreparedAuthorizationService(session, ctx, kernel, repository)
        return await GuideCompilationService(
            session, ProjectGuideCompilationAuthorizationAdapter(kernel, prepared)
        ).authorize_request(
            origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
            actor=actor,
            facts=facts,
            identity=attempt_identity,
            runtime_configuration=compilation_context.runtime_configuration,
        )


async def compilation_and_projections(
    url,
    factory,
    values,
    *,
    classification="draft_ready",
    project=True,
    compilation_context=None,
    predecessor_id=None,
    outcome=None,
    requested=None,
):
    """Persist one accepted compilation with real custody guards and real projection adapters."""
    compilation_context = compilation_context or context(values)
    requested = requested or await request_compilation(
        factory, values, compilation_context, predecessor_id
    )
    await admit_compilation_delivery(factory, compilation_context)
    supplied_outcome = outcome is not None
    outcome = outcome or generated_result()
    if classification != "draft_ready" and not supplied_outcome:
        patch = {
            "status": classification,
            "findings": (
                outcome.findings[0].model_copy(
                    update={
                        "severity": "blocking_gap"
                        if classification == "guide_blocked"
                        else "warning"
                    }
                ),
            ),
        }
        if classification == "guide_blocked":
            patch.update(
                submission_artifact_policy=None,
                requirements=(),
            )
        outcome = outcome.model_copy(update=patch)
    from ..test_hidden_orchestrator_postgresql import _Runtime, _port
    from app.modules.projects.api import (
        ProjectGuideCompilationExecutionCommand, ProjectGuideCompilationExecutionClassification,
    )
    runtime = _Runtime(outcome)
    runtime.identity = compilation_context.runtime_configuration.adapter_identity
    receipt = await _port(
        factory,
        runtime,
    ).execute(
        ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    )
    assert receipt.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
    assert runtime.calls == 1
    if project:
        projections = GuideCompilationProjectionService(
            factory,
            material_factory=guide_document_manifest_port,
            sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
            policy_authorization_factory=artifact_policy_projection_authorization,
        )
        command = ProjectGuideProjectionCommand(attempt_id=requested.attempt_id)
        await projections.project_guide_sufficiency(command)
        if classification != "guide_blocked":
            await projections.project_submission_artifact_policy(command)
    return ProjectGuideSetupFinalizationCommand(
        project_id=values["project"],
        guide_id=values["guide"],
        setup_run_id=compilation_context.setup_run_id,
        setup_generation=compilation_context.setup_generation,
        compilation_id=receipt.compilation_id,
    )


async def admit_compilation_delivery(factory, compilation_context):
    """Commit the canonical queue transition without contacting a test broker."""
    material = compilation_context.material
    task_id = project_guide_compilation_task_id(
        str(compilation_context.setup_run_id), compilation_context.setup_generation
    )
    with patch(
        "app.modules.projects.setup_queue.enqueue_project_guide_compilation",
        return_value=task_id,
    ):
        async with factory() as session:
            dispatched = await dispatch_project_guide_compilation_after_commit(
                session,
                project_id=str(material.project_id),
                guide_id=str(material.guide_id),
                source_snapshot_id=str(material.source_snapshot_id),
                setup_run_id=str(compilation_context.setup_run_id),
                setup_generation=compilation_context.setup_generation,
                claimed_task_id=task_id,
            )
    assert dispatched == task_id
