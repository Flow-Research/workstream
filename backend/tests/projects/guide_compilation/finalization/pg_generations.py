"""A second real setup/material generation for cross-generation custody probes."""

from datetime import timedelta

from sqlalchemy import null, select, text

from app.modules.projects.api.guide_documents import GuideDocumentManifestRequest
from app.adapters.artifacts import (
    guide_document_manifest_port,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.models import ProjectSetupRun
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from ..helpers import context


async def clone_row(session, model, source_id, **changes):
    """Copy a real parent row while naming each new immutable lineage edge."""
    source = await session.get(model, str(source_id))
    assert source is not None
    values = {column.key: getattr(source, column.key) for column in model.__table__.columns}
    values.update(changes)
    row = model(**values)
    session.add(row)
    await session.flush()
    return row


async def second_generation(factory, values):
    """Rebind committed originals to a separate setup generation and opaque grant."""
    async with factory() as session, session.begin():
        await session.execute(text("alter table project_setup_runs disable trigger user"))
        setup_id = str(values["setup_2"])
        source = await session.get(ProjectSetupRun, str(values["setup_1"]))
        created = source.created_at + timedelta(microseconds=1)
        await clone_row(
            session,
            ProjectSetupRun,
            values["setup_1"],
            id=setup_id,
            setup_generation=2,
            created_at=created,
            updated_at=created,
            # ORM JSON None becomes JSON null; a pristine setup requires SQL NULL.
            post_submit_derivation_summary=null(),
            celery_task_id=project_guide_compilation_task_id(setup_id, 2),
        )
        await session.execute(text("alter table project_setup_runs enable trigger user"))
        latest = await ProjectRepository(session).lock_latest_project_setup_run(
            str(values["project"]), str(values["guide"]), "v1"
        )
        assert latest.id == setup_id and latest.setup_generation == 2
        assert await session.scalar(
            select(ProjectSetupRun.post_submit_derivation_summary.is_(None)).where(
                ProjectSetupRun.id == setup_id
            )
        )
        material = await guide_document_manifest_port(session).load(
            GuideDocumentManifestRequest(
                project_id=values["project"],
                guide_id=values["guide"],
                guide_source_snapshot_id=values["snapshot"],
                project_setup_run_id=values["setup_2"],
                setup_generation=2,
            )
        )
    return context(values, generation=2).model_copy(update={"material": material})
